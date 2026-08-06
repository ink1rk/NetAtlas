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
    uptime_seconds = None
    if uptime_ticks and uptime_ticks.isdigit():
        uptime_seconds = int(uptime_ticks) // 100

    return InventoryFacts(
        hostname=sys_name,
        vendor=vendor_hint if vendor_hint != "unknown" else platform.value,
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
        entries.append(
            FdbEntry(
                mac=_normalize_mac(mac) or str(mac),
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
        ip = ".".join(parts[-4:])
        iface = parts[-5]
        entries.append(ArpEntry(ip=ip, mac=_normalize_mac(mac) or str(mac), interface=iface))
    return entries


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
        else:
            cpu = await ctx.snmp_get(ctx.target_ip, "1.3.6.1.2.1.25.3.3.1.2.1", **params)
            cpu_percent = float(cpu) if cpu else None
    except Exception:
        cpu_percent = None

    # Memory — hrStorage RAM entries (type .2.1.2)
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
        for idx, typ in types.items():
            if "2.1.2" not in str(typ) and not str(typ).endswith(".2"):
                continue
            try:
                size_u = float(sizes.get(idx) or 0)
                used_u = float(used.get(idx) or 0)
            except ValueError:
                continue
            if size_u > 0:
                memory_percent = round((used_u / size_u) * 100.0, 2)
                extras["memory_hrstorage_index"] = idx
                break
    except Exception:
        memory_percent = None

    # Uptime
    try:
        uptime_raw = await ctx.snmp_get(ctx.target_ip, SNMP_SYS_UPTIME, **params)
        if uptime_raw:
            # timeticks → seconds
            extras["uptime_seconds"] = int(float(uptime_raw) / 100.0)
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
    try:
        in_err = await ctx.snmp_walk(ctx.target_ip, "1.3.6.1.2.1.2.2.1.14", **params)
        out_err = await ctx.snmp_walk(ctx.target_ip, "1.3.6.1.2.1.2.2.1.20", **params)

        def _sum(rows: list[tuple[str, str]]) -> int:
            total = 0
            for _, v in rows:
                try:
                    total += int(float(v))
                except ValueError:
                    continue
            return total

        extras["if_in_errors"] = _sum(in_err)
        extras["if_out_errors"] = _sum(out_err)
    except Exception:
        pass

    interface_counters = await snmp_interface_counters(ctx)

    return MetricsSample(
        cpu_percent=cpu_percent,
        memory_percent=memory_percent,
        interface_counters=interface_counters,
        extras=extras,
    )


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
