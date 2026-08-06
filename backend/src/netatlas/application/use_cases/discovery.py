"""Discovery orchestration use case."""

from __future__ import annotations

import ipaddress
import json
import logging
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from netatlas.domain.entities import Device, DiscoveryJob, Interface, Link, Snapshot
from netatlas.domain.ports import (
    CollectorContext,
    DeviceFingerprint,
    DeviceRepository,
    DiscoveryJobRepository,
    DiscoverySeedRepository,
    InterfaceRepository,
    LinkRepository,
    NeighborFact,
    SnapshotRepository,
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
from netatlas.infrastructure.collectors.base.registry import CollectorRegistry, fingerprint_platform
from netatlas.infrastructure.collectors.base.snmp_transport import SnmpTransport
from netatlas.infrastructure.collectors.base.ssh_transport import SshTransport

logger = logging.getLogger(__name__)


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

        try:
            seed_ids = [UUID(x) for x in job.config.get("seed_ids", [])] if job.config.get("seed_ids") else []
            seeds = await self._seeds.get_many(seed_ids)
            targets = self._expand_targets(seeds)
            job.stats["targets"] = len(targets)
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
                    fingerprint = await self._fingerprint(target, creds)
                    plugin = self._registry.resolve(fingerprint)
                    ctx = self._build_context(target, creds, job.config)
                    inventory = await plugin.collect_inventory(ctx)
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
                    ifaces = [
                        Interface(
                            id=uuid4(),
                            device_id=device.id,
                            name=str(i.get("name")),
                            if_index=i.get("if_index"),
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
                            attributes={},
                        )
                        for i in inventory.interfaces
                        if i.get("name")
                    ]
                    await self._interfaces.replace_for_device(device.id, ifaces)
                    neighbors = await plugin.collect_neighbors(ctx)
                    if not neighbors:
                        fdb = await plugin.collect_fdb(ctx)
                        neighbors = self._neighbors_from_fdb(fdb, device_index)
                        method = DiscoveryMethod.FDB
                    else:
                        method = (
                            DiscoveryMethod.LLDP
                            if neighbors and neighbors[0].protocol == "lldp"
                            else DiscoveryMethod.CDP
                        )
                    if not neighbors:
                        arp = await plugin.collect_arp(ctx)
                        neighbors = self._neighbors_from_arp(arp, device_index)
                        method = DiscoveryMethod.ARP
                    created_links = await self._materialize_links(device, ifaces, neighbors, method)
                    job.stats["links"] = int(job.stats.get("links", 0)) + created_links
                    job.stats["inventoried"] = int(job.stats.get("inventoried", 0)) + 1
                    await self._jobs.update(job)
                    await self._emit(
                        job_id,
                        {"event": "device", "ip": target, "hostname": device.hostname, "vendor": device.vendor},
                    )
                except Exception as exc:  # noqa: BLE001
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
        except Exception as exc:  # noqa: BLE001
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

    async def _fingerprint(self, target: str, creds: dict[str, Any]) -> DeviceFingerprint:
        snmp = creds.get("snmp", {})
        sys_descr = await self._snmp.get(
            target,
            "1.3.6.1.2.1.1.1.0",
            community=snmp.get("community", "public"),
            version=int(snmp.get("version", 2)),
            timeout=2.0,
            username=snmp.get("username"),
            auth_key=snmp.get("auth_key"),
            priv_key=snmp.get("priv_key"),
        )
        sys_oid = await self._snmp.get(
            target,
            "1.3.6.1.2.1.1.2.0",
            community=snmp.get("community", "public"),
            version=int(snmp.get("version", 2)),
            timeout=2.0,
            username=snmp.get("username"),
            auth_key=snmp.get("auth_key"),
            priv_key=snmp.get("priv_key"),
        )
        return DeviceFingerprint(management_ip=target, sys_descr=sys_descr, sys_object_id=sys_oid)

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
                    vlans=[local.native_vlan] if local.native_vlan else [],
                    confidence=confidence,
                    last_confirmed_at=datetime.now(UTC),
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
