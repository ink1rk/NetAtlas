"""Ideco UTM/NGFW read-only collector (edge firewall / gateway)."""

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


class IdecoCollector:
    """Ideco exposes inventory primarily via SNMP; SSH used for read-only status dumps."""

    vendor = "ideco"
    platforms = frozenset({"ideco"})

    def supports(self, fingerprint: DeviceFingerprint) -> bool:
        blob = " ".join(
            filter(None, [fingerprint.sys_descr, fingerprint.ssh_banner, fingerprint.sys_object_id])
        ).lower()
        if fingerprint.hints.get("platform") == "ideco":
            return True
        return "ideco" in blob or "ics-utm" in blob

    async def collect_inventory(self, ctx: CollectorContext) -> InventoryFacts:
        facts = await snmp_inventory(ctx, vendor_hint="ideco")
        facts.platform = DevicePlatform.IDECO
        facts.vendor = "ideco"
        if "ideco" not in (facts.model or "").lower() and facts.os_version:
            if "ideco" in facts.os_version.lower():
                facts.model = "Ideco UTM"
        if ctx.ssh_exec and ctx.credentials.get("ssh"):
            ssh = ctx.credentials["ssh"]

            async def run(cmd: str) -> str:
                return await ctx.ssh_exec(
                    ctx.target_ip,
                    cmd,
                    username=ssh.get("username", ""),
                    password=ssh.get("password"),
                    private_key=ssh.get("private_key"),
                    platform="ideco",
                    timeout=ctx.timeouts.get("ssh", 20.0),
                )

            # Conservative read-only probes — Linux-like userland on many Ideco builds
            hostname = (await run("hostnamectl --static")).strip()
            uname = await run("uname -a")
            ip_link = await run("ip -j link")
            if hostname:
                facts.hostname = hostname
            if uname:
                facts.os_version = uname.strip()[:255]
                facts.attributes["uname"] = uname[:2000]
            if ip_link:
                facts.attributes["ip_link"] = ip_link[:8000]
        facts.attributes["role"] = "firewall"
        return facts

    async def collect_neighbors(self, ctx: CollectorContext) -> list[NeighborFact]:
        return await snmp_neighbors(ctx)

    async def collect_fdb(self, ctx: CollectorContext) -> list[FdbEntry]:
        return await snmp_fdb(ctx)

    async def collect_arp(self, ctx: CollectorContext) -> list[ArpEntry]:
        entries = await snmp_arp(ctx)
        if entries:
            return entries
        if ctx.ssh_exec and ctx.credentials.get("ssh"):
            ssh = ctx.credentials["ssh"]
            out = await ctx.ssh_exec(
                ctx.target_ip,
                "ip -j neigh",
                username=ssh.get("username", ""),
                password=ssh.get("password"),
                private_key=ssh.get("private_key"),
                platform="ideco",
                timeout=ctx.timeouts.get("ssh", 20.0),
            )
            try:
                import json

                return [
                    ArpEntry(ip=i.get("dst"), mac=i.get("lladdr") or "", interface=i.get("dev"))
                    for i in json.loads(out or "[]")
                    if i.get("dst") and i.get("lladdr")
                ]
            except Exception:
                return []
        return []

    async def collect_metrics(self, ctx: CollectorContext) -> MetricsSample:
        return await snmp_metrics(ctx)
