"""Proxmox VE read-only collector (nodes, QEMU/LXC inventory via API)."""

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


class ProxmoxCollector:
    vendor = "proxmox"
    platforms = frozenset({"proxmox"})

    def supports(self, fingerprint: DeviceFingerprint) -> bool:
        blob = " ".join(
            filter(None, [fingerprint.sys_descr, fingerprint.ssh_banner, fingerprint.sys_object_id])
        ).lower()
        if fingerprint.hints.get("platform") == "proxmox":
            return True
        return "proxmox" in blob or "pve" in blob

    async def collect_inventory(self, ctx: CollectorContext) -> InventoryFacts:
        prox = ctx.credentials.get("proxmox") or {}
        if ctx.http_get and (prox.get("base_url") or prox.get("token_id")):
            data = await self._api(ctx, prox)
            if data:
                return data
        # Proxmox nodes are Linux — SSH/SNMP fallback still useful
        if ctx.ssh_exec and ctx.credentials.get("ssh"):
            ssh = ctx.credentials["ssh"]

            async def run(cmd: str) -> str:
                return await ctx.ssh_exec(
                    ctx.target_ip,
                    cmd,
                    username=ssh.get("username", ""),
                    password=ssh.get("password"),
                    private_key=ssh.get("private_key"),
                    platform="linux",
                    timeout=ctx.timeouts.get("ssh", 20.0),
                )

            version = await run("pveversion -v")
            hostname = (await run("hostnamectl --static")).strip() or ctx.target_ip
            status = await run("pvesh get /nodes --output-format json")
            attrs: dict[str, Any] = {}
            if version:
                attrs["pveversion"] = version[:4000]
            vms: list[dict[str, Any]] = []
            try:
                nodes = json.loads(status or "[]")
                attrs["nodes"] = nodes
            except json.JSONDecodeError:
                attrs["nodes_raw"] = status[:2000]
            return InventoryFacts(
                hostname=hostname,
                vendor="proxmox",
                model="Proxmox VE",
                serial=None,
                firmware=None,
                os_version=(version.splitlines()[0] if version else None),
                management_mac=None,
                platform=DevicePlatform.PROXMOX,
                attributes={**attrs, "guests": vms},
                interfaces=[],
            )
        facts = await snmp_inventory(ctx, vendor_hint="proxmox")
        facts.platform = DevicePlatform.PROXMOX
        facts.vendor = "proxmox"
        return facts

    async def collect_neighbors(self, ctx: CollectorContext) -> list[NeighborFact]:
        return await snmp_neighbors(ctx)

    async def collect_fdb(self, ctx: CollectorContext) -> list[FdbEntry]:
        return await snmp_fdb(ctx)

    async def collect_arp(self, ctx: CollectorContext) -> list[ArpEntry]:
        return await snmp_arp(ctx)

    async def collect_metrics(self, ctx: CollectorContext) -> MetricsSample:
        prox = ctx.credentials.get("proxmox") or {}
        if ctx.http_get and prox.get("base_url"):
            node = prox.get("node") or "localhost"
            status = await self._get_json(ctx, prox, f"/api2/json/nodes/{node}/status")
            data = (status or {}).get("data") or {}
            cpu = _to_float(data.get("cpu"))
            if cpu is not None and cpu <= 1.0:
                cpu *= 100.0
            mem = None
            if data.get("memory"):
                used = _to_float(data["memory"].get("used"))
                total = _to_float(data["memory"].get("total"))
                if used is not None and total:
                    mem = 100.0 * used / total
            return MetricsSample(cpu_percent=cpu, memory_percent=mem)
        return await snmp_metrics(ctx)

    async def _api(self, ctx: CollectorContext, prox: dict[str, Any]) -> InventoryFacts | None:
        version = await self._get_json(ctx, prox, "/api2/json/version")
        nodes = await self._get_json(ctx, prox, "/api2/json/nodes")
        if not version and not nodes:
            return None
        ver_data = (version or {}).get("data") or {}
        node_rows = (nodes or {}).get("data") or []
        guests: list[dict[str, Any]] = []
        interfaces: list[dict[str, Any]] = []
        primary = prox.get("node")
        if not primary and node_rows:
            primary = node_rows[0].get("node")
        if primary:
            qemu = await self._get_json(ctx, prox, f"/api2/json/nodes/{primary}/qemu")
            lxc = await self._get_json(ctx, prox, f"/api2/json/nodes/{primary}/lxc")
            network = await self._get_json(ctx, prox, f"/api2/json/nodes/{primary}/network")
            for row in (qemu or {}).get("data") or []:
                guests.append(
                    {
                        "type": "qemu",
                        "vmid": row.get("vmid"),
                        "name": row.get("name"),
                        "status": row.get("status"),
                        "cpus": row.get("cpus"),
                        "maxmem": row.get("maxmem"),
                    }
                )
            for row in (lxc or {}).get("data") or []:
                guests.append(
                    {
                        "type": "lxc",
                        "vmid": row.get("vmid"),
                        "name": row.get("name"),
                        "status": row.get("status"),
                        "cpus": row.get("cpus"),
                        "maxmem": row.get("maxmem"),
                    }
                )
            for row in (network or {}).get("data") or []:
                interfaces.append(
                    {
                        "name": row.get("iface") or row.get("name"),
                        "if_index": None,
                        "description": row.get("type"),
                        "mac": row.get("mac") or row.get("hwaddr") or row.get("hw-address"),
                        "mtu": row.get("mtu"),
                        "speed_bps": None,
                        "admin_status": "down" if row.get("disabled") else "up",
                        "oper_status": "up" if row.get("active") else "down",
                        "duplex": None,
                        "poe_enabled": False,
                        "is_trunk": False,
                        "native_vlan": None,
                        "lacp_group": row.get("bond_mode"),
                    }
                )
        hostname = primary or ctx.target_ip
        for n in node_rows:
            if n.get("node") == primary:
                hostname = str(n.get("node"))
        return InventoryFacts(
            hostname=hostname,
            vendor="proxmox",
            model="Proxmox VE",
            serial=None,
            firmware=None,
            os_version=str(ver_data.get("version") or ver_data.get("release") or ""),
            management_mac=None,
            platform=DevicePlatform.PROXMOX,
            attributes={"guests": guests, "nodes": node_rows, "version": ver_data},
            interfaces=[i for i in interfaces if i.get("name")],
        )

    async def _get_json(
        self, ctx: CollectorContext, prox: dict[str, Any], path: str
    ) -> dict[str, Any] | None:
        assert ctx.http_get
        base = (prox.get("base_url") or f"https://{ctx.target_ip}:8006").rstrip("/")
        headers = {"Accept": "application/json"}
        token_id = prox.get("token_id")
        token_secret = prox.get("token_secret")
        if token_id and token_secret:
            headers["Authorization"] = f"PVEAPIToken={token_id}={token_secret}"
        elif prox.get("ticket"):
            headers["Cookie"] = f"PVEAuthCookie={prox['ticket']}"
            if prox.get("csrf"):
                headers["CSRFPreventionToken"] = prox["csrf"]
        try:
            raw = await ctx.http_get(f"{base}{path}", headers=headers)
            data = json.loads(raw) if isinstance(raw, str) else raw
            return data if isinstance(data, dict) else {"data": data}
        except Exception as exc:  # noqa: BLE001
            logger.debug("Proxmox API %s failed: %s", path, exc)
            return None


def _to_float(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None
