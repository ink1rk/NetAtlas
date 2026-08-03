"""Kyocera printer / MFP read-only collector (SNMP Printer-MIB)."""

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
from netatlas.domain.value_objects import DevicePlatform
from netatlas.infrastructure.collectors.base.snmp_inventory import (
    SNMP_SYS_DESCR,
    SNMP_SYS_NAME,
    SNMP_SYS_OBJECT_ID,
    SNMP_SYS_UPTIME,
    snmp_arp,
    snmp_inventory,
    snmp_metrics,
)

# Printer-MIB / Host-Resources highlights
PRT_GENERAL_SERIAL = "1.3.6.1.2.1.43.5.1.1.17.1"
PRT_GENERAL_PRINTER_NAME = "1.3.6.1.2.1.43.5.1.1.16.1"
HR_DEVICE_DESCR = "1.3.6.1.2.1.25.3.2.1.3.1"
PRT_MARKER_SUPPLIES_LEVEL = "1.3.6.1.2.1.43.11.1.1.9.1.1"
PRT_MARKER_SUPPLIES_MAX = "1.3.6.1.2.1.43.11.1.1.8.1.1"
PRT_INPUT_NAME = "1.3.6.1.2.1.43.8.2.1.18.1.1"


class KyoceraCollector:
    vendor = "kyocera"
    platforms = frozenset({"kyocera"})

    def supports(self, fingerprint: DeviceFingerprint) -> bool:
        blob = " ".join(
            filter(None, [fingerprint.sys_descr, fingerprint.ssh_banner, fingerprint.sys_object_id])
        ).lower()
        if fingerprint.hints.get("platform") == "kyocera":
            return True
        return any(
            x in blob
            for x in (
                "kyocera",
                "ecosys",
                "taskalfa",
                "fs-",
                "1.3.6.1.4.1.1347",  # Kyocera enterprise OID
            )
        )

    async def collect_inventory(self, ctx: CollectorContext) -> InventoryFacts:
        assert ctx.snmp_get
        snmp = ctx.credentials.get("snmp", {})
        params = {
            "community": snmp.get("community", "public"),
            "version": int(snmp.get("version", 2)),
            "timeout": ctx.timeouts.get("snmp", 2.0),
            "username": snmp.get("username"),
            "auth_key": snmp.get("auth_key"),
            "priv_key": snmp.get("priv_key"),
        }
        sys_name = await ctx.snmp_get(ctx.target_ip, SNMP_SYS_NAME, **params) or ctx.target_ip
        sys_descr = await ctx.snmp_get(ctx.target_ip, SNMP_SYS_DESCR, **params) or ""
        sys_oid = await ctx.snmp_get(ctx.target_ip, SNMP_SYS_OBJECT_ID, **params)
        uptime = await ctx.snmp_get(ctx.target_ip, SNMP_SYS_UPTIME, **params)
        serial = await ctx.snmp_get(ctx.target_ip, PRT_GENERAL_SERIAL, **params)
        printer_name = await ctx.snmp_get(ctx.target_ip, PRT_GENERAL_PRINTER_NAME, **params)
        device_descr = await ctx.snmp_get(ctx.target_ip, HR_DEVICE_DESCR, **params)
        toner_level = await ctx.snmp_get(ctx.target_ip, PRT_MARKER_SUPPLIES_LEVEL, **params)
        toner_max = await ctx.snmp_get(ctx.target_ip, PRT_MARKER_SUPPLIES_MAX, **params)

        model = device_descr or printer_name or "Kyocera"
        # Prefer Kyocera model token from sysDescr
        for token in sys_descr.replace(",", " ").split():
            if token.upper().startswith(("ECOSYS", "TASKalfa", "FS-", "P", "M")) and len(token) > 2:
                model = token
                break

        toner_pct = None
        try:
            if toner_level is not None and toner_max and float(toner_max) > 0:
                toner_pct = max(0.0, min(100.0, 100.0 * float(toner_level) / float(toner_max)))
        except ValueError:
            toner_pct = None

        uptime_seconds = int(uptime) // 100 if uptime and str(uptime).isdigit() else None

        # Printers still get IF-MIB interfaces when available
        base = await snmp_inventory(ctx, vendor_hint="kyocera")
        return InventoryFacts(
            hostname=printer_name or sys_name,
            vendor="kyocera",
            model=str(model)[:128],
            serial=serial,
            firmware=None,
            os_version=sys_descr[:255] if sys_descr else None,
            management_mac=base.management_mac,
            platform=DevicePlatform.KYOCERA,
            attributes={
                "sys_object_id": sys_oid,
                "device_class": "printer",
                "toner_percent": toner_pct,
                "printer_name": printer_name,
            },
            interfaces=base.interfaces,
            uptime_seconds=uptime_seconds,
        )

    async def collect_neighbors(self, ctx: CollectorContext) -> list[NeighborFact]:
        # Printers typically have no LLDP; topology comes from switch FDB/ARP.
        return []

    async def collect_fdb(self, ctx: CollectorContext) -> list[FdbEntry]:
        return []

    async def collect_arp(self, ctx: CollectorContext) -> list[ArpEntry]:
        return await snmp_arp(ctx)

    async def collect_metrics(self, ctx: CollectorContext) -> MetricsSample:
        # Toner level exposed as custom metric channel via attributes on next inventory;
        # keep host metrics best-effort.
        return await snmp_metrics(ctx)
