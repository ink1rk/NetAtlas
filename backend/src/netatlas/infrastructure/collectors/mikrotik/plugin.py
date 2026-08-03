"""Mikrotik RouterOS read-only collector."""
from __future__ import annotations
from netatlas.domain.ports import *
from netatlas.infrastructure.collectors.base.snmp_inventory import snmp_arp, snmp_fdb, snmp_inventory, snmp_metrics, snmp_neighbors

class MikrotikCollector:
    vendor = "mikrotik"
    platforms = frozenset({"mikrotik"})

    def supports(self, fingerprint: DeviceFingerprint) -> bool:
        blob = " ".join(filter(None, [fingerprint.sys_descr, fingerprint.ssh_banner])).lower()
        return "mikrotik" in blob or "routeros" in blob

    async def collect_inventory(self, ctx: CollectorContext) -> InventoryFacts:
        facts = await snmp_inventory(ctx, vendor_hint="mikrotik")
        if ctx.ssh_exec and ctx.credentials.get("ssh"):
            ssh = ctx.credentials["ssh"]
            out = await ctx.ssh_exec(ctx.target_ip, "/system resource print", username=ssh.get("username",""), password=ssh.get("password"), private_key=ssh.get("private_key"), platform="mikrotik", timeout=ctx.timeouts.get("ssh", 20.0))
            if out:
                facts.attributes["resource_print"] = out[:4000]
        return facts

    async def collect_neighbors(self, ctx: CollectorContext) -> list[NeighborFact]:
        neighbors = await snmp_neighbors(ctx)
        if neighbors: return neighbors
        if ctx.ssh_exec and ctx.credentials.get("ssh"):
            ssh = ctx.credentials["ssh"]
            out = await ctx.ssh_exec(ctx.target_ip, "/ip neighbor print detail", username=ssh.get("username",""), password=ssh.get("password"), private_key=ssh.get("private_key"), platform="mikrotik", timeout=ctx.timeouts.get("ssh", 20.0))
            facts=[]
            for block in out.split("\n\n"):
                host=iface=local=None
                for line in block.splitlines():
                    if "identity=" in line: host=line.split("identity=",1)[1].split()[0].strip('"')
                    if "interface=" in line: local=line.split("interface=",1)[1].split()[0].strip('"')
                    if "interface-name=" in line: iface=line.split("interface-name=",1)[1].split()[0].strip('"')
                if local and host:
                    facts.append(NeighborFact(local_interface=local, remote_hostname=host, remote_interface=iface, remote_chassis_id=None, remote_mgmt_ip=None, protocol="lldp"))
            return facts
        return []

    async def collect_fdb(self, ctx: CollectorContext) -> list[FdbEntry]: return await snmp_fdb(ctx)
    async def collect_arp(self, ctx: CollectorContext) -> list[ArpEntry]: return await snmp_arp(ctx)
    async def collect_metrics(self, ctx: CollectorContext) -> MetricsSample: return await snmp_metrics(ctx)
