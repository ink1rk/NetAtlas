"""Ubiquiti UniFi read-only collector (Controller / Network Application API)."""

from __future__ import annotations

import json
import logging
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
    snmp_arp,
    snmp_fdb,
    snmp_inventory,
    snmp_metrics,
    snmp_neighbors,
)

logger = logging.getLogger(__name__)


class UnifiCollector:
    """Collects UniFi gateways/switches/APs via controller API (read GET only)."""

    vendor = "ubiquiti"
    platforms = frozenset({"unifi"})

    def supports(self, fingerprint: DeviceFingerprint) -> bool:
        blob = " ".join(
            filter(None, [fingerprint.sys_descr, fingerprint.ssh_banner, fingerprint.sys_object_id])
        ).lower()
        if fingerprint.hints.get("platform") == "unifi":
            return True
        return any(x in blob for x in ("unifi", "ubiquiti", "udm", "usw", "uap", "uxg"))

    async def collect_inventory(self, ctx: CollectorContext) -> InventoryFacts:
        unifi = ctx.credentials.get("unifi") or {}
        if ctx.http_get and unifi.get("base_url"):
            device = await self._fetch_device(ctx, unifi)
            if device:
                return self._facts_from_device(device, ctx.target_ip)
        # Fallback: device may speak SNMP directly
        facts = await snmp_inventory(ctx, vendor_hint="ubiquiti")
        facts.platform = DevicePlatform.UNIFI
        facts.vendor = "ubiquiti"
        return facts

    async def collect_neighbors(self, ctx: CollectorContext) -> list[NeighborFact]:
        unifi = ctx.credentials.get("unifi") or {}
        if ctx.http_get and unifi.get("base_url"):
            device = await self._fetch_device(ctx, unifi)
            facts: list[NeighborFact] = []
            if not device:
                return await snmp_neighbors(ctx)
            for uplink in device.get("uplink") and [device["uplink"]] or []:
                facts.append(
                    NeighborFact(
                        local_interface=str(uplink.get("local_port") or uplink.get("port_idx") or "uplink"),
                        remote_hostname=uplink.get("name") or uplink.get("hostname"),
                        remote_interface=str(uplink.get("remote_port") or uplink.get("uplink_remote_port") or ""),
                        remote_chassis_id=uplink.get("mac"),
                        remote_mgmt_ip=uplink.get("ip"),
                        protocol="lldp",
                        attributes={"source": "unifi_uplink"},
                    )
                )
            for port in device.get("port_table") or []:
                if not port.get("up") or not port.get("mac_table"):
                    continue
                # Port-level LLDP-ish hints when present
                if port.get("lldp_table"):
                    for neigh in port["lldp_table"]:
                        facts.append(
                            NeighborFact(
                                local_interface=str(port.get("name") or port.get("port_idx")),
                                remote_hostname=neigh.get("chassis_id") or neigh.get("system_name"),
                                remote_interface=neigh.get("port_id"),
                                remote_chassis_id=neigh.get("chassis_id"),
                                remote_mgmt_ip=None,
                                protocol="lldp",
                            )
                        )
            return facts or await snmp_neighbors(ctx)
        return await snmp_neighbors(ctx)

    async def collect_fdb(self, ctx: CollectorContext) -> list[FdbEntry]:
        unifi = ctx.credentials.get("unifi") or {}
        if ctx.http_get and unifi.get("base_url"):
            device = await self._fetch_device(ctx, unifi)
            entries: list[FdbEntry] = []
            if device:
                for port in device.get("port_table") or []:
                    for mac_row in port.get("mac_table") or []:
                        mac = mac_row.get("mac") or mac_row.get("addr")
                        if not mac:
                            continue
                        entries.append(
                            FdbEntry(
                                mac=str(mac).lower(),
                                vlan_id=mac_row.get("vlan") or port.get("vlan"),
                                interface=str(port.get("name") or port.get("port_idx") or "?"),
                            )
                        )
            if entries:
                return entries
        return await snmp_fdb(ctx)

    async def collect_arp(self, ctx: CollectorContext) -> list[ArpEntry]:
        return await snmp_arp(ctx)

    async def collect_metrics(self, ctx: CollectorContext) -> MetricsSample:
        unifi = ctx.credentials.get("unifi") or {}
        if ctx.http_get and unifi.get("base_url"):
            device = await self._fetch_device(ctx, unifi)
            if device:
                sys_stats = device.get("sys_stats") or {}
                return MetricsSample(
                    cpu_percent=_to_float(sys_stats.get("cpu")),
                    memory_percent=_to_float(sys_stats.get("mem")),
                    temperature_c=_to_float(device.get("general_temperature")),
                )
        return await snmp_metrics(ctx)

    async def _fetch_device(self, ctx: CollectorContext, unifi: dict[str, Any]) -> dict[str, Any] | None:
        """GET device list from UniFi Network Application and match by management IP/MAC."""
        assert ctx.http_get
        base = unifi["base_url"].rstrip("/")
        site = unifi.get("site", "default")
        headers = {}
        # Prefer API key / cookie session provided already decrypted from vault.
        if unifi.get("api_key"):
            headers["X-API-KEY"] = unifi["api_key"]
        if unifi.get("cookie"):
            headers["Cookie"] = unifi["cookie"]
        if unifi.get("csrf_token"):
            headers["X-CSRF-Token"] = unifi["csrf_token"]
        url = f"{base}/proxy/network/api/s/{site}/stat/device"
        # Legacy controller path fallback handled by caller if first fails.
        try:
            raw = await ctx.http_get(url, headers=headers)
        except Exception:
            url = f"{base}/api/s/{site}/stat/device"
            try:
                raw = await ctx.http_get(url, headers=headers)
            except Exception as exc:  # noqa: BLE001
                logger.debug("UniFi API fetch failed: %s", exc)
                return None
        payload = _as_json(raw)
        devices = payload.get("data") if isinstance(payload, dict) else payload
        if not isinstance(devices, list):
            return None
        target = ctx.target_ip
        for device in devices:
            if str(device.get("ip")) == target or str(device.get("last_ip")) == target:
                return device
            for net in device.get("network_table") or []:
                if str(net.get("ip")) == target:
                    return device
        # If seed is the controller itself, return first gateway-ish device summary
        if unifi.get("match_controller"):
            return devices[0] if devices else None
        return None

    def _facts_from_device(self, device: dict[str, Any], target_ip: str) -> InventoryFacts:
        interfaces: list[dict[str, Any]] = []
        for port in device.get("port_table") or []:
            interfaces.append(
                {
                    "name": str(port.get("name") or f"port-{port.get('port_idx')}"),
                    "if_index": str(port.get("port_idx")) if port.get("port_idx") is not None else None,
                    "description": port.get("media") or port.get("port_idx_name"),
                    "mac": (port.get("mac") or device.get("mac") or "").lower() or None,
                    "mtu": None,
                    "speed_bps": int(port["speed"] * 1_000_000) if port.get("speed") else None,
                    "admin_status": "up" if port.get("enable", True) else "down",
                    "oper_status": "up" if port.get("up") else "down",
                    "duplex": "full" if port.get("full_duplex") else None,
                    "poe_enabled": bool(port.get("poe_enable")),
                    "is_trunk": bool(port.get("portconf_id") and "profile" in str(port.get("portconf_id"))),
                    "native_vlan": int(port["vlan"]) if str(port.get("vlan") or "").isdigit() else None,
                    "lacp_group": str(port.get("lag_member")) if port.get("lag_member") else None,
                }
            )
        return InventoryFacts(
            hostname=str(device.get("name") or device.get("hostname") or target_ip),
            vendor="ubiquiti",
            model=str(device.get("model") or device.get("type") or "unifi"),
            serial=device.get("serial") or device.get("device_id"),
            firmware=device.get("version") or device.get("displayable_version"),
            os_version=device.get("version"),
            management_mac=(device.get("mac") or "").lower() or None,
            platform=DevicePlatform.UNIFI,
            attributes={
                "unifi_type": device.get("type"),
                "adopted": device.get("adopted"),
                "site_id": device.get("site_id"),
            },
            interfaces=interfaces,
            cpu_percent=_to_float((device.get("sys_stats") or {}).get("cpu")),
            memory_percent=_to_float((device.get("sys_stats") or {}).get("mem")),
            temperature_c=_to_float(device.get("general_temperature")),
            uptime_seconds=int(device["uptime"]) if device.get("uptime") else None,
        )


def _as_json(raw: Any) -> Any:
    if isinstance(raw, (dict, list)):
        return raw
    try:
        return json.loads(raw or "{}")
    except json.JSONDecodeError:
        return {}


def _to_float(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None
