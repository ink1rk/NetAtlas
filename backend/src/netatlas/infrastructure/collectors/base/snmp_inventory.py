"""Shared SNMP inventory helpers used by collectors."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from netatlas.domain.ports import (
    ArpEntry,
    CollectorContext,
    FdbEntry,
    InventoryFacts,
    MetricsSample,
    NeighborFact,
)
from netatlas.domain.value_objects import DevicePlatform
from netatlas.infrastructure.collectors.base.registry import fingerprint_platform

SNMP_SYS_DESCR = "1.3.6.1.2.1.1.1.0"
SNMP_SYS_OBJECT_ID = "1.3.6.1.2.1.1.2.0"
SNMP_SYS_UPTIME = "1.3.6.1.2.1.1.3.0"
SNMP_SYS_NAME = "1.3.6.1.2.1.1.5.0"
SNMP_IF_NAME = "1.3.6.1.2.1.31.1.1.1.1"
SNMP_IF_DESCR = "1.3.6.1.2.1.2.2.1.2"
SNMP_IF_MTU = "1.3.6.1.2.1.2.2.1.4"
SNMP_IF_SPEED = "1.3.6.1.2.1.2.2.1.5"
SNMP_IF_PHYS = "1.3.6.1.2.1.2.2.1.6"
SNMP_IF_ADMIN = "1.3.6.1.2.1.2.2.1.7"
SNMP_IF_OPER = "1.3.6.1.2.1.2.2.1.8"
SNMP_LLDP_REM_SYS_NAME = "1.0.8802.1.1.2.1.4.1.1.9"
SNMP_LLDP_REM_PORT_ID = "1.0.8802.1.1.2.1.4.1.1.7"
SNMP_FDB_ADDRESS = "1.3.6.1.2.1.17.4.3.1.1"
SNMP_FDB_PORT = "1.3.6.1.2.1.17.4.3.1.2"
SNMP_IP_NET_TO_MEDIA_PHYS = "1.3.6.1.2.1.4.22.1.2"
SNMP_ENTITY_SERIAL = "1.3.6.1.2.1.47.1.1.1.1.11.1"
SNMP_ENTITY_MODEL = "1.3.6.1.2.1.47.1.1.1.1.13.1"
SNMP_ENTITY_FW = "1.3.6.1.2.1.47.1.1.1.1.10.1"
SNMP_ENTITY_MODEL_TABLE = "1.3.6.1.2.1.47.1.1.1.1.13"
SNMP_ENTITY_SERIAL_TABLE = "1.3.6.1.2.1.47.1.1.1.1.11"
SNMP_ENTITY_FW_TABLE = "1.3.6.1.2.1.47.1.1.1.1.10"


SnmpGet = Callable[..., Awaitable[str | None]]
SnmpWalk = Callable[..., Awaitable[list[tuple[str, str]]]]


def _cred_snmp(ctx: CollectorContext) -> dict[str, Any]:
    snmp = ctx.credentials.get("snmp", {})
    return {
        "community": snmp.get("community", "public"),
        "version": int(snmp.get("version", 2)),
        "timeout": ctx.timeouts.get("snmp", 2.0),
        "username": snmp.get("username"),
        "auth_key": snmp.get("auth_key"),
        "priv_key": snmp.get("priv_key"),
    }


async def _first_entity_value(
    ctx: CollectorContext,
    params: dict[str, Any],
    scalar_oid: str,
    table_oid: str,
) -> str | None:
    """ENTITY-MIB index `.1` is often empty on RouterOS — walk for first non-empty."""
    assert ctx.snmp_get and ctx.snmp_walk
    value = await ctx.snmp_get(ctx.target_ip, scalar_oid, **params)
    if value:
        return value
    for _oid, val in await ctx.snmp_walk(ctx.target_ip, table_oid, **params):
        if val and str(val).strip():
            return str(val).strip()
    return None


def _model_from_sys_descr(sys_descr: str) -> str | None:
    """Best-effort model parse from sysDescr (RouterOS CRS354-..., Eltex MES…)."""
    import re

    text = (sys_descr or "").strip()
    if not text:
        return None
    # MikroTik: "RouterOS CRS354-48P-4S+2Q+" — no trailing \b (board names end with +).
    m = re.search(r"(?i)\b((?:CRS|CCR|CSS|RB|C52i)\d[\w.+-]*)", text)
    if m:
        return m.group(1)
    m = re.search(r"(?i)\b((?:MES|ESR)\d[\w+-]*)", text)
    if m:
        return m.group(1)
    return None


async def snmp_inventory(ctx: CollectorContext, *, vendor_hint: str = "unknown") -> InventoryFacts:
    assert ctx.snmp_get and ctx.snmp_walk
    params = _cred_snmp(ctx)
    sys_name = await ctx.snmp_get(ctx.target_ip, SNMP_SYS_NAME, **params) or ctx.target_ip
    sys_descr = await ctx.snmp_get(ctx.target_ip, SNMP_SYS_DESCR, **params) or ""
    sys_oid = await ctx.snmp_get(ctx.target_ip, SNMP_SYS_OBJECT_ID, **params)
    uptime_ticks = await ctx.snmp_get(ctx.target_ip, SNMP_SYS_UPTIME, **params)
    serial = await _first_entity_value(ctx, params, SNMP_ENTITY_SERIAL, SNMP_ENTITY_SERIAL_TABLE)
    model = await _first_entity_value(ctx, params, SNMP_ENTITY_MODEL, SNMP_ENTITY_MODEL_TABLE)
    firmware = await _first_entity_value(ctx, params, SNMP_ENTITY_FW, SNMP_ENTITY_FW_TABLE)
    if not model:
        model = _model_from_sys_descr(sys_descr) or "unknown"

    names = {oid.rsplit(".", 1)[-1]: val for oid, val in await ctx.snmp_walk(ctx.target_ip, SNMP_IF_NAME, **params)}
    if not names:
        # Some stacks only expose ifDescr
        names = {oid.rsplit(".", 1)[-1]: val for oid, val in await ctx.snmp_walk(ctx.target_ip, SNMP_IF_DESCR, **params)}
    descrs = {oid.rsplit(".", 1)[-1]: val for oid, val in await ctx.snmp_walk(ctx.target_ip, SNMP_IF_DESCR, **params)}
    mtus = {oid.rsplit(".", 1)[-1]: val for oid, val in await ctx.snmp_walk(ctx.target_ip, SNMP_IF_MTU, **params)}
    speeds = {oid.rsplit(".", 1)[-1]: val for oid, val in await ctx.snmp_walk(ctx.target_ip, SNMP_IF_SPEED, **params)}
    macs = {oid.rsplit(".", 1)[-1]: val for oid, val in await ctx.snmp_walk(ctx.target_ip, SNMP_IF_PHYS, **params)}
    admins = {oid.rsplit(".", 1)[-1]: val for oid, val in await ctx.snmp_walk(ctx.target_ip, SNMP_IF_ADMIN, **params)}
    opers = {oid.rsplit(".", 1)[-1]: val for oid, val in await ctx.snmp_walk(ctx.target_ip, SNMP_IF_OPER, **params)}

    interfaces: list[dict[str, Any]] = []
    for idx, name in names.items():
        if not name or not str(name).strip():
            continue
        try:
            speed = int(speeds.get(idx) or 0)
        except ValueError:
            speed = 0
        try:
            mtu = int(mtus.get(idx) or 0) or None
        except ValueError:
            mtu = None
        interfaces.append(
            {
                "name": name,
                "if_index": idx,
                "description": descrs.get(idx),
                "mac": _normalize_mac(macs.get(idx)),
                "mtu": mtu,
                "speed_bps": speed or None,
                "admin_status": _if_status(admins.get(idx)),
                "oper_status": _if_status(opers.get(idx)),
                "duplex": None,
                "poe_enabled": False,
                "is_trunk": False,
                "native_vlan": None,
                "lacp_group": None,
            }
        )

    management_mac = None
    for iface in interfaces:
        mac = iface.get("mac")
        if mac and mac != "00:00:00:00:00:00":
            management_mac = mac
            break

    from netatlas.domain.ports import DeviceFingerprint

    platform = fingerprint_platform(
        DeviceFingerprint(
            management_ip=ctx.target_ip,
            sys_descr=sys_descr,
            sys_object_id=sys_oid,
        )
    )
    uptime_seconds = parse_timeticks_seconds(uptime_ticks)

    # Prefer detected platform vendor over forced "generic" hint so inventory UI
    # shows mikrotik/eltex/… even when the Generic collector handled the host.
    if platform != DevicePlatform.UNKNOWN:
        vendor = platform.value
    elif vendor_hint and vendor_hint not in {"unknown", "generic"}:
        vendor = vendor_hint
    else:
        vendor = vendor_hint or "unknown"

    return InventoryFacts(
        hostname=sys_name,
        vendor=vendor,
        model=model,
        serial=serial,
        firmware=firmware,
        os_version=sys_descr[:255] if sys_descr else None,
        management_mac=management_mac,
        platform=platform if platform != DevicePlatform.UNKNOWN else DevicePlatform.UNKNOWN,
        attributes={"sys_object_id": sys_oid, "sys_descr": sys_descr},
        interfaces=interfaces,
        uptime_seconds=uptime_seconds,
    )


async def snmp_neighbors(ctx: CollectorContext) -> list[NeighborFact]:
    assert ctx.snmp_walk
    params = _cred_snmp(ctx)
    names = dict(await ctx.snmp_walk(ctx.target_ip, SNMP_LLDP_REM_SYS_NAME, **params))
    ports = dict(await ctx.snmp_walk(ctx.target_ip, SNMP_LLDP_REM_PORT_ID, **params))
    facts: list[NeighborFact] = []
    for oid, remote_name in names.items():
        # OID index: ...localIfIndex.remoteIndex
        parts = oid.split(".")
        local_if = parts[-2] if len(parts) >= 2 else "?"
        facts.append(
            NeighborFact(
                local_interface=local_if,
                remote_hostname=remote_name,
                remote_interface=ports.get(oid),
                remote_chassis_id=None,
                remote_mgmt_ip=None,
                protocol="lldp",
            )
        )
    return facts


async def snmp_fdb(ctx: CollectorContext) -> list[FdbEntry]:
    assert ctx.snmp_walk
    params = _cred_snmp(ctx)
    macs = dict(await ctx.snmp_walk(ctx.target_ip, SNMP_FDB_ADDRESS, **params))
    ports = dict(await ctx.snmp_walk(ctx.target_ip, SNMP_FDB_PORT, **params))
    entries: list[FdbEntry] = []
    for oid, mac in macs.items():
        normalized = _normalize_mac(mac)
        if not normalized:
            continue
        entries.append(
            FdbEntry(
                mac=normalized,
                vlan_id=None,
                interface=str(ports.get(oid) or "?"),
            )
        )
    return entries


async def snmp_arp(ctx: CollectorContext) -> list[ArpEntry]:
    assert ctx.snmp_walk
    params = _cred_snmp(ctx)
    rows = await ctx.snmp_walk(ctx.target_ip, SNMP_IP_NET_TO_MEDIA_PHYS, **params)
    entries: list[ArpEntry] = []
    for oid, mac in rows:
        # ...ipNetToMediaIfIndex.ipNetToMediaNetAddress
        parts = oid.split(".")
        if len(parts) < 5:
            continue
        normalized = _normalize_mac(mac)
        if not normalized:
            continue
        ip = ".".join(parts[-4:])
        iface = parts[-5]
        entries.append(ArpEntry(ip=ip, mac=normalized, interface=iface))
    return entries


# MikroTik enterprise health (MIKROTIK-MIB) — RouterOS often skips HOST-RESOURCES CPU table.
MIKROTIK_HL_TEMPERATURE = "1.3.6.1.4.1.14988.1.1.3.10.0"  # often 0.1 °C
MIKROTIK_HL_CPU_LOAD = "1.3.6.1.4.1.14988.1.1.3.11.0"  # percent
MIKROTIK_HL_MEMORY_USAGE = "1.3.6.1.4.1.14988.1.1.3.12.0"  # percent
MIKROTIK_HL_CPU_TEMPERATURE = "1.3.6.1.4.1.14988.1.1.3.6.0"  # often 0.1 °C


def parse_timeticks_seconds(raw: str | None) -> int | None:
    """Convert SNMPv2-MIB::sysUpTime Timeticks to seconds."""
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None
    # Common forms: "12345600", "Timeticks: (12345600) 1 day, …", "(12345600)"
    import re

    m = re.search(r"\((\d+)\)", text)
    if m:
        return int(m.group(1)) // 100
    m = re.search(r"(\d+)", text)
    if m:
        return int(m.group(1)) // 100
    try:
        return int(float(text) / 100.0)
    except ValueError:
        return None


def is_ram_hrstorage(typ: str, descr: str | None = None) -> bool:
    """HOST-RESOURCES RAM row: hrStorageRam (.2) or MikroTik 'main memory' as Other (.1)."""
    t = str(typ or "").strip()
    d = (descr or "").lower().strip()
    # hrStorageRam OID — avoid false positive on ".2.1.25" substring matches.
    if t.endswith("25.2.1.2") or t.endswith(".2.1.2") or t in {"2", "hrStorageRam"}:
        return True
    if d in {"main memory", "physical memory", "ram", "memory"}:
        return True
    if "memory" in d and not any(x in d for x in ("disk", "flash", "swap", "virtual")):
        return True
    return False


async def snmp_metrics(ctx: CollectorContext) -> MetricsSample:
    """Collect core MIB metrics for monitoring / trigger evaluation."""
    assert ctx.snmp_get and ctx.snmp_walk
    params = _cred_snmp(ctx)
    extras: dict[str, Any] = {}

    # CPU — average hrProcessorLoad
    cpu_percent: float | None = None
    try:
        cpu_rows = await ctx.snmp_walk(ctx.target_ip, "1.3.6.1.2.1.25.3.3.1.2", **params)
        loads = []
        for _, val in cpu_rows:
            try:
                loads.append(float(val))
            except ValueError:
                continue
        if loads:
            cpu_percent = sum(loads) / len(loads)
            extras["cpu_cores_sampled"] = len(loads)
            extras["cpu_source"] = "host-resources"
        else:
            cpu = await ctx.snmp_get(ctx.target_ip, "1.3.6.1.2.1.25.3.3.1.2.1", **params)
            if cpu:
                cpu_percent = float(cpu)
                extras["cpu_source"] = "host-resources.1"
    except Exception:
        cpu_percent = None

    # Memory — hrStorage RAM / MikroTik "main memory" (type Other .1.2.1.1)
    memory_percent: float | None = None
    try:
        types = {
            oid.rsplit(".", 1)[-1]: val
            for oid, val in await ctx.snmp_walk(ctx.target_ip, "1.3.6.1.2.1.25.2.3.1.2", **params)
        }
        sizes = {
            oid.rsplit(".", 1)[-1]: val
            for oid, val in await ctx.snmp_walk(ctx.target_ip, "1.3.6.1.2.1.25.2.3.1.5", **params)
        }
        used = {
            oid.rsplit(".", 1)[-1]: val
            for oid, val in await ctx.snmp_walk(ctx.target_ip, "1.3.6.1.2.1.25.2.3.1.6", **params)
        }
        descrs = {
            oid.rsplit(".", 1)[-1]: val
            for oid, val in await ctx.snmp_walk(ctx.target_ip, "1.3.6.1.2.1.25.2.3.1.3", **params)
        }
        # Prefer explicit RAM type; also accept MikroTik index 65536 / "main memory".
        for idx, typ in types.items():
            if not (is_ram_hrstorage(str(typ), descrs.get(idx)) or idx in {"65536", "2"}):
                continue
            try:
                size_u = float(sizes.get(idx) or 0)
                used_u = float(used.get(idx) or 0)
            except ValueError:
                continue
            if size_u > 0:
                memory_percent = round((used_u / size_u) * 100.0, 2)
                extras["memory_hrstorage_index"] = idx
                extras["memory_source"] = "host-resources"
                break
    except Exception:
        memory_percent = None

    # MikroTik proprietary health — fills CPU/RAM when HOST-RESOURCES is empty/wrong.
    try:
        mt_cpu = await ctx.snmp_get(ctx.target_ip, MIKROTIK_HL_CPU_LOAD, **params)
        if mt_cpu is not None and cpu_percent is None:
            val = float(mt_cpu)
            if 0 <= val <= 100:
                cpu_percent = val
                extras["cpu_source"] = "mikrotik.mtxrHlProcessorLoad"
        mt_mem = await ctx.snmp_get(ctx.target_ip, MIKROTIK_HL_MEMORY_USAGE, **params)
        if mt_mem is not None and memory_percent is None:
            val = float(mt_mem)
            if 0 <= val <= 100:
                memory_percent = val
                extras["memory_source"] = "mikrotik.mtxrHlMemoryUsage"
    except Exception:
        pass

    # Uptime
    try:
        uptime_raw = await ctx.snmp_get(ctx.target_ip, SNMP_SYS_UPTIME, **params)
        uptime_s = parse_timeticks_seconds(uptime_raw)
        if uptime_s is not None:
            extras["uptime_seconds"] = uptime_s
    except Exception:
        pass

    # IF-MIB oper status + error counters (aggregated)
    try:
        opers = await ctx.snmp_walk(ctx.target_ip, SNMP_IF_OPER, **params)
        total = len(opers)
        down = sum(1 for _, v in opers if str(v).strip() == "2")
        extras["interfaces_total"] = total
        extras["interfaces_down"] = down
    except Exception:
        pass

    def _sum_walk(rows: list[tuple[str, str]]) -> int:
        total = 0
        for _, v in rows:
            try:
                total += int(float(v))
            except ValueError:
                continue
        return total

    try:
        in_err = await ctx.snmp_walk(ctx.target_ip, "1.3.6.1.2.1.2.2.1.14", **params)
        out_err = await ctx.snmp_walk(ctx.target_ip, "1.3.6.1.2.1.2.2.1.20", **params)
        extras["if_in_errors"] = _sum_walk(in_err)
        extras["if_out_errors"] = _sum_walk(out_err)
    except Exception:
        pass
    try:
        in_disc = await ctx.snmp_walk(ctx.target_ip, "1.3.6.1.2.1.2.2.1.13", **params)
        out_disc = await ctx.snmp_walk(ctx.target_ip, "1.3.6.1.2.1.2.2.1.19", **params)
        extras["if_in_discards"] = _sum_walk(in_disc)
        extras["if_out_discards"] = _sum_walk(out_disc)
    except Exception:
        pass
    try:
        # Prefer 64-bit counters when present (switches with high traffic).
        in_oct = await ctx.snmp_walk(ctx.target_ip, "1.3.6.1.2.1.31.1.1.1.6", **params)  # ifHCInOctets
        out_oct = await ctx.snmp_walk(ctx.target_ip, "1.3.6.1.2.1.31.1.1.1.10", **params)
        if not in_oct:
            in_oct = await ctx.snmp_walk(ctx.target_ip, "1.3.6.1.2.1.2.2.1.10", **params)
            out_oct = await ctx.snmp_walk(ctx.target_ip, "1.3.6.1.2.1.2.2.1.16", **params)
        extras["if_in_octets"] = _sum_walk(in_oct)
        extras["if_out_octets"] = _sum_walk(out_oct)
    except Exception:
        pass

    temperature_c = await _snmp_temperature_c(ctx, params, extras)

    interface_counters = await snmp_interface_counters(ctx)
    if interface_counters and "if_in_octets" not in extras:
        extras["if_in_octets"] = sum(int(c.get("in_octets") or 0) for c in interface_counters)
        extras["if_out_octets"] = sum(int(c.get("out_octets") or 0) for c in interface_counters)
    if interface_counters and "if_in_discards" not in extras:
        extras["if_in_discards"] = sum(int(c.get("in_discards") or 0) for c in interface_counters)
        extras["if_out_discards"] = sum(int(c.get("out_discards") or 0) for c in interface_counters)

    return MetricsSample(
        cpu_percent=cpu_percent,
        memory_percent=memory_percent,
        temperature_c=temperature_c,
        interface_counters=interface_counters,
        extras=extras,
    )


async def _snmp_temperature_c(
    ctx: CollectorContext,
    params: dict[str, Any],
    extras: dict[str, Any],
) -> float | None:
    """Best-effort temperature: MikroTik health OIDs, then ENTITY-SENSOR-MIB (°C)."""
    assert ctx.snmp_get and ctx.snmp_walk

    # NOTE: .11.0 is CPU load (%), NOT temperature — do not use it here.
    for oid, label, tenths in (
        (MIKROTIK_HL_TEMPERATURE, "mikrotik.mtxrHlTemperature", True),
        (MIKROTIK_HL_CPU_TEMPERATURE, "mikrotik.mtxrHlCpuTemperature", True),
    ):
        try:
            raw = await ctx.snmp_get(ctx.target_ip, oid, **params)
            if not raw:
                continue
            val = float(raw)
            # RouterOS usually reports 0.1 °C units (e.g. 452 → 45.2 °C).
            if tenths and val > 120:
                val = val / 10.0
            if 0 < val < 120:
                extras["temperature_source"] = label
                return round(val, 1)
        except Exception:
            continue

    # ENTITY-SENSOR-MIB: type 8 = celsius
    try:
        types = {
            oid.rsplit(".", 1)[-1]: val
            for oid, val in await ctx.snmp_walk(ctx.target_ip, "1.3.6.1.2.1.99.1.1.1.1", **params)
        }
        scales = {
            oid.rsplit(".", 1)[-1]: val
            for oid, val in await ctx.snmp_walk(ctx.target_ip, "1.3.6.1.2.1.99.1.1.1.2", **params)
        }
        precisions = {
            oid.rsplit(".", 1)[-1]: val
            for oid, val in await ctx.snmp_walk(ctx.target_ip, "1.3.6.1.2.1.99.1.1.1.3", **params)
        }
        values = {
            oid.rsplit(".", 1)[-1]: val
            for oid, val in await ctx.snmp_walk(ctx.target_ip, "1.3.6.1.2.1.99.1.1.1.4", **params)
        }
        temps: list[float] = []
        for idx, typ in types.items():
            if str(typ).strip() not in ("8",):
                continue
            try:
                raw_v = float(values.get(idx) or 0)
            except ValueError:
                continue
            try:
                prec = int(float(precisions.get(idx) or 0))
            except ValueError:
                prec = 0
            scale = str(scales.get(idx) or "9").strip()  # 9 = units
            try:
                scale_n = int(float(scale)) if scale.replace(".", "", 1).isdigit() else 9
            except ValueError:
                scale_n = 9
            # entPhySensorScale: 9=units, 8=deci, 7=centi, 6=milli …
            scale_div = {9: 1.0, 8: 10.0, 7: 100.0, 6: 1000.0}.get(scale_n, 1.0)
            val = raw_v / (10**prec if prec > 0 else 1) / scale_div
            if 0 < val < 120:
                temps.append(val)
        if temps:
            extras["temperature_source"] = "entity-sensor"
            extras["temperature_sensors"] = len(temps)
            return round(sum(temps) / len(temps), 1)
    except Exception:
        pass
    return None


async def snmp_interface_counters(ctx: CollectorContext) -> list[dict[str, Any]]:
    """Per-interface error/discard/octet counters for Link Health scoring.

    Keyed by interface name (matches Interface.name populated at discovery time)
    so the topology/link-health API can correlate readings to a specific Link.
    """
    if not ctx.snmp_walk:
        return []
    params = _cred_snmp(ctx)
    try:
        names = {oid.rsplit(".", 1)[-1]: val for oid, val in await ctx.snmp_walk(ctx.target_ip, SNMP_IF_NAME, **params)}
        if not names:
            names = {
                oid.rsplit(".", 1)[-1]: val for oid, val in await ctx.snmp_walk(ctx.target_ip, SNMP_IF_DESCR, **params)
            }
        opers = {oid.rsplit(".", 1)[-1]: val for oid, val in await ctx.snmp_walk(ctx.target_ip, SNMP_IF_OPER, **params)}
        in_err = {oid.rsplit(".", 1)[-1]: val for oid, val in await ctx.snmp_walk(ctx.target_ip, "1.3.6.1.2.1.2.2.1.14", **params)}
        out_err = {oid.rsplit(".", 1)[-1]: val for oid, val in await ctx.snmp_walk(ctx.target_ip, "1.3.6.1.2.1.2.2.1.20", **params)}
        in_disc = {oid.rsplit(".", 1)[-1]: val for oid, val in await ctx.snmp_walk(ctx.target_ip, "1.3.6.1.2.1.2.2.1.13", **params)}
        out_disc = {oid.rsplit(".", 1)[-1]: val for oid, val in await ctx.snmp_walk(ctx.target_ip, "1.3.6.1.2.1.2.2.1.19", **params)}
        in_oct = {oid.rsplit(".", 1)[-1]: val for oid, val in await ctx.snmp_walk(ctx.target_ip, "1.3.6.1.2.1.2.2.1.10", **params)}
        out_oct = {oid.rsplit(".", 1)[-1]: val for oid, val in await ctx.snmp_walk(ctx.target_ip, "1.3.6.1.2.1.2.2.1.16", **params)}
        speeds = {oid.rsplit(".", 1)[-1]: val for oid, val in await ctx.snmp_walk(ctx.target_ip, SNMP_IF_SPEED, **params)}
    except Exception:
        return []

    def _int(v: str | None) -> int | None:
        try:
            return int(float(v)) if v is not None else None
        except ValueError:
            return None

    counters: list[dict[str, Any]] = []
    for idx, name in names.items():
        counters.append(
            {
                "if_index": idx,
                "name": name,
                "oper_status": _if_status(opers.get(idx)),
                "in_errors": _int(in_err.get(idx)) or 0,
                "out_errors": _int(out_err.get(idx)) or 0,
                "in_discards": _int(in_disc.get(idx)) or 0,
                "out_discards": _int(out_disc.get(idx)) or 0,
                "in_octets": _int(in_oct.get(idx)),
                "out_octets": _int(out_oct.get(idx)),
                "speed_bps": _int(speeds.get(idx)),
            }
        )
    return counters


def _if_status(raw: str | None) -> str:
    if raw == "1":
        return "up"
    if raw == "2":
        return "down"
    return "unknown"


def _normalize_mac(raw: str | None) -> str | None:
    if not raw:
        return None
    cleaned = raw.strip().lower().replace(" ", ":").replace("-", ":")
    cleaned = cleaned.removeprefix("0x")
    hex_only = cleaned.replace(":", "")
    if len(hex_only) == 12 and all(c in "0123456789abcdef" for c in hex_only):
        return ":".join(hex_only[i : i + 2] for i in range(0, 12, 2))
    return None
