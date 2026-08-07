"""Celery application and tasks."""

from __future__ import annotations

import asyncio
import logging
from typing import Any
from uuid import UUID

from celery import Celery

from netatlas.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

celery_app = Celery(
    "netatlas",
    broker=settings.rabbitmq_url,
    backend=settings.redis_url,
)
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_routes={
        "netatlas.workers.tasks.run_discovery_job": {"queue": "discovery"},
        "netatlas.workers.tasks.collect_metrics": {"queue": "metrics"},
        "netatlas.workers.tasks.evaluate_triggers": {"queue": "maintenance"},
        "netatlas.workers.tasks.purge_observability": {"queue": "maintenance"},
    },
    beat_schedule={
        "evaluate-triggers": {
            "task": "netatlas.workers.tasks.evaluate_triggers",
            "schedule": float(settings.trigger_eval_interval_seconds),
        },
        "collect-metrics": {
            "task": "netatlas.workers.tasks.collect_metrics",
            "schedule": float(settings.metrics_interval_seconds),
        },
        "purge-observability": {
            "task": "netatlas.workers.tasks.purge_observability",
            "schedule": 3600.0,
        },
    },
)


def main() -> None:
    celery_app.start()


@celery_app.task(name="netatlas.workers.tasks.run_discovery_job")
def run_discovery_job(job_id: str) -> dict[str, Any]:
    return asyncio.run(_run_discovery(UUID(job_id)))


@celery_app.task(name="netatlas.workers.tasks.collect_metrics")
def collect_metrics() -> dict[str, Any]:
    return asyncio.run(_collect_metrics())


@celery_app.task(name="netatlas.workers.tasks.evaluate_triggers")
def evaluate_triggers() -> dict[str, Any]:
    return asyncio.run(_evaluate_triggers())


@celery_app.task(name="netatlas.workers.tasks.purge_observability")
def purge_observability() -> dict[str, Any]:
    return asyncio.run(_purge_observability())


async def _run_discovery(job_id: UUID) -> dict[str, Any]:
    from netatlas.application.use_cases.discovery import DiscoveryOrchestrator
    from netatlas.infrastructure.collectors.base.registry import build_default_registry
    from netatlas.infrastructure.persistence.repositories import (
        SqlAlchemyArpRepository,
        SqlAlchemyDeviceRepository,
        SqlAlchemyDiscoveryJobRepository,
        SqlAlchemyDiscoverySeedRepository,
        SqlAlchemyFdbRepository,
        SqlAlchemyInterfaceRepository,
        SqlAlchemyLinkRepository,
        SqlAlchemyNeighborRepository,
        SqlAlchemyRouteRepository,
        SqlAlchemySnapshotRepository,
        SqlAlchemyVlanRepository,
    )
    from netatlas.infrastructure.persistence.session import SessionLocal
    from netatlas.infrastructure.security.credential_resolver import (
        bind_device_credentials,
        discovery_profile_ids,
        load_profile_candidates,
        load_profiles,
    )
    from netatlas.infrastructure.security.vault import AesGcmSecretVault

    async with SessionLocal() as session:
        vault = AesGcmSecretVault(get_settings().master_key_b64.get_secret_value())

        async def credential_loader(seeds: list[Any]) -> dict[str, Any]:
            # Seed attachments + all SNMP profiles (so Credentials page profiles work).
            profile_ids = await discovery_profile_ids(session, seeds, include_global_snmp=True)
            return await load_profiles(session, vault, profile_ids, default_snmp=True)

        async def credential_candidates_loader(seeds: list[Any]) -> list[dict[str, Any]]:
            """Rotate seed + global SNMP profiles until one answers sysDescr."""
            profile_ids = await discovery_profile_ids(session, seeds, include_global_snmp=True)
            return await load_profile_candidates(session, vault, profile_ids, default_snmp=True)

        async def on_device(
            device: Any, seeds: list[Any], verified_profile_id: str | None = None
        ) -> None:
            # Prefer the SNMP profile that answered; else bind seed + global SNMP profiles.
            if verified_profile_id:
                await bind_device_credentials(session, device.id, [UUID(str(verified_profile_id))])
                return
            profile_ids = await discovery_profile_ids(session, seeds, include_global_snmp=True)
            await bind_device_credentials(session, device.id, profile_ids)

        async def progress_callback(_jid: UUID, _payload: dict[str, Any]) -> None:
            # Commit mid-run so API/UI see progress and cancel flags
            await session.commit()

        async def session_rollback() -> None:
            await session.rollback()

        orch = DiscoveryOrchestrator(
            jobs=SqlAlchemyDiscoveryJobRepository(session),
            seeds=SqlAlchemyDiscoverySeedRepository(session),
            devices=SqlAlchemyDeviceRepository(session),
            interfaces=SqlAlchemyInterfaceRepository(session),
            links=SqlAlchemyLinkRepository(session),
            snapshots=SqlAlchemySnapshotRepository(session),
            registry=build_default_registry(),
            credential_loader=credential_loader,
            credential_candidates_loader=credential_candidates_loader,
            progress_callback=progress_callback,
            on_device=on_device,
            neighbors=SqlAlchemyNeighborRepository(session),
            fdb=SqlAlchemyFdbRepository(session),
            arp=SqlAlchemyArpRepository(session),
            vlans=SqlAlchemyVlanRepository(session),
            routes=SqlAlchemyRouteRepository(session),
            session_rollback=session_rollback,
        )
        job = await orch.run(job_id)
        await session.commit()
        return {"id": str(job.id), "status": job.status.value, "stats": job.stats}


