"""Kyocera printer / MFP read-only collector (SNMP Printer-MIB + Host-Resources-MIB)."""

from __future__ import annotations

from typing import Any

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
# prtMarkerSuppliesTable — walked, indexed by marker/supply unit
PRT_MARKER_SUPPLIES_DESC = "1.3.6.1.2.1.43.11.1.1.6.1"  # description (e.g. "Black Toner", "Waste Toner Box")
PRT_MARKER_SUPPLIES_LEVEL = "1.3.6.1.2.1.43.11.1.1.9.1"  # current level
PRT_MARKER_SUPPLIES_MAX = "1.3.6.1.2.1.43.11.1.1.8.1"  # max capacity
# prtInputTable — paper trays
PRT_INPUT_NAME = "1.3.6.1.2.1.43.8.2.1.18.1"
PRT_INPUT_STATUS = "1.3.6.1.2.1.43.8.2.1.11.1"  # negative values indicate warnings/errors
PRT_INPUT_CURRENT_LEVEL = "1.3.6.1.2.1.43.8.2.1.10.1"  # -2 = unknown, -3 = at-least-one-remains
# hrPrinterDetectedErrorState — bitmask (lowAlert, noPaper, jam, ... )
HR_PRINTER_DETECTED_ERROR_STATE = "1.3.6.1.2.1.25.3.5.1.2.1"
HR_PRINTER_STATUS = "1.3.6.1.2.1.25.3.5.1.1.1"
# prtMarkerLifeCount — total page/impression counter
PRT_MARKER_LIFE_COUNT = "1.3.6.1.2.1.43.10.2.1.4.1.1"

