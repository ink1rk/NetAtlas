"""Device intelligence: role detection, MAC trace, hierarchical layout ranks."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


NETWORK_ROLES = (
    "core",
    "distribution",
    "access",
    "firewall",
    "router",
    "server",
    "storage",
    "wireless",
    "unknown",
)

# Layout tiers for hierarchical topology (top → bottom)
ROLE_LAYOUT_RANK: dict[str, int] = {
    "firewall": 0,
    "router": 1,
    "core": 2,
    "distribution": 3,
    "access": 4,
    "wireless": 5,
    "server": 6,
    "storage": 6,
    "unknown": 5,
}


@dataclass(slots=True)
class RoleDetectionResult:
    role: str
    confidence: float
    reasons: list[str] = field(default_factory=list)
    signals: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "role": self.role,
            "confidence": round(self.confidence, 1),
            "reasons": self.reasons,
            "signals": self.signals,
        }


class RoleDetector:
    """Heuristic network-role classifier from inventory/topology signals."""

    def detect(
        self,
        *,
        device: dict[str, Any],
        interfaces: list[dict[str, Any]] | None = None,
        neighbor_count: int = 0,
        vlan_count: int = 0,
        fdb_count: int = 0,
        link_stats: dict[str, Any] | None = None,
    ) -> RoleDetectionResult:
        interfaces = interfaces or []
        link_stats = link_stats or {}
        attrs = device.get("attributes") or {}
        platform = str(device.get("platform") or "").lower()
        vendor = str(device.get("vendor") or "").lower()
        model = str(device.get("model") or "").lower()
        hostname = str(device.get("hostname") or "").lower()
        combined = f"{platform} {vendor} {model} {hostname}"

        trunk_count = sum(1 for i in interfaces if i.get("is_trunk"))
        access_ports = sum(1 for i in interfaces if not i.get("is_trunk") and i.get("oper_status") == "up")
        high_speed = sum(1 for i in interfaces if (i.get("speed_bps") or 0) >= 10_000_000_000)
        uplinkish = sum(
            1
            for i in interfaces
            if (i.get("speed_bps") or 0) >= 1_000_000_000 and (i.get("is_trunk") or "uplink" in str(i.get("description") or "").lower())
        )
        iface_count = len(interfaces)
        vlan_hint = vlan_count or len(
            {i.get("native_vlan") for i in interfaces if i.get("native_vlan") is not None}
        )
        trunk_links = int(link_stats.get("trunk_links") or 0)
        total_links = int(link_stats.get("links") or neighbor_count)

        scores: dict[str, float] = {r: 0.0 for r in NETWORK_ROLES}
        reasons: dict[str, list[str]] = {r: [] for r in NETWORK_ROLES}

        def bump(role: str, points: float, reason: str) -> None:
            scores[role] += points
            reasons[role].append(reason)

        # Explicit attribute hints from collectors
        explicit = str(attrs.get("role") or attrs.get("network_role") or "").lower()
        if explicit in scores:
            bump(explicit, 80, f"Collector attribute role={explicit}")
        device_class = str(attrs.get("device_class") or "").lower()
        if device_class == "printer":
            bump("unknown", 40, "Device class printer")
        if "firewall" in combined or "ideco" in combined or "utm" in combined:
            bump("firewall", 70, "Platform/vendor indicates firewall/UTM")
        if any(x in combined for x in ("proxmox", "vsphere", "esxi", "hypervisor")):
            bump("server", 65, "Hypervisor platform")
        if any(x in combined for x in ("storage", "nas", "san")):
            bump("storage", 60, "Storage platform hint")
        if any(x in combined for x in ("unifi", "uap", "wifi", "wireless", "ap-")):
            bump("wireless", 55, "Wireless AP hint")
        if any(x in combined for x in ("router", "esr", "mikrotik", "gateway")):
            bump("router", 35, "Router platform hint")
        if any(x in combined for x in ("mes", "switch", "eltex")):
            bump("access", 20, "Switch platform baseline")

        # Topology fan-out
        if neighbor_count >= 12 or total_links >= 12:
            bump("core", 35, f"{max(neighbor_count, total_links)} neighbors/links")
        elif neighbor_count >= 5:
            bump("distribution", 25, f"{neighbor_count} neighbors")
        elif neighbor_count <= 2 and access_ports >= 8:
            bump("access", 20, "Few uplinks, many access ports")

        if vlan_hint >= 20 or trunk_count >= 8:
            bump("core", 40, f"{vlan_hint} VLANs / {trunk_count} trunk interfaces")
        elif vlan_hint >= 8 or trunk_count >= 3:
            bump("distribution", 28, f"{vlan_hint} VLANs / {trunk_count} trunks")

        if trunk_links >= 6 or uplinkish >= 6:
            bump("core", 30, f"{max(trunk_links, uplinkish)} trunk/uplink links")
        if high_speed >= 4:
            bump("core", 20, f"{high_speed} ≥10G interfaces")
            bump("distribution", 10, f"{high_speed} high-speed interfaces")

        if access_ports >= 16 and trunk_count <= 2:
            bump("access", 45, f"{access_ports} access ports, few trunks")
        if fdb_count >= 100:
            bump("access", 25, f"{fdb_count} MAC addresses in FDB")
        elif fdb_count >= 30:
            bump("access", 12, f"{fdb_count} MAC addresses in FDB")

        if "wan" in combined or any("wan" in str(i.get("name") or "").lower() for i in interfaces):
            bump("firewall", 25, "WAN interface naming")
            bump("router", 15, "WAN interface naming")

        if iface_count == 0 and platform in {"linux", "windows", "proxmox", "vsphere", "esxi"}:
            bump("server", 30, "Host platform with no switchports")

        # Pick winner
        best_role = max(scores.items(), key=lambda kv: kv[1])
        role, raw = best_role
        if raw < 15:
            role = "unknown"
            why = ["Insufficient signals for confident classification"]
            confidence = 35.0
        else:
            # Normalize confidence: 100 ≈ raw 120
            second = sorted(scores.values(), reverse=True)[1] if len(scores) > 1 else 0
            margin = raw - second
            confidence = min(98.0, max(40.0, 45 + raw * 0.4 + margin * 0.25))
            why = reasons[role][:6] or [f"Score {raw:.0f} for {role}"]

        return RoleDetectionResult(
            role=role,
            confidence=confidence,
            reasons=why,
            signals={
                "neighbor_count": neighbor_count,
                "vlan_count": vlan_hint,
                "trunk_interfaces": trunk_count,
                "access_ports_up": access_ports,
                "high_speed_ports": high_speed,
                "fdb_count": fdb_count,
                "interface_count": iface_count,
                "trunk_links": trunk_links,
                "platform": platform,
            },
        )


@dataclass(slots=True)
class MacTraceHop:
    device_id: str
    hostname: str
    role: str | None
    interface: str | None


@dataclass(slots=True)
class MacTraceResult:
    query: str
    found: bool
    mac: str | None = None
    ip: str | None = None
    hostname: str | None = None
    endpoint_device_id: str | None = None
    connected_device_id: str | None = None
    connected_hostname: str | None = None
    port: str | None = None
    vlan_id: int | None = None
    path: list[MacTraceHop] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "query": self.query,
            "found": self.found,
            "mac": self.mac,
            "ip": self.ip,
            "hostname": self.hostname,
            "endpoint_device_id": self.endpoint_device_id,
            "connected_device_id": self.connected_device_id,
            "connected_hostname": self.connected_hostname,
            "port": self.port,
            "vlan_id": self.vlan_id,
            "path": [
                {
                    "device_id": h.device_id,
                    "hostname": h.hostname,
                    "role": h.role,
                    "interface": h.interface,
                }
                for h in self.path
            ],
            "sources": self.sources,
        }


class HierarchicalLayout:
    """Assign ranks/layers for Internet → Firewall → Core → Dist → Access → Clients."""

    def assign(
        self,
        devices: list[dict[str, Any]],
        edges: list[dict[str, Any]],
    ) -> dict[str, dict[str, Any]]:
        """Return per-device layout metadata: rank, layer, column."""
        by_id = {str(d["id"]): d for d in devices}
        ranks: dict[str, int] = {}
        for did, d in by_id.items():
            role = str(d.get("network_role") or d.get("role") or "unknown").lower()
            ranks[did] = ROLE_LAYOUT_RANK.get(role, ROLE_LAYOUT_RANK["unknown"])

        # Column packing per rank
        buckets: dict[int, list[str]] = {}
        for did, rank in ranks.items():
            buckets.setdefault(rank, []).append(did)
        for rank in buckets:
            buckets[rank].sort(key=lambda i: (by_id[i].get("hostname") or i).lower())

        meta: dict[str, dict[str, Any]] = {}
        for rank, ids in buckets.items():
            for col, did in enumerate(ids):
                role = str(by_id[did].get("network_role") or by_id[did].get("role") or "unknown")
                meta[did] = {
                    "rank": rank,
                    "layer": role,
                    "column": col,
                    "columns_in_layer": len(ids),
                }
        # Preserve edge count for clustering hints
        degree: dict[str, int] = {i: 0 for i in by_id}
        for e in edges:
            s, t = str(e.get("source")), str(e.get("target"))
            if s in degree:
                degree[s] += 1
            if t in degree:
                degree[t] += 1
        for did, m in meta.items():
            m["degree"] = degree.get(did, 0)
            m["cluster"] = "collapse" if degree.get(did, 0) <= 1 and m["rank"] >= 5 else "expand"
        return meta