class _SnmpProbeFailed(Exception):
    """Control-flow: SNMP probe failed; poll log already filled."""


def _merge_snmp_candidates(
    primary: list[dict[str, Any]],
    extra: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Deduped SNMP credential bags — device links first, then global profiles."""
    seen: set[tuple[Any, ...]] = set()
    out: list[dict[str, Any]] = []
    for cand in list(primary or []) + list(extra or []):
        snmp = cand.get("snmp") or {}
        key = (
            int(snmp.get("version") or 2),
            str(snmp.get("community") or "").lower(),
            str(snmp.get("username") or ""),
        )
        if key in seen:
            continue
        seen.add(key)
        out.append(cand)
    return out


async def _probe_snmp_candidates(
    snmp: Any,
    host: str,
    candidates: list[dict[str, Any]],
    *,
    timeout: float = 3.0,
) -> tuple[dict[str, Any] | None, str | None, list[str]]:
    """Return (winning_creds, sys_descr, tried_labels) for first sysDescr hit."""
    tried: list[str] = []
    for cand in candidates:
        snmp_c = cand.get("snmp") or {}
        label = (
            f"v{snmp_c.get('version', 2)}/"
            f"{snmp_c.get('community') or snmp_c.get('username') or '?'}"
        )
        # Never log full secrets beyond community name (communities are shared secrets
        # but operators need to see which profile answered).
        tried.append(label)
        probe = await snmp.get(
            host,
            "1.3.6.1.2.1.1.1.0",
            community=snmp_c.get("community", "public"),
            version=int(snmp_c.get("version", 2)),
            timeout=timeout,
            username=snmp_c.get("username"),
            auth_key=snmp_c.get("auth_key"),
            priv_key=snmp_c.get("priv_key"),
        )
        if probe:
            return cand, str(probe)[:500], tried
    return None, None, tried


def _needs_identity_enrichment(device: Any, *, interface_count: int | None = None) -> bool:
    """True when discovery left a thin ICMP-only stub that SNMP can still fill in."""
    vendor = str(getattr(device, "vendor", "") or "").lower()
    model = str(getattr(device, "model", "") or "").lower()
    attrs = getattr(device, "attributes", None) or {}
    if attrs.get("auto_classified"):
        return True
    if vendor in {"generic", "unknown", ""} and model in {"unknown", "unknown device", ""}:
        return True
    # ICMP stub without sysDescr — try SNMP once credentials exist.
    if not attrs.get("sys_descr") and model in {"unknown", "unknown device", ""}:
        return True
    # Known device but zero interfaces → IF-MIB never landed; retry inventory.
    if interface_count is not None and interface_count == 0:
        return True
    return False


async def _enrich_device_identity(
    session: Any,
    device: Any,
    ctx: Any,
    registry: Any,
    *,
    snmp: Any,
) -> bool:
    """Re-fingerprint + inventory for thin devices; persist hostname/vendor/ifaces.

    Returns True when identity fields were updated.
    """
    from uuid import uuid4

    from netatlas.domain.entities import Interface
    from netatlas.domain.ports import CollectorContext, DeviceFingerprint
    from netatlas.domain.value_objects import DevicePlatform, DeviceStatus
    from netatlas.infrastructure.collectors.base.registry import fingerprint_platform
    from netatlas.infrastructure.persistence.repositories import SqlAlchemyInterfaceRepository

    snmp_bag = (ctx.credentials or {}).get("snmp") or {}
    sys_descr = await snmp.get(
        str(device.management_ip),
        "1.3.6.1.2.1.1.1.0",
        community=snmp_bag.get("community", "public"),
        version=int(snmp_bag.get("version", 2)),
        timeout=2.0,
        username=snmp_bag.get("username"),
        auth_key=snmp_bag.get("auth_key"),
        priv_key=snmp_bag.get("priv_key"),
    )
    if not sys_descr:
        return False
    sys_oid = await snmp.get(
        str(device.management_ip),
        "1.3.6.1.2.1.1.2.0",
        community=snmp_bag.get("community", "public"),
        version=int(snmp_bag.get("version", 2)),
        timeout=2.0,
        username=snmp_bag.get("username"),
        auth_key=snmp_bag.get("auth_key"),
        priv_key=snmp_bag.get("priv_key"),
    )
    fingerprint = DeviceFingerprint(
        management_ip=str(device.management_ip),
        sys_descr=sys_descr,
        sys_object_id=sys_oid,
    )
    plugin = registry.resolve(fingerprint)
    inventory = await plugin.collect_inventory(ctx)
    iface_list = list(getattr(inventory, "interfaces", None) or []) if inventory else []
    # Retry IF-MIB once with a longer timeout — CRS/large switches often miss the first walk.
    if inventory is not None and not iface_list:
        slow_timeouts = dict(ctx.timeouts or {})
        slow_timeouts["snmp"] = max(float(slow_timeouts.get("snmp") or 2.0), 12.0)
        slow_ctx = CollectorContext(
            target_ip=ctx.target_ip,
            credentials=ctx.credentials,
            timeouts=slow_timeouts,
            snmp_get=ctx.snmp_get,
            snmp_walk=ctx.snmp_walk,
            ssh_exec=ctx.ssh_exec,
        )
        try:
            retry_inv = await plugin.collect_inventory(slow_ctx)
            if retry_inv and (retry_inv.interfaces or []):
                inventory = retry_inv
                iface_list = list(retry_inv.interfaces or [])
        except Exception as retry_exc:  # noqa: BLE001
            logger.warning("IF-MIB retry failed device=%s: %s", device.hostname or device.id, retry_exc)

    model_s = str(getattr(inventory, "model", "") or "").lower() if inventory else ""
    thin = inventory is None or (model_s in {"unknown", ""} and not iface_list)
    if thin:
        # Still try sysName-only upgrade when SNMP answers at all.
        if inventory and inventory.hostname and inventory.hostname != str(device.management_ip):
            device.hostname = inventory.hostname
            attrs = dict(device.attributes or {})
            attrs.update(inventory.attributes or {})
            attrs["sys_descr"] = sys_descr
            attrs["sys_object_id"] = sys_oid
            attrs.pop("auto_classified", None)
            device.attributes = attrs
            return True
        return False

    device.hostname = inventory.hostname or device.hostname
    device.vendor = inventory.vendor or device.vendor
    device.model = inventory.model or device.model
    device.serial = inventory.serial or device.serial
    device.firmware = inventory.firmware or device.firmware
    device.os_version = inventory.os_version or device.os_version
    device.management_mac = inventory.management_mac or device.management_mac
    platform = inventory.platform
    if platform == DevicePlatform.UNKNOWN:
        platform = fingerprint_platform(fingerprint)
    device.platform = platform.value if hasattr(platform, "value") else str(platform)
    device.status = DeviceStatus.UP.value if hasattr(DeviceStatus.UP, "value") else "up"
    attrs = dict(device.attributes or {})
    attrs.update(inventory.attributes or {})
    attrs["sys_descr"] = sys_descr
    attrs["sys_object_id"] = sys_oid
    attrs.pop("auto_classified", None)
    attrs["enriched_from_metrics"] = True
    attrs["interface_count_enriched"] = len(iface_list)
    device.attributes = attrs

    ifaces = [
        Interface(
            id=uuid4(),
            device_id=device.id,
            name=str(i.get("name")),
            if_index=str(i["if_index"]) if i.get("if_index") is not None else None,
            description=i.get("description"),
            mac=i.get("mac") if i.get("mac") else None,
            mtu=i.get("mtu"),
            duplex=i.get("duplex"),
            speed_bps=i.get("speed_bps"),
            poe_enabled=bool(i.get("poe_enabled", False)),
            admin_status=str(i.get("admin_status") or "unknown"),
            oper_status=str(i.get("oper_status") or "unknown"),
            is_trunk=bool(i.get("is_trunk", False)),
            native_vlan=i.get("native_vlan"),
            lacp_group=i.get("lacp_group"),
            attributes={"tagged_vlans": i["tagged_vlans"]} if i.get("tagged_vlans") else {},
        )
        for i in iface_list
        if i.get("name")
    ]
    if ifaces:
        await SqlAlchemyInterfaceRepository(session).replace_for_device(device.id, ifaces)
    # Persist verified profile for next rediscovery / metrics.
    winning = (ctx.credentials or {}).get("_profile_id")
    if winning:
        attrs = dict(device.attributes or {})
        attrs["verified_credential_profile_id"] = str(winning)
        device.attributes = attrs
    return True


async def _collect_metrics() -> dict[str, Any]:
    """Poll SNMP/API metrics; also re-inventory thin Unknown Device stubs."""
    from datetime import UTC, datetime
    from uuid import uuid4

    from sqlalchemy import func, select

    from netatlas.domain.ports import CollectorContext, DeviceFingerprint
    from netatlas.infrastructure.collectors.base.registry import build_default_registry
    from netatlas.infrastructure.collectors.base.snmp_transport import SnmpTransport
    from netatlas.infrastructure.collectors.base.ssh_transport import SshTransport
    from netatlas.infrastructure.persistence.models import (
        DeviceCredentialModel,
        DeviceMetricModel,
        DeviceModel,
        InterfaceModel,
        MetricPollLogModel,
    )
    from netatlas.infrastructure.persistence.session import SessionLocal
    from netatlas.infrastructure.security.credential_resolver import (
        list_snmp_profile_ids,
        load_profile_candidates,
    )
    from netatlas.infrastructure.security.vault import AesGcmSecretVault

    snmp = SnmpTransport()
    ssh = SshTransport()
    registry = build_default_registry()
    run_id = uuid4()
    run_started = datetime.now(UTC)
    stats = {"devices": 0, "ok": 0, "errors": 0, "skipped": 0, "enriched": 0, "run_id": str(run_id)}

    async with SessionLocal() as session:
        vault = AesGcmSecretVault(get_settings().master_key_b64.get_secret_value())
        # Prefer devices with explicit credentials; also poll others with default public.
        # select(column) + scalars() already yields UUID values — do NOT access .device_id.
        linked_ids = set(
            (await session.execute(select(DeviceCredentialModel.device_id))).scalars().all()
        )
        global_snmp_ids = await list_snmp_profile_ids(session)
        global_candidates = await load_profile_candidates(
            session, vault, global_snmp_ids, default_snmp=True
        )
        iface_counts = {
            row[0]: int(row[1])
            for row in (
                await session.execute(
                    select(InterfaceModel.device_id, func.count())
                    .group_by(InterfaceModel.device_id)
                )
            ).all()
        }
        devices = (await session.execute(select(DeviceModel).order_by(DeviceModel.hostname))).scalars().all()
        for device in devices:
            started = datetime.now(UTC)
            if not device.management_ip:
                stats["skipped"] += 1
                finished = datetime.now(UTC)
                session.add(
                    MetricPollLogModel(
                        id=uuid4(),
                        run_id=run_id,
                        device_id=device.id,
                        started_at=started,
                        finished_at=finished,
                        status="skipped",
                        phase="skip",
                        message="No management IP",
                        duration_ms=int((finished - started).total_seconds() * 1000),
                        detail={"hostname": device.hostname, "reason": "no_management_ip"},
                    )
                )
                continue
            stats["devices"] += 1
            poll = MetricPollLogModel(
                id=uuid4(),
                run_id=run_id,
                device_id=device.id,
                started_at=started,
                status="ok",
                phase="collect",
                detail={
                    "hostname": device.hostname,
                    "management_ip": str(device.management_ip),
                    "platform": device.platform,
                    "credential_source": "device" if device.id in linked_ids else "global",
                },
            )
            try:
                from netatlas.infrastructure.security.credential_resolver import bind_device_credentials

                device_links: list[Any] = []
                if device.id in linked_ids:
                    device_links = list(
                        (
                            await session.execute(
                                select(DeviceCredentialModel.credential_profile_id).where(
                                    DeviceCredentialModel.device_id == device.id
                                )
                            )
                        ).scalars().all()
                    )
                    device_candidates = await load_profile_candidates(
                        session, vault, list(device_links), default_snmp=True
                    )
                else:
                    device_candidates = []
                # Always rotate through global SNMP profiles too — a wrong device-linked
                # community must not block the correct profile from Credentials page.
                candidates = _merge_snmp_candidates(device_candidates, global_candidates)
                if not candidates:
                    candidates = [{"snmp": {"community": "public", "version": 2}}]

                async def snmp_get(host: str, oid: str, **kwargs: Any) -> str | None:
                    return await snmp.get(host, oid, **kwargs)

                async def snmp_walk(host: str, oid: str, **kwargs: Any) -> list[tuple[str, str]]:
                    return await snmp.walk(host, oid, **kwargs)

                async def ssh_exec(host: str, command: str, **kwargs: Any) -> str:
                    return await ssh.exec(host, command, **kwargs)

                iface_count = iface_counts.get(device.id, 0)
                needs_enrich = _needs_identity_enrichment(device, interface_count=iface_count)
                poll.detail["needs_enrichment"] = needs_enrich
                poll.detail["interface_count_before"] = iface_count
                poll.detail["credential_source"] = "device" if device.id in linked_ids else "global"

                # ALWAYS probe — empty 20ms "partial" samples mean SNMP never answered.
                poll.phase = "probe_credentials"
                winning_creds, sys_descr_live, tried = await _probe_snmp_candidates(
                    snmp, str(device.management_ip), candidates, timeout=3.0
                )
                poll.detail["snmp_communities_tried"] = tried
                if not winning_creds or not sys_descr_live:
                    poll.status = "error"
                    poll.phase = "probe_credentials"
                    poll.message = (
                        "SNMP no response — check community, /snmp on MikroTik, "
                        "firewall UDP/161, and Credentials profiles"
                    )
                    poll.error = "sysDescr probe failed for all credential candidates"
                    poll.detail["snmp_probe"] = "no_response"
                    stats["errors"] += 1
                    raise _SnmpProbeFailed()

                poll.detail["snmp_probe"] = "ok"
                poll.detail["sys_descr"] = sys_descr_live[:240]
                # Prefer live sysDescr for vendor plugin selection (Unknown Device stubs).
                attrs = dict(device.attributes or {})
                attrs["sys_descr"] = sys_descr_live
                attrs.pop("auto_classified", None)
                device.attributes = attrs
                winning_pid = winning_creds.get("_profile_id")
                if winning_pid:
                    try:
                        await bind_device_credentials(session, device.id, [UUID(str(winning_pid))])
                        poll.detail["bound_credential_profile_id"] = str(winning_pid)
                    except Exception as bind_exc:  # noqa: BLE001
                        poll.detail["bind_error"] = str(bind_exc)[:200]

                # CRS / large IF tables need >2s; short timeouts produce empty samples.
                ctx = CollectorContext(
                    target_ip=str(device.management_ip),
                    credentials=winning_creds,
                    timeouts={"snmp": 8.0, "ssh": 15.0, "icmp": 1.0},
                    snmp_get=snmp_get,
                    snmp_walk=snmp_walk,
                    ssh_exec=ssh_exec,
                )

                enriched = False
                if needs_enrich:
                    poll.phase = "enrich"
                    try:
                        if await _enrich_device_identity(session, device, ctx, registry, snmp=snmp):
                            stats["enriched"] += 1
                            enriched = True
                            logger.info(
                                "Enriched device identity ip=%s hostname=%s vendor=%s model=%s",
                                device.management_ip,
                                device.hostname,
                                device.vendor,
                                device.model,
                            )
                    except Exception as enrich_exc:  # noqa: BLE001
                        poll.detail["enrich_error"] = str(enrich_exc)[:500]
                        logger.warning(
                            "Identity enrichment failed device=%s: %s",
                            device.hostname or device.id,
                            enrich_exc,
                        )

                poll.phase = "collect_metrics"
                plugin = registry.resolve(
                    DeviceFingerprint(
                        management_ip=str(device.management_ip),
                        sys_descr=str(
                            (device.attributes or {}).get("sys_descr")
                            or sys_descr_live
                            or device.vendor
                            or ""
                        ),
                        sys_object_id=str((device.attributes or {}).get("sys_object_id") or ""),
                    )
                )
                plugin_name = getattr(plugin, "vendor", None) or getattr(plugin, "name", None) or type(plugin).__name__
                poll.detail["plugin"] = str(plugin_name)
                sample = await plugin.collect_metrics(ctx)
                extras = dict(getattr(sample, "extras", None) or {})
                extras["snmp_alive"] = True
                extras["sys_descr"] = sys_descr_live[:240]
                if sample.interface_counters:
                    extras["interface_counters"] = sample.interface_counters
                session.add(
                    DeviceMetricModel(
                        id=uuid4(),
                        device_id=device.id,
                        cpu_percent=sample.cpu_percent,
                        memory_percent=sample.memory_percent,
                        temperature_c=sample.temperature_c,
                        extras=extras,
                    )
                )
                now = datetime.now(UTC)
                device.last_seen_at = now
                if (device.status or "").lower() in ("unknown", "down", ""):
                    device.status = "up"
                poll.metrics_written = 1
                poll.phase = "store"
                has_core = any(
                    v is not None
                    for v in (
                        sample.cpu_percent,
                        sample.memory_percent,
                        sample.temperature_c,
                        extras.get("uptime_seconds"),
                    )
                )
                has_if = int(extras.get("interfaces_total") or 0) > 0 or bool(sample.interface_counters)
                if has_core:
                    poll.status = "ok"
                    poll.message = "Metrics stored"
                    stats["ok"] += 1
                elif has_if:
                    poll.status = "partial"
                    poll.message = "Partial sample — IF counters only (no CPU/memory/uptime)"
                    stats["ok"] += 1
                else:
                    poll.status = "partial"
                    poll.message = (
                        "SNMP alive but no CPU/memory/IF metrics — "
                        "enable SNMP MIBs / health on device"
                    )
                    stats["ok"] += 1
                poll.detail.update(
                    {
                        "enriched": enriched,
                        "cpu_percent": sample.cpu_percent,
                        "memory_percent": sample.memory_percent,
                        "temperature_c": sample.temperature_c,
                        "uptime_seconds": extras.get("uptime_seconds"),
                        "interfaces_total": extras.get("interfaces_total"),
                        "interfaces_down": extras.get("interfaces_down"),
                        "if_in_errors": extras.get("if_in_errors"),
                        "if_out_errors": extras.get("if_out_errors"),
                        "if_counters": len(sample.interface_counters or []),
                        "temperature_source": extras.get("temperature_source"),
                        "cpu_source": extras.get("cpu_source"),
                        "memory_source": extras.get("memory_source"),
                        "has_core_metrics": has_core,
                    }
                )
            except _SnmpProbeFailed:
                # poll.status / message / stats["errors"] already set in probe branch
                pass
            except Exception as exc:  # noqa: BLE001
                logger.warning("Metrics failed device=%s: %s", device.hostname or device.id, exc)
                poll.status = "error"
                poll.error = str(exc)[:2000]
                poll.message = "Collection failed"
                poll.phase = poll.phase or "collect"
                stats["errors"] += 1
            finally:
                finished = datetime.now(UTC)
                poll.finished_at = finished
                poll.duration_ms = int((finished - started).total_seconds() * 1000)
                session.add(poll)

        run_finished = datetime.now(UTC)
        session.add(
            MetricPollLogModel(
                id=uuid4(),
                run_id=run_id,
                device_id=None,
                started_at=run_started,
                finished_at=run_finished,
                status="ok" if stats["errors"] == 0 else ("partial" if stats["ok"] else "error"),
                phase="sweep",
                message=f"Sweep finished: ok={stats['ok']} errors={stats['errors']} skipped={stats['skipped']}",
                metrics_written=stats["ok"],
                duration_ms=int((run_finished - run_started).total_seconds() * 1000),
                detail=dict(stats),
            )
        )
        await session.commit()
    logger.info("Metrics collection stats=%s", stats)
    return stats


async def _evaluate_triggers() -> dict[str, Any]:
    from netatlas.infrastructure.observability.dispatcher import NotificationDispatcher
    from netatlas.infrastructure.observability.trigger_engine import TriggerEngine
    from netatlas.infrastructure.persistence.session import SessionLocal

    async with SessionLocal() as session:
        settings = get_settings()
        engine = TriggerEngine(session, NotificationDispatcher(session, settings))
        stats = await engine.evaluate_all()
        await session.commit()
        logger.info("Trigger evaluation stats=%s", stats)
        return stats


async def _purge_observability() -> dict[str, Any]:
    from datetime import UTC, datetime, timedelta

    from sqlalchemy import delete

    from netatlas.infrastructure.observability.ingest import SyslogIngestService
    from netatlas.infrastructure.persistence.models import DeviceMetricModel, MetricPollLogModel
    from netatlas.infrastructure.persistence.session import SessionLocal

    async with SessionLocal() as session:
        deleted = await SyslogIngestService(session, get_settings()).purge_expired()
        now = datetime.now(UTC)
        metrics_cut = now - timedelta(days=14)
        logs_cut = now - timedelta(days=7)
        metrics_deleted = (
            await session.execute(
                delete(DeviceMetricModel).where(DeviceMetricModel.collected_at < metrics_cut)
            )
        ).rowcount or 0
        logs_deleted = (
            await session.execute(
                delete(MetricPollLogModel).where(MetricPollLogModel.started_at < logs_cut)
            )
        ).rowcount or 0
        await session.commit()
        return {
            "deleted_events": deleted,
            "deleted_metrics": int(metrics_deleted),
            "deleted_poll_logs": int(logs_deleted),
        }