_COLOR_KEYS = {
    "black": "black_toner_percent",
    "cyan": "cyan_toner_percent",
    "magenta": "magenta_toner_percent",
    "yellow": "yellow_toner_percent",
    "waste": "waste_toner_percent",
}


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
        params = _params(ctx)
        sys_name = await ctx.snmp_get(ctx.target_ip, SNMP_SYS_NAME, **params) or ctx.target_ip
        sys_descr = await ctx.snmp_get(ctx.target_ip, SNMP_SYS_DESCR, **params) or ""
        sys_oid = await ctx.snmp_get(ctx.target_ip, SNMP_SYS_OBJECT_ID, **params)
        uptime = await ctx.snmp_get(ctx.target_ip, SNMP_SYS_UPTIME, **params)
        serial = await ctx.snmp_get(ctx.target_ip, PRT_GENERAL_SERIAL, **params)
        printer_name = await ctx.snmp_get(ctx.target_ip, PRT_GENERAL_PRINTER_NAME, **params)
        device_descr = await ctx.snmp_get(ctx.target_ip, HR_DEVICE_DESCR, **params)

        model = device_descr or printer_name or "Kyocera"
        for token in sys_descr.replace(",", " ").split():
            if token.upper().startswith(("ECOSYS", "TASKalfa", "FS-", "P", "M")) and len(token) > 2:
                model = token
                break

        printer = await _collect_printer_supplies(ctx, params)
        uptime_seconds = int(uptime) // 100 if uptime and str(uptime).isdigit() else None

        # Printers still get IF-MIB interfaces when available
        base = await snmp_inventory(ctx, vendor_hint="kyocera")
        return InventoryFacts(
            hostname=printer_name or sys_name,
            vendor="kyocera",
            model=str(model)[:128],
            serial=serial or printer.get("serial"),
            firmware=printer.get("firmware"),
            os_version=sys_descr[:255] if sys_descr else None,
            management_mac=base.management_mac,
            platform=DevicePlatform.KYOCERA,
            attributes={
                "sys_object_id": sys_oid,
                "device_class": "printer",
                "toner_percent": printer.get("black_toner_percent"),
                "printer_name": printer_name,
                "printer": printer,
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
        sample = await snmp_metrics(ctx)
        params = _params(ctx)
        printer = await _collect_printer_supplies(ctx, params)
        for key in (
            "black_toner_percent",
            "cyan_toner_percent",
            "magenta_toner_percent",
            "yellow_toner_percent",
            "waste_toner_percent",
            "total_pages",
            "paper_empty",
            "status",
        ):
            if printer.get(key) is not None:
                sample.extras[key] = printer[key]
        if printer.get("black_toner_percent") is not None:
            sample.extras["toner_percent"] = printer["black_toner_percent"]
        if printer.get("errors"):
            sample.extras["printer_errors"] = printer["errors"]
        return sample


def _params(ctx: CollectorContext) -> dict[str, Any]:
    snmp = ctx.credentials.get("snmp", {})
    return {
        "community": snmp.get("community", "public"),
        "version": int(snmp.get("version", 2)),
        "timeout": ctx.timeouts.get("snmp", 2.0),
        "username": snmp.get("username"),
        "auth_key": snmp.get("auth_key"),
        "priv_key": snmp.get("priv_key"),
    }


async def _collect_printer_supplies(ctx: CollectorContext, params: dict[str, Any]) -> dict[str, Any]:
    """Walk Printer-MIB supplies/input tables for consumables + page count + errors."""
    result: dict[str, Any] = {}
    if not ctx.snmp_walk:
        return result
    try:
        descs = dict(await ctx.snmp_walk(ctx.target_ip, PRT_MARKER_SUPPLIES_DESC, **params))
        levels = dict(await ctx.snmp_walk(ctx.target_ip, PRT_MARKER_SUPPLIES_LEVEL, **params))
        maxes = dict(await ctx.snmp_walk(ctx.target_ip, PRT_MARKER_SUPPLIES_MAX, **params))
        for oid, desc in descs.items():
            idx = oid.rsplit(".", 1)[-1]
            level = levels.get(idx)
            cap = maxes.get(idx)
            pct = None
            try:
                if level is not None and cap and float(cap) > 0:
                    pct = round(max(0.0, min(100.0, 100.0 * float(level) / float(cap))), 1)
            except (TypeError, ValueError):
                pct = None
            label = str(desc or "").strip().lower()
            for key_hint, out_key in _COLOR_KEYS.items():
                if key_hint in label:
                    result[out_key] = pct
                    break
    except Exception:  # noqa: BLE001
        pass

    try:
        total = await ctx.snmp_get(ctx.target_ip, PRT_MARKER_LIFE_COUNT, **params)
        if total and str(total).lstrip("-").isdigit():
            result["total_pages"] = int(total)
    except Exception:  # noqa: BLE001
        pass

    try:
        input_status = dict(await ctx.snmp_walk(ctx.target_ip, PRT_INPUT_STATUS, **params))
        # Negative status codes per Printer-MIB indicate warning/critical tray conditions.
        result["paper_empty"] = 1 if any(str(v).strip() not in ("", "0", "3") for v in input_status.values()) else 0
    except Exception:  # noqa: BLE001
        pass

    try:
        err_state = await ctx.snmp_get(ctx.target_ip, HR_PRINTER_DETECTED_ERROR_STATE, **params)
        errors: list[str] = []
        if err_state and str(err_state).isdigit():
            bits = int(err_state)
            # hrPrinterDetectedErrorState is a BITS/OCTET STRING; treat as bitmask best-effort.
            flags = {
                0: "lowPaper",
                1: "noPaper",
                2: "lowToner",
                3: "noToner",
                4: "doorOpen",
                5: "jammed",
                6: "offline",
                7: "serviceRequested",
            }
            for bit, label in flags.items():
                if bits & (1 << (7 - bit)):
                    errors.append(label)
        result["errors"] = errors
        status = await ctx.snmp_get(ctx.target_ip, HR_PRINTER_STATUS, **params)
        status_map = {"1": "other", "2": "unknown", "3": "idle", "4": "printing", "5": "warmup"}
        result["status"] = status_map.get(str(status), "unknown") if status else "unknown"
    except Exception:  # noqa: BLE001
        pass

    return result
