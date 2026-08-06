"""Topology routes."""

from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from netatlas.api.deps import get_db, require_permission
from netatlas.domain.services import CablePathResolver, LinkHealthScorer, TopologyBuilder
from netatlas.infrastructure.persistence.models import (
    DeviceMetricModel,
    DeviceModel,
    InterfaceModel,
    LinkModel,
)

router = APIRouter(prefix="/topology", tags=["topology"])


async def _latest_interface_counters(session: AsyncSession, device_ids: set[str]) -> dict[str, dict[str, dict[str, Any]]]:
    """Latest per-device interface counter snapshot, keyed by device_id → interface name."""
    result: dict[str, dict[str, dict[str, Any]]] = {}
    if not device_ids:
        return result
    for did in device_ids:
        row = (
            await session.execute(
                select(DeviceMetricModel)
                .where(DeviceMetricModel.device_id == did)
                .order_by(DeviceMetricModel.collected_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if not row:
            continue
        counters = (row.extras or {}).get("interface_counters") or []
        by_name = {c.get("name"): c for c in counters if c.get("name")}
        if by_name:
            result[did] = by_name
    return result


def _link_dict(link: LinkModel) -> dict[str, Any]:
    return {
        "id": str(link.id),
        "interface_a_id": str(link.interface_a_id),
        "interface_b_id": str(link.interface_b_id),
        "discovery_method": link.discovery_method,
        "speed_bps": link.speed_bps,
        "is_lacp": link.is_lacp,
        "lacp_key": link.lacp_key,
        "is_trunk": link.is_trunk,
        "vlans": link.vlans or [],
        "confidence": link.confidence,
        "media": getattr(link, "media", None) or "unknown",
        "link_status": getattr(link, "link_status", None) or "unknown",
        "crc_errors": getattr(link, "crc_errors", None),
        "drops": getattr(link, "drops", None),
        "rx_utilization_pct": getattr(link, "rx_utilization_pct", None),
        "tx_utilization_pct": getattr(link, "tx_utilization_pct", None),
        "sfp_vendor": getattr(link, "sfp_vendor", None),
        "sfp_model": getattr(link, "sfp_model", None),
        "sfp_serial": getattr(link, "sfp_serial", None),
        "rx_optical_dbm": getattr(link, "rx_optical_dbm", None),
        "tx_optical_dbm": getattr(link, "tx_optical_dbm", None),
        "temperature_c": getattr(link, "temperature_c", None),
        "voltage": getattr(link, "voltage", None),
    }


async def _score_links(
    session: AsyncSession, links: list[LinkModel], interfaces: dict[str, InterfaceModel]
) -> dict[str, tuple[str, list[str]]]:
    """Compute Link Health for a batch of links using latest SNMP interface counters."""
    device_ids: set[str] = set()
    for link in links:
        a = interfaces.get(str(link.interface_a_id))
        b = interfaces.get(str(link.interface_b_id))
        if a:
            device_ids.add(str(a.device_id))
        if b:
            device_ids.add(str(b.device_id))
    counters_by_device = await _latest_interface_counters(session, device_ids)

    scorer = LinkHealthScorer()
    results: dict[str, tuple[str, list[str]]] = {}
    for link in links:
        a = interfaces.get(str(link.interface_a_id))
        b = interfaces.get(str(link.interface_b_id))
        if not a or not b:
            continue
        counters_a = counters_by_device.get(str(a.device_id), {}).get(a.name)
        counters_b = counters_by_device.get(str(b.device_id), {}).get(b.name)
        status, reasons = scorer.score(
            iface_a={"oper_status": a.oper_status, "duplex": a.duplex},
            iface_b={"oper_status": b.oper_status, "duplex": b.duplex},
            counters_a=counters_a,
            counters_b=counters_b,
            link=_link_dict(link),
        )
        results[str(link.id)] = (status, reasons)
    return results


@router.get("/graph")
async def topology_graph(
    session: Annotated[AsyncSession, Depends(get_db)],
    _user: Annotated[Any, Depends(require_permission("topology:read"))],
) -> dict[str, Any]:
    devices = (await session.execute(select(DeviceModel))).scalars().all()
    links = (await session.execute(select(LinkModel))).scalars().all()
    interfaces = (await session.execute(select(InterfaceModel))).scalars().all()
    interfaces_by_id = {
        str(i.id): {
            "id": str(i.id),
            "device_id": str(i.device_id),
            "name": i.name,
            "speed_bps": i.speed_bps,
        }
        for i in interfaces
    }
    interfaces_models_by_id = {str(i.id): i for i in interfaces}
    device_dicts = [
        {
            "id": str(d.id),
            "hostname": d.hostname,
            "management_ip": str(d.management_ip) if d.management_ip else None,
            "platform": d.platform,
            "vendor": d.vendor,
            "status": d.status,
            "network_role": getattr(d, "network_role", None) or "unknown",
            "role_confidence": float(getattr(d, "role_confidence", 0) or 0),
            "role": getattr(d, "network_role", None) or "unknown",
            "location": getattr(d, "location", None),
            "criticality": getattr(d, "criticality", None) or "normal",
            "device_class": (d.attributes or {}).get("device_class"),
            "printer": (d.attributes or {}).get("printer"),
            "auto_classified": bool((d.attributes or {}).get("auto_classified")),
        }
        for d in devices
    ]
    health_by_link = await _score_links(session, links, interfaces_models_by_id)
    link_dicts = []
    for link in links:
        d = _link_dict(link)
        status, reasons = health_by_link.get(str(link.id), ("unknown", ["No telemetry available yet"]))
        d["health"] = status
        d["health_reasons"] = reasons
        link_dicts.append(d)
    nodes, edges = TopologyBuilder().build(device_dicts, link_dicts, interfaces_by_id)
    from netatlas.domain.services.intelligence import HierarchicalLayout

    edge_simple = [{"source": e.source, "target": e.target} for e in edges]
    layout = HierarchicalLayout().assign(device_dicts, edge_simple)
    return {
        "nodes": [
            {
                "id": n.id,
                "label": n.label,
                "kind": n.kind,
                "type": n.data.get("platform") or n.kind,
                "role": n.data.get("network_role") or n.data.get("role") or "unknown",
                "data": {**n.data, "layout": layout.get(n.id, {})},
            }
            for n in nodes
        ],
        "edges": [
            {"id": e.id, "source": e.source, "target": e.target, "label": e.label, "data": e.data}
            for e in edges
        ],
        "layout": {"algorithm": "role-hierarchy", "nodes": layout},
    }


@router.get("/cable-path")
async def cable_path(
    session: Annotated[AsyncSession, Depends(get_db)],
    _user: Annotated[Any, Depends(require_permission("topology:read"))],
    from_device_id: UUID = Query(...),
    to_device_id: UUID = Query(...),
) -> dict[str, Any]:
    graph = await topology_graph(session, _user)
    devices = {n["id"]: n["data"] for n in graph["nodes"]}
    interfaces = {}
    iface_rows = (await session.execute(select(InterfaceModel))).scalars().all()
    for i in iface_rows:
        interfaces[str(i.id)] = {
            "id": str(i.id),
            "device_id": str(i.device_id),
            "name": i.name,
        }
    links = (await session.execute(select(LinkModel))).scalars().all()
    link_dicts = [
        {
            "id": str(link.id),
            "interface_a_id": str(link.interface_a_id),
            "interface_b_id": str(link.interface_b_id),
        }
        for link in links
    ]
    hops = CablePathResolver().resolve(
        from_device_id=from_device_id,
        to_device_id=to_device_id,
        devices=devices,
        links=link_dicts,
        interfaces_by_id=interfaces,
    )
    return {
        "found": bool(hops),
        "hops": [
            {"device_id": h.device_id, "hostname": h.hostname, "interface": h.interface} for h in hops
        ],
    }


@router.get("/links")
async def list_links(
    session: Annotated[AsyncSession, Depends(get_db)],
    _user: Annotated[Any, Depends(require_permission("topology:read"))],
) -> list[dict[str, Any]]:
    links = (await session.execute(select(LinkModel))).scalars().all()
    interfaces = {str(i.id): i for i in (await session.execute(select(InterfaceModel))).scalars().all()}
    health_by_link = await _score_links(session, links, interfaces)
    items = []
    for link in links:
        d = _link_dict(link)
        status, reasons = health_by_link.get(str(link.id), ("unknown", ["No telemetry available yet"]))
        d["health"] = status
        d["health_reasons"] = reasons
        items.append(d)
    return items


@router.get("/links/{link_id}")
async def get_link_detail(
    link_id: UUID,
    session: Annotated[AsyncSession, Depends(get_db)],
    _user: Annotated[Any, Depends(require_permission("topology:read"))],
) -> dict[str, Any]:
    """Interface-centric connection card: both endpoints, media, VLANs, health."""
    link = await session.get(LinkModel, link_id)
    if not link:
        raise HTTPException(status_code=404, detail="Link not found")
    iface_a = await session.get(InterfaceModel, link.interface_a_id)
    iface_b = await session.get(InterfaceModel, link.interface_b_id)
    if not iface_a or not iface_b:
        raise HTTPException(status_code=404, detail="Link endpoints missing")
    device_a = await session.get(DeviceModel, iface_a.device_id)
    device_b = await session.get(DeviceModel, iface_b.device_id)

    health_by_link = await _score_links(session, [link], {str(iface_a.id): iface_a, str(iface_b.id): iface_b})
    status, reasons = health_by_link.get(str(link.id), ("unknown", ["No telemetry available yet"]))

    def _endpoint(iface: InterfaceModel, device: DeviceModel | None) -> dict[str, Any]:
        return {
            "device_id": str(iface.device_id),
            "hostname": device.hostname if device else None,
            "management_ip": str(device.management_ip) if device and device.management_ip else None,
            "role": getattr(device, "network_role", None) if device else None,
            "interface": iface.name,
            "description": iface.description,
            "mac": iface.mac,
            "mtu": iface.mtu,
            "duplex": iface.duplex,
            "speed_bps": iface.speed_bps,
            "admin_status": iface.admin_status,
            "oper_status": iface.oper_status,
            "is_trunk": iface.is_trunk,
            "native_vlan": iface.native_vlan,
            "tagged_vlans": (iface.attributes or {}).get("tagged_vlans") or [],
            "lacp_group": iface.lacp_group,
        }

    d = _link_dict(link)
    d["health"] = status
    d["health_reasons"] = reasons
    d["a"] = _endpoint(iface_a, device_a)
    d["b"] = _endpoint(iface_b, device_b)
    return d
