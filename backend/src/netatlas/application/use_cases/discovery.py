"""Discovery orchestration use case."""

from __future__ import annotations

import ipaddress
import logging
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from netatlas.domain.entities import Device, DiscoveryJob, Interface, Link, Snapshot
from netatlas.domain.ports import (
    ArpEntry,
    ArpRepository,
    CollectorContext,
    DeviceFingerprint,
    DeviceRepository,
    DiscoveryJobRepository,
    DiscoverySeedRepository,
    FdbEntry,
    FdbRepository,
    InterfaceRepository,
    LinkRepository,
    NeighborFact,
    NeighborRepository,
    RouteFact,
    RouteRepository,
    SnapshotRepository,
    VlanRepository,
)
from netatlas.domain.services import SnapshotChecksum
from netatlas.domain.value_objects import (
    DevicePlatform,
    DeviceStatus,
    DiscoveryMethod,
    IpNetworkVO,
    JobStatus,
)
from netatlas.infrastructure.collectors.base.icmp import icmp_probe
from netatlas.infrastructure.collectors.base.local_arp import resolve_local_mac, reverse_dns
from netatlas.infrastructure.collectors.base.oui import guess_device_type, lookup_oui
from netatlas.infrastructure.collectors.base.registry import CollectorRegistry, fingerprint_platform
from netatlas.infrastructure.collectors.base.snmp_transport import SnmpTransport
from netatlas.infrastructure.collectors.base.ssh_transport import SshTransport

logger = logging.getLogger(__name__)

# scan_mode gating — see docs/DISCOVERY_ENRICHMENT.md
_MODE_ADJACENCY = {"deep", "topology"}  # neighbors/FDB/ARP for link building
_MODE_FULL_DETAIL = {"deep"}  # VLANs, routes, interface persistence detail


_EMPTY_SNMP = (
    "",
    "none",
    "unknown",
    "nosuchobject",
    "nosuchinstance",
    "endofmibview",
    "no such object currently exists at this oid",
    "no such instance currently exists at this oid",
)


def _snmp_empty(value: Any) -> bool:
    text = str(value or "").strip().lower()
    return text in _EMPTY_SNMP or text.startswith("no such ")


def _is_generic_signal(inventory: Any) -> bool:
    """True when a collector returned essentially no usable signal (SNMP closed)."""
    vendor = str(getattr(inventory, "vendor", "") or "").lower()
    model = str(getattr(inventory, "model", "") or "").lower()
    if _snmp_empty(model):
        model = "unknown"
    named_ifaces = [
        i
        for i in (getattr(inventory, "interfaces", None) or [])
        if isinstance(i, dict) and str(i.get("name") or "").strip() and not _snmp_empty(i.get("name"))
    ]
    return vendor in {"generic", "unknown", ""} and model in {"unknown", ""} and not named_ifaces


_FIBER_HINTS = ("sfp", "fiber", "tengig", "twentyfive", "fortygig", "hundredgig", "gpon", "dwdm")
_FIBER_PREFIXES = ("te", "xe", "hu", "twe", "fo")  # Cisco-style short names for fiber uplinks (Te0/1, Xe-0/0/0, ...)
_COPPER_HINTS = ("fastethernet", "gigabitethernet", "ether", "eth", "fa0", "fa1", "gi0", "gi1")


def _guess_media(interface_name: str | None) -> str:
    """Best-effort Fiber/Copper classification from interface naming conventions.

    Real transceiver media type (when exposed via ENTITY-MIB/vendor OIDs) should
    override this heuristic — this is a sane default when it is not available.
    """
    name = (interface_name or "").lower()
    if any(h in name for h in _FIBER_HINTS):
        return "fiber"
    for prefix in _FIBER_PREFIXES:
        if name.startswith(prefix) and len(name) > len(prefix) and (name[len(prefix)].isdigit() or name[len(prefix)] in "-/"):
            return "fiber"
    if any(h in name for h in _COPPER_HINTS):
        return "copper"
    return "unknown"


