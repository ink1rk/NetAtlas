"""Topology and snapshot domain services."""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Any
from uuid import UUID


@dataclass(frozen=True, slots=True)
class GraphNode:
    id: str
    label: str
    kind: str
    data: dict[str, Any]


@dataclass(frozen=True, slots=True)
class GraphEdge:
    id: str
    source: str
    target: str
    label: str
    data: dict[str, Any]


@dataclass(frozen=True, slots=True)
class CableHop:
    device_id: str
    hostname: str
    interface: str | None


class TopologyBuilder:
    """Build Cytoscape-ready graph structures from devices and links."""

    def build(
        self,
        devices: list[dict[str, Any]],
        links: list[dict[str, Any]],
        interfaces_by_id: dict[str, dict[str, Any]],
    ) -> tuple[list[GraphNode], list[GraphEdge]]:
        nodes = [
            GraphNode(
                id=str(d["id"]),
                label=d.get("hostname") or d.get("management_ip") or str(d["id"]),
                kind=d.get("platform") or "unknown",
                data=d,
            )
            for d in devices
        ]
        edges: list[GraphEdge] = []
        for link in links:
            a = interfaces_by_id.get(str(link["interface_a_id"]))
            b = interfaces_by_id.get(str(link["interface_b_id"]))
            if not a or not b:
                continue
            speed = link.get("speed_bps")
            speed_label = f"{int(speed) // 1_000_000}M" if speed else "?"
            label = f"{a.get('name')} ↔ {b.get('name')} · {speed_label}"
            edges.append(
                GraphEdge(
                    id=str(link["id"]),
                    source=str(a["device_id"]),
                    target=str(b["device_id"]),
                    label=label,
                    data={
                        **link,
                        "interface_a": a.get("name"),
                        "interface_b": b.get("name"),
                    },
                )
            )
        return nodes, edges


class CablePathResolver:
    """Shortest path over undirected device graph using BFS."""

    def resolve(
        self,
        *,
        from_device_id: UUID,
        to_device_id: UUID,
        devices: dict[str, dict[str, Any]],
        links: list[dict[str, Any]],
        interfaces_by_id: dict[str, dict[str, Any]],
    ) -> list[CableHop]:
        adjacency: dict[str, list[tuple[str, str, str]]] = defaultdict(list)
        for link in links:
            a = interfaces_by_id.get(str(link["interface_a_id"]))
            b = interfaces_by_id.get(str(link["interface_b_id"]))
            if not a or not b:
                continue
            da, db = str(a["device_id"]), str(b["device_id"])
            adjacency[da].append((db, a.get("name") or "", b.get("name") or ""))
            adjacency[db].append((da, b.get("name") or "", a.get("name") or ""))

        start, goal = str(from_device_id), str(to_device_id)
        if start == goal:
            d = devices.get(start, {})
            return [CableHop(start, d.get("hostname") or start, None)]

        queue: deque[str] = deque([start])
        prev: dict[str, tuple[str, str, str] | None] = {start: None}
        while queue:
            current = queue.popleft()
            if current == goal:
                break
            for neighbor, local_if, remote_if in adjacency.get(current, []):
                if neighbor in prev:
                    continue
                prev[neighbor] = (current, local_if, remote_if)
                queue.append(neighbor)

        if goal not in prev:
            return []

        hops_rev: list[CableHop] = []
        cursor: str | None = goal
        while cursor is not None:
            meta = prev[cursor]
            d = devices.get(cursor, {})
            iface = meta[2] if meta else None
            hops_rev.append(CableHop(cursor, d.get("hostname") or cursor, iface))
            cursor = meta[0] if meta else None
        hops_rev.reverse()
        return hops_rev


