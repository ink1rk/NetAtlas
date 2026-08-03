"""VMware ESXi read-only collector via HTTPS API."""
from __future__ import annotations
from netatlas.domain.ports import *
from netatlas.domain.value_objects import DevicePlatform
from netatlas.infrastructure.collectors.base.snmp_inventory import snmp_arp, snmp_fdb, snmp_inventory, snmp_metrics, snmp_neighbors

class EsxiCollector:
    vendor = "vmware"
    platforms = frozenset({"esxi"})

    def supports(self, fingerprint: DeviceFingerprint) -> bool:
        blob = " ".join(filter(None, [fingerprint.sys_descr, fingerprint.ssh_banner])).lower()
        return "esxi" in blob or "vmware" in blob or fingerprint.hints.get("platform") == "esxi"

    async def collect_inventory(self, ctx: CollectorContext) -> InventoryFacts:
        esxi = ctx.credentials.get("esxi") or {}
        if ctx.http_get and esxi:
            # Read-only: GET host summary
            data = await ctx.http_get(f"https://{ctx.target_ip}/api/vcenter/host", headers={"vmware-api-session-id": esxi.get("session_id","")})
            hostname = ctx.target_ip
            attrs = {"raw": data}
            return InventoryFacts(hostname=hostname, vendor="vmware", model="ESXi", serial=None, firmware=None, os_version=None, management_mac=None, platform=DevicePlatform.ESXI, attributes=attrs, interfaces=[])
        return await snmp_inventory(ctx, vendor_hint="vmware")

    async def collect_neighbors(self, ctx: CollectorContext) -> list[NeighborFact]: return await snmp_neighbors(ctx)
    async def collect_fdb(self, ctx: CollectorContext) -> list[FdbEntry]: return await snmp_fdb(ctx)
    async def collect_arp(self, ctx: CollectorContext) -> list[ArpEntry]: return await snmp_arp(ctx)
    async def collect_metrics(self, ctx: CollectorContext) -> MetricsSample: return await snmp_metrics(ctx)
