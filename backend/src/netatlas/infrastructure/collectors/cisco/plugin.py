"""Cisco IOS read-only collector."""

from __future__ import annotations

from netatlas.domain.ports import (
    ArpEntry,
    CollectorContext,
    DeviceFingerprint,
    FdbEntry,
    InventoryFacts,
    MetricsSample,
    NeighborFact,
)
from netatlas.infrastructure.collectors.base.snmp_inventory import (
    snmp_arp,
    snmp_fdb,
    snmp_inventory,
    snmp_metrics,
    snmp_neighbors,
)


class CiscoIosCollector:
    vendor = "cisco"
    platforms = frozenset({"cisco_ios"})

    def supports(self, fingerprint: DeviceFingerprint) -> bool:
        blob = " ".join(filter(None, [fingerprint.sys_descr, fingerprint.ssh_banner, fingerprint.sys_object_id])).lower()
        return any(x in blob for x in ("cisco", "ios-xe", "catalyst", "nx-os", "1.3.6.1.4.1.9"))

    async def collect_inventory(self, ctx: CollectorContext) -> InventoryFacts:
        facts = await snmp_inventory(ctx, vendor_hint="cisco")
        if ctx.ssh_exec and ctx.credentials.get("ssh"):
            ssh = ctx.credentials["ssh"]
            version = await ctx.ssh_exec(
                ctx.target_ip,
                "show version",
                username=ssh.get("username", ""),
                password=ssh.get("password"),
                private_key=ssh.get("private_key"),
                platform="cisco_ios",
                timeout=ctx.timeouts.get("ssh", 20.0),
            )
            if version:
                facts.attributes["show_version"] = version[:4000]
                for line in version.splitlines():
                    if "Cisco IOS" in line or "Cisco IOS XE" in line:
                        facts.os_version = line.strip()[:255]
                    if line.lower().startswith("processor board id"):
                        facts.serial = line.split()[-1]
        return facts

    async def collect_neighbors(self, ctx: CollectorContext) -> list[NeighborFact]:
        neighbors = await snmp_neighbors(ctx)
        if neighbors:
            return neighbors
        if ctx.ssh_exec and ctx.credentials.get("ssh"):
            ssh = ctx.credentials["ssh"]
            out = await ctx.ssh_exec(
                ctx.target_ip,
                "show lldp neighbors detail",
                username=ssh.get("username", ""),
                password=ssh.get("password"),
                private_key=ssh.get("private_key"),
                platform="cisco_ios",
                timeout=ctx.timeouts.get("ssh", 20.0),
            )
            return _parse_cisco_lldp(out)
        return []

    async def collect_fdb(self, ctx: CollectorContext) -> list[FdbEntry]:
        return await snmp_fdb(ctx)

    async def collect_arp(self, ctx: CollectorContext) -> list[ArpEntry]:
        return await snmp_arp(ctx)

    async def collect_metrics(self, ctx: CollectorContext) -> MetricsSample:
        return await snmp_metrics(ctx)


def _parse_cisco_lldp(text: str) -> list[NeighborFact]:
    facts: list[NeighborFact] = []
    local_if = remote_sys = remote_port = None
    for line in text.splitlines():
        lower = line.lower().strip()
        if lower.startswith("local intf:"):
            if local_if and remote_sys:
                facts.append(
                    NeighborFact(
                        local_interface=local_if,
                        remote_hostname=remote_sys,
                        remote_interface=remote_port,
                        remote_chassis_id=None,
                        remote_mgmt_ip=None,
                        protocol="lldp",
                    )
                )
            local_if = line.split(":", 1)[1].strip()
            remote_sys = remote_port = None
        elif lower.startswith("system name:"):
            remote_sys = line.split(":", 1)[1].strip()
        elif lower.startswith("port id:"):
            remote_port = line.split(":", 1)[1].strip()
    if local_if and remote_sys:
        facts.append(
            NeighborFact(
                local_interface=local_if,
                remote_hostname=remote_sys,
                remote_interface=remote_port,
                remote_chassis_id=None,
                remote_mgmt_ip=None,
                protocol="lldp",
            )
        )
    return facts
