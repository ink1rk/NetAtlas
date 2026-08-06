"""Celery application and tasks."""

from __future__ import annotations

import asyncio
import json
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
        SqlAlchemyDeviceRepository,
        SqlAlchemyDiscoveryJobRepository,
        SqlAlchemyDiscoverySeedRepository,
        SqlAlchemyInterfaceRepository,
        SqlAlchemyLinkRepository,
        SqlAlchemySnapshotRepository,
    )
    from netatlas.infrastructure.persistence.session import SessionLocal
    from netatlas.infrastructure.security.credential_resolver import bind_device_credentials, load_profiles
    from netatlas.infrastructure.security.vault import AesGcmSecretVault

    async with SessionLocal() as session:
        vault = AesGcmSecretVault(get_settings().master_key_b64.get_secret_value())

        async def credential_loader(seeds: list[Any]) -> dict[str, Any]:
            profile_ids: list[UUID] = []
            for seed in seeds:
                profile_ids.extend(seed.credential_profile_ids)
            return await load_profiles(session, vault, profile_ids, default_snmp=True)

        async def on_device(device: Any, seeds: list[Any]) -> None:
            profile_ids: list[UUID] = []
            for seed in seeds:
                profile_ids.extend(list(seed.credential_profile_ids or []))
            # normalize to UUID
            norms: list[UUID] = []
            for pid in profile_ids:
                norms.append(pid if isinstance(pid, UUID) else UUID(str(pid)))
            await bind_device_credentials(session, device.id, norms)

        async def progress_callback(_jid: UUID, _payload: dict[str, Any]) -> None:
            # Commit mid-run so API/UI see progress and cancel flags
            await session.commit()

        orch = DiscoveryOrchestrator(
            jobs=SqlAlchemyDiscoveryJobRepository(session),
            seeds=SqlAlchemyDiscoverySeedRepository(session),
            devices=SqlAlchemyDeviceRepository(session),
            interfaces=SqlAlchemyInterfaceRepository(session),
            links=SqlAlchemyLinkRepository(session),
            snapshots=SqlAlchemySnapshotRepository(session),
            registry=build_default_registry(),
            credential_loader=credential_loader,
            progress_callback=progress_callback,
            on_device=on_device,
        )
        job = await orch.run(job_id)
        await session.commit()
        return {"id": str(job.id), "status": job.status.value, "stats": job.stats}


async def _collect_metrics() -> dict[str, Any]:
    """Poll SNMP/API metrics for devices that have credential profiles (or SNMP default)."""
    from uuid import uuid4

    from sqlalchemy import select

    from netatlas.domain.ports import CollectorContext, DeviceFingerprint
    from netatlas.infrastructure.collectors.base.registry import build_default_registry
    from netatlas.infrastructure.collectors.base.snmp_transport import SnmpTransport
    from netatlas.infrastructure.collectors.base.ssh_transport import SshTransport
    from netatlas.infrastructure.persistence.models import DeviceCredentialModel, DeviceMetricModel, DeviceModel
    from netatlas.infrastructure.persistence.session import SessionLocal
    from netatlas.infrastructure.security.credential_resolver import load_device_credentials, load_profiles
    from netatlas.infrastructure.security.vault import AesGcmSecretVault

    snmp = SnmpTransport()
    ssh = SshTransport()
    registry = build_default_registry()
    stats = {"devices": 0, "ok": 0, "errors": 0, "skipped": 0}

    async with SessionLocal() as session:
        vault = AesGcmSecretVault(get_settings().master_key_b64.get_secret_value())
        # Prefer devices with explicit credentials; also poll others with default public
        linked_ids = {
            row.device_id
            for row in (await session.execute(select(DeviceCredentialModel.device_id))).scalars().all()
        }
        devices = (await session.execute(select(DeviceModel).order_by(DeviceModel.hostname))).scalars().all()
        for device in devices:
            if not device.management_ip:
                stats["skipped"] += 1
                continue
            stats["devices"] += 1
            try:
                if device.id in linked_ids:
                    creds = await load_device_credentials(session, vault, device.id, default_snmp=False)
                else:
                    # No profile: try default community (lab/simple estates)
                    creds = await load_profiles(session, vault, [], default_snmp=True)

                async def snmp_get(host: str, oid: str, **kwargs: Any) -> str | None:
                    return await snmp.get(host, oid, **kwargs)

                async def snmp_walk(host: str, oid: str, **kwargs: Any) -> list[tuple[str, str]]:
                    return await snmp.walk(host, oid, **kwargs)

                async def ssh_exec(host: str, command: str, **kwargs: Any) -> str:
                    return await ssh.exec(host, command, **kwargs)

                ctx = CollectorContext(
                    target_ip=str(device.management_ip),
                    credentials=creds,
                    timeouts={"snmp": 2.0, "ssh": 15.0, "icmp": 1.0},
                    snmp_get=snmp_get,
                    snmp_walk=snmp_walk,
                    ssh_exec=ssh_exec,
                )
                plugin = registry.resolve(
                    DeviceFingerprint(
                        management_ip=str(device.management_ip),
                        sys_descr=str((device.attributes or {}).get("sys_descr") or device.vendor or ""),
                        sys_object_id=str((device.attributes or {}).get("sys_object_id") or ""),
                    )
                )
                sample = await plugin.collect_metrics(ctx)
                extras = dict(getattr(sample, "extras", None) or {})
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
                stats["ok"] += 1
            except Exception as exc:  # noqa: BLE001
                logger.warning("Metrics failed device=%s: %s", device.hostname or device.id, exc)
                stats["errors"] += 1
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
    from netatlas.infrastructure.observability.ingest import SyslogIngestService
    from netatlas.infrastructure.persistence.session import SessionLocal

    async with SessionLocal() as session:
        deleted = await SyslogIngestService(session, get_settings()).purge_expired()
        await session.commit()
        return {"deleted_events": deleted}
