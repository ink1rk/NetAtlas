"""Eltex MES / ESR read-only collector (primary access/core switch stack)."""

from __future__ import annotations

import re

from netatlas.domain.ports import (
    ArpEntry,
    CollectorContext,
    DeviceFingerprint,
    FdbEntry,
    InventoryFacts,
    MetricsSample,
    NeighborFact,
)
from netatlas.domain.value_objects import DevicePlatform
from netatlas.infrastructure.collectors.base.snmp_inventory import (
    snmp_arp,
    snmp_fdb,
    snmp_inventory,
    snmp_metrics,
    snmp_neighbors,
)


class EltexCollector:
    vendor = "eltex"
    platforms = frozenset({"eltex"})

    def supports(self, fingerprint: DeviceFingerprint) -> bool:
        blob = " ".join(
            filter(None, [fingerprint.sys_descr, fingerprint.ssh_banner, fingerprint.sys_object_id])
        ).lower()
        return any(
            x in blob
            for x in (
                "eltex",
                "mes-",
                "mes ",
                "esr-",
                "1.3.6.1.4.1.35265",  # Eltex enterprise OID prefix
            )
        ) or bool(re.search(r"\bmes\d+", blob))

    async def collect_inventory(self, ctx: CollectorContext) -> InventoryFacts:
        facts = await snmp_inventory(ctx, vendor_hint="eltex")
        facts.platform = DevicePlatform.ELTEX
        facts.vendor = "eltex"
        if ctx.ssh_exec and ctx.credentials.get("ssh"):
            ssh = ctx.credentials["ssh"]

            async def run(cmd: str) -> str:
                return await ctx.ssh_exec(
                    ctx.target_ip,
                    cmd,
                    username=ssh.get("username", ""),
                    password=ssh.get("password"),
                    private_key=ssh.get("private_key"),
                    platform="eltex",
                    timeout=ctx.timeouts.get("ssh", 20.0),
                )

            version = await run("show version")
            if version:
                facts.attributes["show_version"] = version[:4000]
                for line in version.splitlines():
                    lower = line.lower()
                    if "software version" in lower or "version:" in lower:
                        facts.os_version = line.split(":", 1)[-1].strip()[:255]
                    if "serial" in lower and ":" in line:
                        facts.serial = line.split(":", 1)[-1].strip()
                    if "system description" in lower or "hardware" in lower:
                        model = line.split(":", 1)[-1].strip()
                        if model:
                            facts.model = model[:128]
            inventory = await run("show system")
            if inventory:
                facts.attributes["show_system"] = inventory[:4000]
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
                platform="eltex",
                timeout=ctx.timeouts.get("ssh", 20.0),
            )
            return _parse_eltex_lldp(out)
        return []

    async def collect_fdb(self, ctx: CollectorContext) -> list[FdbEntry]:
        entries = await snmp_fdb(ctx)
        if entries:
            return entries
        if ctx.ssh_exec and ctx.credentials.get("ssh"):
            ssh = ctx.credentials["ssh"]
            out = await ctx.ssh_exec(
                ctx.target_ip,
                "show mac address-table",
                username=ssh.get("username", ""),
                password=ssh.get("password"),
                private_key=ssh.get("private_key"),
                platform="eltex",
                timeout=ctx.timeouts.get("ssh", 20.0),
            )
            return _parse_mac_table(out)
        return []

    async def collect_arp(self, ctx: CollectorContext) -> list[ArpEntry]:
        return await snmp_arp(ctx)

    async def collect_metrics(self, ctx: CollectorContext) -> MetricsSample:
        return await snmp_metrics(ctx)


def _parse_eltex_lldp(text: str) -> list[NeighborFact]:
    facts: list[NeighborFact] = []
    local_if = remote_sys = remote_port = None
    for line in text.splitlines():
        lower = line.lower().strip()
        if "local port" in lower or lower.startswith("local intf") or lower.startswith("interface:"):
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
            local_if = line.split(":", 1)[-1].strip()
            remote_sys = remote_port = None
        elif "system name" in lower or "remote system" in lower:
            remote_sys = line.split(":", 1)[-1].strip()
        elif "port id" in lower or "remote port" in lower:
            remote_port = line.split(":", 1)[-1].strip()
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


def _parse_mac_table(text: str) -> list[FdbEntry]:
    entries: list[FdbEntry] = []
    mac_re = re.compile(r"([0-9a-f]{2}([-:])){5}[0-9a-f]{2}", re.I)
    for line in text.splitlines():
        m = mac_re.search(line)
        if not m:
            continue
        parts = line.split()
        iface = parts[-1] if parts else "?"
        vlan = None
        for p in parts:
            if p.isdigit() and 1 <= int(p) <= 4094:
                vlan = int(p)
                break
        entries.append(FdbEntry(mac=m.group(0).lower().replace("-", ":"), vlan_id=vlan, interface=iface))
    return entries
