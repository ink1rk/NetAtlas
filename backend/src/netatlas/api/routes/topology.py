"""Topology routes."""

from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from netatlas.api.deps import get_db, require_permission
from netatlas.domain.services import CablePathResolver, TopologyBuilder
from netatlas.infrastructure.persistence.models import DeviceModel, InterfaceModel, LinkModel

router = APIRouter(prefix="/topology", tags=["topology"])


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
    device_dicts = [
        {
            "id": str(d.id),
            "hostname": d.hostname,
            "management_ip": str(d.management_ip) if d.management_ip else None,
            "platform": d.platform,
            "vendor": d.vendor,
            "status": d.status,
        }
        for d in devices
    ]
    link_dicts = [
        {
            "id": str(link.id),
            "interface_a_id": str(link.interface_a_id),
            "interface_b_id": str(link.interface_b_id),
            "discovery_method": link.discovery_method,
            "speed_bps": link.speed_bps,
            "is_lacp": link.is_lacp,
            "is_trunk": link.is_trunk,
            "vlans": link.vlans or [],
            "confidence": link.confidence,
        }
        for link in links
    ]
    nodes, edges = TopologyBuilder().build(device_dicts, link_dicts, interfaces_by_id)
    return {
        "nodes": [{"id": n.id, "label": n.label, "kind": n.kind, "data": n.data} for n in nodes],
        "edges": [
            {"id": e.id, "source": e.source, "target": e.target, "label": e.label, "data": e.data}
            for e in edges
        ],
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
    return [
        {
            "id": str(link.id),
            "interface_a_id": str(link.interface_a_id),
            "interface_b_id": str(link.interface_b_id),
            "discovery_method": link.discovery_method,
            "speed_bps": link.speed_bps,
            "is_lacp": link.is_lacp,
            "is_trunk": link.is_trunk,
            "vlans": link.vlans or [],
            "confidence": link.confidence,
        }
        for link in links
    ]
