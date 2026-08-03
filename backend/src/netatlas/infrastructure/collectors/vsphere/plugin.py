"""VMware vSphere / ESXi read-only collector (HTTPS API)."""

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


class VsphereCollector:
    """Supports ESXi hosts and vCenter read APIs. Never mutates VM power/config."""

    vendor = "vmware"
    platforms = frozenset({"vsphere", "esxi"})

    def supports(self, fingerprint: DeviceFingerprint) -> bool:
        blob = " ".join(
            filter(None, [fingerprint.sys_descr, fingerprint.ssh_banner, fingerprint.sys_object_id])
        ).lower()
        if fingerprint.hints.get("platform") in {"vsphere", "esxi"}:
            return True
        return any(x in blob for x in ("esxi", "vmware", "vcenter", "vsphere"))

    async def collect_inventory(self, ctx: CollectorContext) -> InventoryFacts:
        vsphere = ctx.credentials.get("vsphere") or ctx.credentials.get("esxi") or {}
        if ctx.http_get and vsphere:
            session = vsphere.get("session_id") or vsphere.get("vmware-api-session-id")
            base = (vsphere.get("base_url") or f"https://{ctx.target_ip}").rstrip("/")
            headers = {"vmware-api-session-id": session} if session else {}
            if vsphere.get("authorization"):
                headers["Authorization"] = vsphere["authorization"]
            host_summary = await self._get(ctx, f"{base}/api/vcenter/host", headers)
            vm_list = await self._get(ctx, f"{base}/api/vcenter/vm", headers)
            datastores = await self._get(ctx, f"{base}/api/vcenter/datastore", headers)
            networks = await self._get(ctx, f"{base}/api/vcenter/network", headers)
            hosts = _as_list(host_summary)
            matched = None
            for h in hosts:
                if str(h.get("name")) == ctx.target_ip or str(h.get("host")) == vsphere.get("host_id"):
                    matched = h
                    break
            if matched is None and hosts:
                matched = hosts[0]
            hostname = str((matched or {}).get("name") or ctx.target_ip)
            return InventoryFacts(
                hostname=hostname,
                vendor="vmware",
                model="ESXi" if "esxi" in hostname.lower() or vsphere.get("mode") == "esxi" else "vSphere",
                serial=None,
                firmware=None,
                os_version=None,
                management_mac=None,
                platform=DevicePlatform.VSPHERE,
                attributes={
                    "hosts": hosts,
                    "vms": _as_list(vm_list),
                    "datastores": _as_list(datastores),
                    "networks": _as_list(networks),
                    "connection_state": (matched or {}).get("connection_state"),
                    "power_state": (matched or {}).get("power_state"),
                },
                interfaces=[],
            )
        facts = await snmp_inventory(ctx, vendor_hint="vmware")
        facts.platform = DevicePlatform.VSPHERE
        facts.vendor = "vmware"
        return facts

    async def collect_neighbors(self, ctx: CollectorContext) -> list[NeighborFact]:
        return await snmp_neighbors(ctx)

    async def collect_fdb(self, ctx: CollectorContext) -> list[FdbEntry]:
        return await snmp_fdb(ctx)

    async def collect_arp(self, ctx: CollectorContext) -> list[ArpEntry]:
        return await snmp_arp(ctx)

    async def collect_metrics(self, ctx: CollectorContext) -> MetricsSample:
        return await snmp_metrics(ctx)

    async def _get(self, ctx: CollectorContext, url: str, headers: dict[str, str]) -> Any:
        assert ctx.http_get
        try:
            raw = await ctx.http_get(url, headers=headers)
            return json.loads(raw) if isinstance(raw, str) else raw
        except Exception as exc:  # noqa: BLE001
            logger.debug("vSphere GET failed url=%s err=%s", url, exc)
            return None


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, dict) and "value" in value:
        v = value["value"]
        return v if isinstance(v, list) else [v]
    return [value]