class LinkHealthScorer:
    """Zabbix-style Link Health classification: healthy | warning | critical.

    Pure function of interface state + optional per-interface counters
    (collected via SNMP IF-MIB). Designed to degrade gracefully when
    counters are unavailable (returns "unknown" rather than a false healthy).
    """

    CRC_WARN = 50
    CRC_CRIT = 500
    DROPS_WARN = 100
    DROPS_CRIT = 1000
    UTIL_WARN = 80.0
    UTIL_CRIT = 95.0
    OPTICAL_WARN_DBM = -18.0
    OPTICAL_CRIT_DBM = -23.0
    TEMP_WARN_C = 55.0
    TEMP_CRIT_C = 70.0

    def score(
        self,
        *,
        iface_a: dict[str, Any] | None,
        iface_b: dict[str, Any] | None,
        counters_a: dict[str, Any] | None = None,
        counters_b: dict[str, Any] | None = None,
        link: dict[str, Any] | None = None,
    ) -> tuple[str, list[str]]:
        iface_a = iface_a or {}
        iface_b = iface_b or {}
        link = link or {}
        reasons: list[str] = []
        level = 0  # 0 healthy, 1 warning, 2 critical

        def bump(new_level: int, reason: str) -> None:
            nonlocal level
            level = max(level, new_level)
            reasons.append(reason)

        oper_a = str(iface_a.get("oper_status") or "unknown").lower()
        oper_b = str(iface_b.get("oper_status") or "unknown").lower()
        if oper_a == "down" or oper_b == "down":
            bump(2, "One or both interfaces are operationally down")

        duplex_a = (iface_a.get("duplex") or "").lower()
        duplex_b = (iface_b.get("duplex") or "").lower()
        if duplex_a and duplex_b and duplex_a != duplex_b:
            bump(1, f"Duplex mismatch ({duplex_a} vs {duplex_b})")

        crc = int((counters_a or {}).get("in_errors") or 0) + int((counters_b or {}).get("in_errors") or 0)
        if crc:
            if crc >= self.CRC_CRIT:
                bump(2, f"High CRC/input errors ({crc})")
            elif crc >= self.CRC_WARN:
                bump(1, f"Elevated CRC/input errors ({crc})")

        drops = (
            int((counters_a or {}).get("in_discards") or 0)
            + int((counters_a or {}).get("out_discards") or 0)
            + int((counters_b or {}).get("in_discards") or 0)
            + int((counters_b or {}).get("out_discards") or 0)
        )
        if drops:
            if drops >= self.DROPS_CRIT:
                bump(2, f"High packet drops ({drops})")
            elif drops >= self.DROPS_WARN:
                bump(1, f"Elevated packet drops ({drops})")

        for util_key, label in (("rx_utilization_pct", "RX"), ("tx_utilization_pct", "TX")):
            util = link.get(util_key)
            if util is None:
                continue
            if util >= self.UTIL_CRIT:
                bump(2, f"{label} utilization critical ({util:.0f}%)")
            elif util >= self.UTIL_WARN:
                bump(1, f"{label} utilization high ({util:.0f}%)")

        for optical_key, label in (("rx_optical_dbm", "RX optical power"), ("tx_optical_dbm", "TX optical power")):
            val = link.get(optical_key)
            if val is None:
                continue
            if val <= self.OPTICAL_CRIT_DBM:
                bump(2, f"{label} critically low ({val} dBm)")
            elif val <= self.OPTICAL_WARN_DBM:
                bump(1, f"{label} low ({val} dBm)")

        temp = link.get("temperature_c")
        if temp is not None:
            if temp >= self.TEMP_CRIT_C:
                bump(2, f"Transceiver temperature critical ({temp}°C)")
            elif temp >= self.TEMP_WARN_C:
                bump(1, f"Transceiver temperature high ({temp}°C)")

        if not counters_a and not counters_b and level == 0 and oper_a == "unknown" and oper_b == "unknown":
            return "unknown", ["No telemetry available yet"]
        if not reasons:
            reasons = ["No anomalies detected"]
        status = {0: "healthy", 1: "warning", 2: "critical"}[level]
        return status, reasons


class SnapshotComparer:
    """Compare two canonical snapshot payloads."""

    def compare(self, left: dict[str, Any], right: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
        added: list[dict[str, Any]] = []
        removed: list[dict[str, Any]] = []
        changed: list[dict[str, Any]] = []

        for section in ("devices", "links", "vlans", "interfaces"):
            left_map = {self._key(section, item): item for item in left.get(section, [])}
            right_map = {self._key(section, item): item for item in right.get(section, [])}
            for key, item in right_map.items():
                if key not in left_map:
                    added.append({"section": section, "key": key, "item": item})
                elif self._normalize(left_map[key]) != self._normalize(item):
                    changed.append(
                        {
                            "section": section,
                            "key": key,
                            "before": left_map[key],
                            "after": item,
                        }
                    )
            for key, item in left_map.items():
                if key not in right_map:
                    removed.append({"section": section, "key": key, "item": item})
        return {"added": added, "removed": removed, "changed": changed}

    @staticmethod
    def _key(section: str, item: dict[str, Any]) -> str:
        if section == "devices":
            return item.get("serial") or item.get("management_ip") or item.get("hostname") or str(item)
        if section == "links":
            return f"{item.get('interface_a')}|{item.get('interface_b')}|{item.get('method')}"
        if section == "vlans":
            return f"{item.get('device')}:{item.get('vlan_id')}"
        if section == "interfaces":
            return f"{item.get('device')}:{item.get('name')}"
        return json.dumps(item, sort_keys=True)

    @staticmethod
    def _normalize(item: dict[str, Any]) -> str:
        return json.dumps(item, sort_keys=True, default=str)


class SnapshotChecksum:
    @staticmethod
    def compute(payload: dict[str, Any]) -> str:
        canonical = json.dumps(payload, sort_keys=True, default=str, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
