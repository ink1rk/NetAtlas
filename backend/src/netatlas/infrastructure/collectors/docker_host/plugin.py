"""Docker host read-only collector."""
from __future__ import annotations
import json
from netatlas.domain.ports import *
from netatlas.domain.value_objects import DevicePlatform
from netatlas.infrastructure.collectors.base.snmp_inventory import snmp_arp, snmp_fdb, snmp_inventory, snmp_metrics, snmp_neighbors

class DockerHostCollector:
    vendor = "docker"
    platforms = frozenset({"docker_host"})

    def supports(self, fingerprint: DeviceFingerprint) -> bool:
        blob = " ".join(filter(None, [fingerprint.sys_descr, fingerprint.ssh_banner])).lower()
        return "docker" in blob or fingerprint.hints.get("platform") == "docker_host"

    async def collect_inventory(self, ctx: CollectorContext) -> InventoryFacts:
        docker = ctx.credentials.get("docker") or {}
        if ctx.http_get and docker.get("endpoint"):
            info = await ctx.http_get(f"{docker['endpoint']}/info")
            try:
                payload = json.loads(info) if isinstance(info, str) else info
            except Exception:
                payload = {"raw": info}
            return InventoryFacts(hostname=str(payload.get("Name") or ctx.target_ip), vendor="docker", model="docker-host", serial=None, firmware=None, os_version=str(payload.get("ServerVersion")), management_mac=None, platform=DevicePlatform.DOCKER_HOST, attributes={"info": payload}, interfaces=[])
        if ctx.ssh_exec and ctx.credentials.get("ssh"):
            ssh = ctx.credentials["ssh"]
            out = await ctx.ssh_exec(ctx.target_ip, "docker info --format '{{json .}}'", username=ssh.get("username",""), password=ssh.get("password"), private_key=ssh.get("private_key"), platform="linux", timeout=ctx.timeouts.get("ssh", 20.0))
            try:
                payload = json.loads(out or "{}")
            except Exception:
                payload = {"raw": out}
            return InventoryFacts(hostname=str(payload.get("Name") or ctx.target_ip), vendor="docker", model="docker-host", serial=None, firmware=None, os_version=str(payload.get("ServerVersion")), management_mac=None, platform=DevicePlatform.DOCKER_HOST, attributes={"info": payload}, interfaces=[])
        return await snmp_inventory(ctx, vendor_hint="docker")

    async def collect_neighbors(self, ctx: CollectorContext) -> list[NeighborFact]: return await snmp_neighbors(ctx)
    async def collect_fdb(self, ctx: CollectorContext) -> list[FdbEntry]: return await snmp_fdb(ctx)
    async def collect_arp(self, ctx: CollectorContext) -> list[ArpEntry]: return await snmp_arp(ctx)
    async def collect_metrics(self, ctx: CollectorContext) -> MetricsSample: return await snmp_metrics(ctx)