class DiscoveryOrchestrator:
    """Runs a full discovery job: probe → fingerprint → inventory → adjacency → snapshot."""

    def __init__(
        self,
        *,
        jobs: DiscoveryJobRepository,
        seeds: DiscoverySeedRepository,
        devices: DeviceRepository,
        interfaces: InterfaceRepository,
        links: LinkRepository,
        snapshots: SnapshotRepository,
        registry: CollectorRegistry,
        credential_loader: Any,
        progress_callback: Any | None = None,
        on_device: Any | None = None,
        credential_candidates_loader: Any | None = None,
        neighbors: NeighborRepository | None = None,
        fdb: FdbRepository | None = None,
        arp: ArpRepository | None = None,
        vlans: VlanRepository | None = None,
        routes: RouteRepository | None = None,
    ) -> None:
        self._jobs = jobs
        self._seeds = seeds
        self._devices = devices
        self._interfaces = interfaces
        self._links = links
        self._snapshots = snapshots
        self._registry = registry
        self._credential_loader = credential_loader
        self._progress = progress_callback
        self._on_device = on_device
        # Credential Manager — rotation across candidate profiles (additive; optional)
        self._credential_candidates_loader = credential_candidates_loader
        # Discovery persistence unlock — optional writer ports (additive; optional)
        self._neighbor_repo = neighbors
        self._fdb_repo = fdb
        self._arp_repo = arp
        self._vlan_repo = vlans
        self._route_repo = routes
        self._snmp = SnmpTransport()
        self._ssh = SshTransport()

    async def _is_cancelled(self, job_id: UUID) -> bool:
        fresh = await self._jobs.get(job_id)
        if fresh is None:
            return True
        if fresh.status == JobStatus.CANCELLED:
            return True
        return bool((fresh.config or {}).get("cancelled"))

    async def run(self, job_id: UUID) -> DiscoveryJob:
        job = await self._jobs.get(job_id)
        if job is None:
            raise ValueError(f"Job not found: {job_id}")
        if job.status == JobStatus.CANCELLED or (job.config or {}).get("cancelled"):
            job.finished_at = job.finished_at or datetime.now(UTC)
            await self._jobs.update(job)
            await self._emit(job_id, {"event": "cancelled"})
            return job

        job.status = JobStatus.RUNNING
        job.started_at = datetime.now(UTC)
        job.stats = {"targets": 0, "alive": 0, "inventoried": 0, "links": 0, "errors": 0, "scanned": 0}
        await self._jobs.update(job)
        await self._emit(job_id, {"event": "started"})

        scan_mode = str((job.config or {}).get("scan_mode") or "deep").lower()
        want_adjacency = scan_mode in _MODE_ADJACENCY
        want_full_detail = scan_mode in _MODE_FULL_DETAIL

        try:
            seed_ids = [UUID(x) for x in job.config.get("seed_ids", [])] if job.config.get("seed_ids") else []
            seeds = await self._seeds.get_many(seed_ids)
            targets = self._expand_targets(seeds)
            job.stats["targets"] = len(targets)
            job.stats.setdefault("unknown_devices", 0)
            await self._jobs.update(job)
            await self._emit(job_id, {"event": "targets", "count": len(targets)})
            device_index: dict[str, Device] = {}

            for idx, target in enumerate(targets, start=1):
                if await self._is_cancelled(job_id):
                    job.status = JobStatus.CANCELLED
                    job.finished_at = datetime.now(UTC)
                    job.error = "Cancelled by operator"
                    await self._jobs.update(job)
                    await self._emit(job_id, {"event": "cancelled", "stats": job.stats})
                    return job

                job.stats["scanned"] = idx
                try:
                    alive = await icmp_probe(target, timeout=float(job.config.get("icmp_timeout", 1.0)))
                    if not alive:
                        if idx % 25 == 0:
                            await self._jobs.update(job)
                            await self._emit(job_id, {"event": "progress", "stats": job.stats})
                        continue
                    job.stats["alive"] = int(job.stats.get("alive", 0)) + 1
                    creds = await self._credential_loader(seeds)
                    candidates = (
                        await self._credential_candidates_loader(seeds)
                        if self._credential_candidates_loader
                        else None
                    )
                    fingerprint, winning_creds, verified_profile_id = await self._fingerprint(
                        target, creds, candidates
                    )
                    plugin = self._registry.resolve(fingerprint)
                    ctx = self._build_context(target, winning_creds, job.config)

                    try:
                        inventory = await plugin.collect_inventory(ctx)
                        collection_failed = _is_generic_signal(inventory)
                    except Exception:  # noqa: BLE001
                        logger.warning("Inventory collection failed ip=%s — falling back to Unknown Device", target)
                        inventory = None
                        collection_failed = True

                    if collection_failed:
                        logger.warning(
                            "No SNMP inventory for ip=%s (fingerprint=%s) — Unknown Device; "
                            "check SNMPv2 community / UDP 161 / seed credentials",
                            target,
                            bool(fingerprint.sys_descr),
                        )
                        device = await self._create_unknown_device(target, inventory)
                        job.stats["unknown_devices"] = int(job.stats.get("unknown_devices", 0)) + 1
                        device = await self._devices.upsert_by_identity(device)
                        device_index[target] = device
                        # Still bind credentials so metrics / next rediscovery can authenticate.
                        if self._on_device:
                            try:
                                await self._on_device(device, seeds)
                            except Exception:
                                logger.exception("on_device callback failed ip=%s", target)
                        job.stats["inventoried"] = int(job.stats.get("inventoried", 0)) + 1
                        await self._jobs.update(job)
                        await self._emit(
                            job_id,
                            {"event": "device", "ip": target, "hostname": device.hostname, "vendor": device.vendor},
                        )
                        continue

                    if verified_profile_id:
                        inventory.attributes = {
                            **inventory.attributes,
                            "verified_credential_profile_id": str(verified_profile_id),
                        }
                    device = Device(
                        id=uuid4(),
                        hostname=inventory.hostname,
                        vendor=inventory.vendor,
                        model=inventory.model,
                        serial=inventory.serial,
                        firmware=inventory.firmware,
                        os_version=inventory.os_version,
                        management_ip=target,
                        management_mac=inventory.management_mac,
                        platform=inventory.platform
                        if inventory.platform != DevicePlatform.UNKNOWN
                        else fingerprint_platform(fingerprint),
                        status=DeviceStatus.UP,
                        attributes=inventory.attributes,
                    )
                    device = await self._devices.upsert_by_identity(device)
                    device_index[target] = device
                    if self._on_device:
                        try:
                            await self._on_device(device, seeds)
                        except Exception:
                            logger.exception("on_device callback failed ip=%s", target)
                    ifaces = [
                        Interface(
                            id=uuid4(),
                            device_id=device.id,
                            name=str(i.get("name")),
                            if_index=str(i["if_index"]) if i.get("if_index") is not None else None,
                            description=i.get("description"),
                            mac=i.get("mac"),
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
                        for i in inventory.interfaces
                        if i.get("name")
                    ]
                    # Never wipe a previous good inventory with an empty IF-MIB walk.
                    if ifaces:
                        await self._interfaces.replace_for_device(device.id, ifaces)

                    neighbors: list[NeighborFact] = []
                    method = DiscoveryMethod.MANUAL_SEED
                    if want_adjacency:
                        fdb_entries: list[FdbEntry] = []
                        arp_entries: list[ArpEntry] = []
                        lldp_neighbors: list[NeighborFact] = []
                        try:
                            lldp_neighbors = await plugin.collect_neighbors(ctx)
                        except Exception:  # noqa: BLE001
                            logger.debug("collect_neighbors failed ip=%s", target)
                        try:
                            fdb_entries = await plugin.collect_fdb(ctx)
                        except Exception:  # noqa: BLE001
                            logger.debug("collect_fdb failed ip=%s", target)
                        try:
                            arp_entries = await plugin.collect_arp(ctx)
                        except Exception:  # noqa: BLE001
                            logger.debug("collect_arp failed ip=%s", target)

                        # Smart Discovery: FDB/ARP/LLDP are first-class inventory facts,
                        # collected and persisted for every device — not merely a
                        # neighbor-inference fallback.
                        if self._fdb_repo is not None:
                            await self._fdb_repo.replace_for_device(device.id, fdb_entries)
                        if self._arp_repo is not None:
                            await self._arp_repo.replace_for_device(device.id, arp_entries)
                        if self._neighbor_repo is not None:
                            lldp_only = [n for n in lldp_neighbors if n.protocol in ("lldp", "cdp")]
                            await self._neighbor_repo.replace_for_device(device.id, lldp_only)

                        # Link building still prefers the strongest evidence available.
                        if lldp_neighbors:
                            neighbors = lldp_neighbors
                            method = (
                                DiscoveryMethod.LLDP
                                if neighbors[0].protocol == "lldp"
                                else DiscoveryMethod.CDP
                            )
                        elif fdb_entries:
                            neighbors = self._neighbors_from_fdb(fdb_entries, device_index)
                            method = DiscoveryMethod.FDB
                        elif arp_entries:
                            neighbors = self._neighbors_from_arp(arp_entries, device_index)
                            method = DiscoveryMethod.ARP

                    if want_full_detail:
                        if self._vlan_repo is not None and inventory.vlans:
                            await self._vlan_repo.replace_for_device(device.id, inventory.vlans)
                        if self._route_repo is not None:
                            raw_routes = inventory.attributes.get("routes") or []
                            route_facts = [
                                RouteFact(
                                    destination=str(r.get("destination")),
                                    next_hop=r.get("next_hop"),
                                    interface=r.get("interface"),
                                    protocol=r.get("protocol"),
                                    metric=r.get("metric"),
                                )
                                for r in raw_routes
                                if r.get("destination")
                            ]
                            if route_facts:
                                await self._route_repo.replace_for_device(device.id, route_facts)

                    created_links = 0
                    if want_adjacency:
                        created_links = await self._materialize_links(device, ifaces, neighbors, method)
                    job.stats["links"] = int(job.stats.get("links", 0)) + created_links
                    job.stats["inventoried"] = int(job.stats.get("inventoried", 0)) + 1
                    await self._jobs.update(job)
                    await self._emit(
                        job_id,
                        {"event": "device", "ip": target, "hostname": device.hostname, "vendor": device.vendor},
                    )
                except Exception as exc:
                    logger.exception("Discovery target failed ip=%s", target)
                    job.stats["errors"] = int(job.stats.get("errors", 0)) + 1
                    await self._jobs.update(job)
                    await self._emit(job_id, {"event": "error", "ip": target, "error": str(exc)})

            if await self._is_cancelled(job_id):
                job.status = JobStatus.CANCELLED
                job.finished_at = datetime.now(UTC)
                job.error = "Cancelled by operator"
                await self._jobs.update(job)
                await self._emit(job_id, {"event": "cancelled", "stats": job.stats})
                return job

            snapshot = await self._create_snapshot(job)
            job.stats["snapshot_id"] = str(snapshot.id)
            job.status = JobStatus.COMPLETED
            job.finished_at = datetime.now(UTC)
            await self._jobs.update(job)
            await self._emit(job_id, {"event": "completed", "stats": job.stats})
            return job
        except Exception as exc:
            if await self._is_cancelled(job_id):
                job.status = JobStatus.CANCELLED
                job.error = "Cancelled by operator"
                job.finished_at = datetime.now(UTC)
                await self._jobs.update(job)
                await self._emit(job_id, {"event": "cancelled"})
                return job
            job.status = JobStatus.FAILED
            job.error = str(exc)
            job.finished_at = datetime.now(UTC)
            await self._jobs.update(job)
            await self._emit(job_id, {"event": "failed", "error": str(exc)})
            raise

    def _expand_targets(self, seeds: list[Any]) -> list[str]:
        targets: list[str] = []
        for seed in seeds:
            if not seed.enabled:
                continue
            try:
                if "/" in seed.target:
                    targets.extend(IpNetworkVO(seed.target).hosts())
                else:
                    targets.append(str(ipaddress.ip_address(seed.target)))
            except ValueError:
                logger.warning("Invalid seed target skipped: %s", seed.target)
        # Deduplicate while preserving order
        seen: set[str] = set()
        ordered: list[str] = []
        for t in targets:
            if t not in seen:
                seen.add(t)
                ordered.append(t)
        return ordered

    async def _snmp_get_pair(self, target: str, snmp: dict[str, Any]) -> tuple[str | None, str | None]:
        kwargs = {
            "community": snmp.get("community", "public"),
            "version": int(snmp.get("version", 2)),
            "timeout": 2.0,
            "username": snmp.get("username"),
            "auth_key": snmp.get("auth_key"),
            "priv_key": snmp.get("priv_key"),
        }
        sys_descr = await self._snmp.get(target, "1.3.6.1.2.1.1.1.0", **kwargs)
        sys_oid = await self._snmp.get(target, "1.3.6.1.2.1.1.2.0", **kwargs) if sys_descr else None
        return sys_descr, sys_oid

    async def _fingerprint(
        self,
        target: str,
        creds: dict[str, Any],
        candidates: list[dict[str, Any]] | None = None,
    ) -> tuple[DeviceFingerprint, dict[str, Any], str | None]:
        """Fingerprint the target, rotating through Credential Manager candidates.

        When `candidates` is provided (Credential Manager profiles attached to the
        seed, tried most-specific-first, default public community last), each SNMP
        candidate is tried until one answers; the winning profile is remembered so
        the caller can persist "used credential profile" on the device record.
        Falls back to the single merged `creds` bag when no candidates are given —
        preserves prior behavior for callers that don't opt into rotation.
        """
        if candidates:
            for cand in candidates:
                snmp = cand.get("snmp")
                if not snmp:
                    continue
                sys_descr, sys_oid = await self._snmp_get_pair(target, snmp)
                if sys_descr:
                    merged = {**creds, "snmp": snmp}
                    return (
                        DeviceFingerprint(management_ip=target, sys_descr=sys_descr, sys_object_id=sys_oid),
                        merged,
                        cand.get("_profile_id"),
                    )
            # Nothing answered — keep original merged creds for downstream SSH/API attempts.
            return DeviceFingerprint(management_ip=target), creds, None

        snmp = creds.get("snmp", {})
        sys_descr, sys_oid = await self._snmp_get_pair(target, snmp)
        return DeviceFingerprint(management_ip=target, sys_descr=sys_descr, sys_object_id=sys_oid), creds, None

    async def _create_unknown_device(self, target: str, inventory: Any | None) -> Device:
        """Smart Discovery fallback: classify by OUI/reverse-DNS when no collector could talk to the host."""
        mac = None
        if inventory is not None and getattr(inventory, "management_mac", None):
            mac = inventory.management_mac
        if not mac:
            mac = await resolve_local_mac(target)
        oui_vendor = lookup_oui(mac)
        hostname = await reverse_dns(target)
        device_class = guess_device_type(oui_vendor, hostname=hostname)
        return Device(
            id=uuid4(),
            hostname=hostname or f"unknown-{target.replace('.', '-')}",
            vendor=oui_vendor or "unknown",
            model="Unknown Device",
            serial=None,
            firmware=None,
            os_version=None,
            management_ip=target,
            management_mac=mac,
            platform=DevicePlatform.UNKNOWN,
            status=DeviceStatus.UP,
            attributes={
                "auto_classified": True,
                "detection_method": "icmp+oui",
                "oui_vendor": oui_vendor,
                "device_class": device_class,
            },
        )

    def _build_context(self, target: str, creds: dict[str, Any], config: dict[str, Any]) -> CollectorContext:
        snmp = self._snmp
        ssh = self._ssh

        async def snmp_get(host: str, oid: str, **kwargs: Any) -> str | None:
            return await snmp.get(host, oid, **kwargs)

        async def snmp_walk(host: str, oid: str, **kwargs: Any) -> list[tuple[str, str]]:
            return await snmp.walk(host, oid, **kwargs)

        async def ssh_exec(host: str, command: str, **kwargs: Any) -> str:
            return await ssh.exec(host, command, **kwargs)

        async def http_get(url: str, **kwargs: Any) -> Any:
            import httpx

            async with httpx.AsyncClient(verify=False, timeout=20.0) as client:
                resp = await client.get(url, **kwargs)
                resp.raise_for_status()
                return resp.text

        return CollectorContext(
            target_ip=target,
            credentials=creds,
            timeouts={
                "snmp": float(config.get("snmp_timeout", 2.0)),
                "ssh": float(config.get("ssh_timeout", 20.0)),
                "icmp": float(config.get("icmp_timeout", 1.0)),
            },
            snmp_get=snmp_get,
            snmp_walk=snmp_walk,
            ssh_exec=ssh_exec,
            http_get=http_get,
        )

    def _neighbors_from_fdb(
        self, fdb: list[Any], device_index: dict[str, Device]
    ) -> list[NeighborFact]:
        mac_to_device = {
            d.management_mac: d for d in device_index.values() if d.management_mac
        }
        facts: list[NeighborFact] = []
        for entry in fdb:
            remote = mac_to_device.get(entry.mac)
            if not remote:
                continue
            facts.append(
                NeighborFact(
                    local_interface=entry.interface,
                    remote_hostname=remote.hostname,
                    remote_interface=None,
                    remote_chassis_id=entry.mac,
                    remote_mgmt_ip=remote.management_ip,
                    protocol="fdb",
                )
            )
        return facts

    def _neighbors_from_arp(
        self, arp: list[Any], device_index: dict[str, Device]
    ) -> list[NeighborFact]:
        facts: list[NeighborFact] = []
        for entry in arp:
            remote = device_index.get(entry.ip)
            if not remote:
                continue
            facts.append(
                NeighborFact(
                    local_interface=entry.interface or "unknown",
                    remote_hostname=remote.hostname,
                    remote_interface=None,
                    remote_chassis_id=entry.mac,
                    remote_mgmt_ip=entry.ip,
                    protocol="arp",
                )
            )
        return facts

    async def _materialize_links(
        self,
        device: Device,
        ifaces: list[Interface],
        neighbors: list[NeighborFact],
        method: DiscoveryMethod,
    ) -> int:
        by_name = {i.name: i for i in ifaces}
        by_index = {i.if_index: i for i in ifaces if i.if_index}
        count = 0
        for neigh in neighbors:
            local = by_name.get(neigh.local_interface) or by_index.get(neigh.local_interface)
            if local is None:
                continue
            # Ensure remote device exists as a stub if we only know hostname/ip
            remote_ip = neigh.remote_mgmt_ip
            remote_device = None
            if remote_ip:
                remote_device = await self._devices.upsert_by_identity(
                    Device(
                        id=uuid4(),
                        hostname=neigh.remote_hostname or remote_ip,
                        vendor="unknown",
                        model="unknown",
                        serial=None,
                        firmware=None,
                        os_version=None,
                        management_ip=remote_ip,
                        management_mac=None,
                        platform=DevicePlatform.UNKNOWN,
                        status=DeviceStatus.UNKNOWN,
                    )
                )
            if remote_device is None:
                continue
            remote_ifaces = await self._interfaces.list_for_device(remote_device.id)
            remote_iface = None
            if neigh.remote_interface:
                remote_iface = next((i for i in remote_ifaces if i.name == neigh.remote_interface), None)
            if remote_iface is None:
                remote_iface = Interface(
                    id=uuid4(),
                    device_id=remote_device.id,
                    name=neigh.remote_interface or "unknown",
                    if_index=None,
                    description="auto-created from discovery",
                    mac=None,
                    mtu=None,
                    duplex=None,
                    speed_bps=local.speed_bps,
                    poe_enabled=False,
                    admin_status="unknown",
                    oper_status="unknown",
                    is_trunk=False,
                    native_vlan=None,
                    lacp_group=None,
                )
                await self._interfaces.replace_for_device(
                    remote_device.id, [*remote_ifaces, remote_iface]
                )
            confidence = 1.0 if method in (DiscoveryMethod.LLDP, DiscoveryMethod.CDP) else 0.6 if method == DiscoveryMethod.FDB else 0.4
            tagged = list((local.attributes or {}).get("tagged_vlans") or [])
            all_vlans = ([local.native_vlan] if local.native_vlan else []) + [v for v in tagged if v not in ([local.native_vlan] if local.native_vlan else [])]
            local_oper = (local.oper_status or "unknown").lower()
            remote_oper = (remote_iface.oper_status or "unknown").lower()
            link_status = "up" if local_oper == "up" and remote_oper == "up" else (
                "down" if local_oper == "down" or remote_oper == "down" else "unknown"
            )
            await self._links.upsert(
                Link(
                    id=uuid4(),
                    interface_a_id=local.id,
                    interface_b_id=remote_iface.id,
                    discovery_method=method,
                    speed_bps=local.speed_bps,
                    is_lacp=bool(local.lacp_group),
                    lacp_key=local.lacp_group,
                    is_trunk=local.is_trunk,
                    vlans=all_vlans,
                    confidence=confidence,
                    last_confirmed_at=datetime.now(UTC),
                    media=_guess_media(local.name),
                    link_status=link_status,
                )
            )
            count += 1
        return count

    async def _create_snapshot(self, job: DiscoveryJob) -> Snapshot:
        devices, _ = await self._devices.list(page=1, page_size=10000)
        links = await self._links.list_all()
        payload: dict[str, Any] = {
            "devices": [
                {
                    "id": str(d.id),
                    "hostname": d.hostname,
                    "vendor": d.vendor,
                    "model": d.model,
                    "serial": d.serial,
                    "firmware": d.firmware,
                    "management_ip": d.management_ip,
                    "platform": d.platform.value,
                    "status": d.status.value,
                }
                for d in devices
            ],
            "links": [
                {
                    "id": str(link.id),
                    "interface_a": str(link.interface_a_id),
                    "interface_b": str(link.interface_b_id),
                    "method": link.discovery_method.value,
                    "speed_bps": link.speed_bps,
                    "confidence": link.confidence,
                }
                for link in links
            ],
            "vlans": [],
            "interfaces": [],
            "arp": [],
            "fdb": [],
            "routes": [],
        }
        # Enrich interfaces
        for d in devices:
            ifaces = await self._interfaces.list_for_device(d.id)
            for i in ifaces:
                payload["interfaces"].append(
                    {
                        "device": d.hostname,
                        "name": i.name,
                        "oper_status": i.oper_status,
                        "speed_bps": i.speed_bps,
                        "mac": i.mac,
                    }
                )
        checksum = SnapshotChecksum.compute(payload)
        snapshot = Snapshot(
            id=uuid4(),
            discovery_job_id=job.id,
            label=f"discovery-{job.id}",
            created_at=datetime.now(UTC),
            checksum=checksum,
            summary={
                "devices": len(payload["devices"]),
                "links": len(payload["links"]),
                "interfaces": len(payload["interfaces"]),
            },
            payload=payload,
        )
        return await self._snapshots.add(snapshot)

    async def _emit(self, job_id: UUID, payload: dict[str, Any]) -> None:
        if self._progress:
            await self._progress(job_id, payload)
