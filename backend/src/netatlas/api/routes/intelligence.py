"""Device Intelligence, MAC Trace, VLAN View, Audit History, role detection APIs.

Additive routes — do not replace existing inventory/topology endpoints.
"""

from __future__ import annotations

import re
from collections import defaultdict
from datetime import datetime, timezone
from typing import Annotated, Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from netatlas.api.deps import get_db, require_permission
from netatlas.domain.services.intelligence import HierarchicalLayout, RoleDetector
from netatlas.infrastructure.persistence.models import (
    ArpEntryModel,
    AuditEventModel,
    CableModel,
    DeviceModel,
    DeviceRelationshipModel,
    FdbEntryModel,
    InterfaceModel,
    IpAddressModel,
    LinkModel,
    LldpNeighborModel,
    PatchPanelModel,
    SnapshotModel,
    VlanModel,
    VlanObjectModel,
)

router = APIRouter(tags=["intelligence"])


def _norm_mac(value: str) -> str:
    hex_only = re.sub(r"[^0-9a-fA-F]", "", value or "")
    if len(hex_only) != 12:
        return (value or "").strip().lower()
    parts = [hex_only[i : i + 2] for i in range(0, 12, 2)]
    return ":".join(parts).lower()


def _device_row_dict(d: DeviceModel) -> dict[str, Any]:
    return {
        "id": str(d.id),
        "hostname": d.hostname,
        "vendor": d.vendor,
        "model": d.model,
        "serial": d.serial,
        "firmware": d.firmware,
        "os_version": d.os_version,
        "management_ip": str(d.management_ip) if d.management_ip else None,
        "management_mac": str(d.management_mac) if d.management_mac else None,
        "platform": d.platform,
        "status": d.status,
        "first_seen_at": d.first_seen_at.isoformat() if d.first_seen_at else None,
        "last_seen_at": d.last_seen_at.isoformat() if d.last_seen_at else None,
        "attributes": d.attributes or {},
        "network_role": d.network_role or "unknown",
        "role_confidence": float(d.role_confidence or 0),
        "role_reasons": list(d.role_reasons or []),
        "role_source": d.role_source or "auto",
        "location": d.location,
        "rack": d.rack,
        "owner": d.owner,
        "criticality": d.criticality or "normal",
        "description": d.description,
    }


async def _iface_dicts(session: AsyncSession, device_id: UUID) -> list[dict[str, Any]]:
    rows = (
        await session.execute(select(InterfaceModel).where(InterfaceModel.device_id == device_id))
    ).scalars().all()
    return [
        {
            "id": str(i.id),
            "name": i.name,
            "description": i.description,
            "mac": str(i.mac) if i.mac else None,
            "speed_bps": i.speed_bps,
            "admin_status": i.admin_status,
            "oper_status": i.oper_status,
            "is_trunk": i.is_trunk,
            "native_vlan": i.native_vlan,
            "lacp_group": i.lacp_group,
        }
        for i in rows
    ]


async def _neighbor_count(session: AsyncSession, device_id: UUID) -> int:
    lldp = await session.scalar(
        select(func.count()).select_from(LldpNeighborModel).where(LldpNeighborModel.device_id == device_id)
    )
    # Also count unique link peers
    ifaces = (
        await session.execute(select(InterfaceModel.id).where(InterfaceModel.device_id == device_id))
    ).scalars().all()
    if not ifaces:
        return int(lldp or 0)
    links = (
        await session.execute(
            select(LinkModel).where(
                or_(LinkModel.interface_a_id.in_(ifaces), LinkModel.interface_b_id.in_(ifaces))
            )
        )
    ).scalars().all()
    return max(int(lldp or 0), len(links))


async def _link_stats_for_device(session: AsyncSession, device_id: UUID) -> dict[str, Any]:
    ifaces = (
        await session.execute(select(InterfaceModel.id).where(InterfaceModel.device_id == device_id))
    ).scalars().all()
    if not ifaces:
        return {"links": 0, "trunk_links": 0}
    links = (
        await session.execute(
            select(LinkModel).where(
                or_(LinkModel.interface_a_id.in_(ifaces), LinkModel.interface_b_id.in_(ifaces))
            )
        )
    ).scalars().all()
    return {
        "links": len(links),
        "trunk_links": sum(1 for link in links if link.is_trunk),
    }


async def _detect_and_persist(session: AsyncSession, device: DeviceModel, *, persist: bool = True) -> dict[str, Any]:
    ifaces = await _iface_dicts(session, device.id)
    neighbors = await _neighbor_count(session, device.id)
    fdb_count = int(
        await session.scalar(
            select(func.count()).select_from(FdbEntryModel).where(FdbEntryModel.device_id == device.id)
        )
        or 0
    )
    vlan_count = int(
        await session.scalar(
            select(func.count()).select_from(VlanModel).where(VlanModel.device_id == device.id)
        )
        or 0
    )
    link_stats = await _link_stats_for_device(session, device.id)
    result = RoleDetector().detect(
        device=_device_row_dict(device),
        interfaces=ifaces,
        neighbor_count=neighbors,
        vlan_count=vlan_count,
        fdb_count=fdb_count,
        link_stats=link_stats,
    )
    if persist and device.role_source != "manual":
        device.network_role = result.role
        device.role_confidence = result.confidence
        device.role_reasons = result.reasons
        device.role_source = "auto"
        await session.commit()
        await session.refresh(device)
    return result.to_dict()


@router.get("/devices/{device_id}/intelligence")
async def device_intelligence(
    device_id: UUID,
    session: Annotated[AsyncSession, Depends(get_db)],
    _user: Annotated[Any, Depends(require_permission("inventory:read"))],
) -> dict[str, Any]:
    device = await session.get(DeviceModel, device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    # Refresh auto role if empty/stale-unknown with 0 confidence
    if device.role_source != "manual" and (not device.network_role or device.network_role == "unknown"):
        await _detect_and_persist(session, device, persist=True)

    ifaces = await _iface_dicts(session, device_id)
    neighbors = (
        await session.execute(
            select(LldpNeighborModel).where(LldpNeighborModel.device_id == device_id).limit(50)
        )
    ).scalars().all()
    vlans = (
        await session.execute(select(VlanModel).where(VlanModel.device_id == device_id))
    ).scalars().all()
    fdb = (
        await session.execute(
            select(FdbEntryModel).where(FdbEntryModel.device_id == device_id).limit(100)
        )
    ).scalars().all()
    rels = (
        await session.execute(
            select(DeviceRelationshipModel).where(
                or_(
                    DeviceRelationshipModel.source_device_id == device_id,
                    DeviceRelationshipModel.target_device_id == device_id,
                )
            )
        )
    ).scalars().all()
    audit = (
        await session.execute(
            select(AuditEventModel)
            .where(
                AuditEventModel.resource_type == "device",
                AuditEventModel.resource_id == str(device_id),
            )
            .order_by(AuditEventModel.created_at.desc())
            .limit(50)
        )
    ).scalars().all()

    link_stats = await _link_stats_for_device(session, device_id)
    role = {
        "role": device.network_role,
        "confidence": float(device.role_confidence or 0),
        "reasons": list(device.role_reasons or []),
        "source": device.role_source,
    }

    return {
        "identity": {
            "id": str(device.id),
            "hostname": device.hostname,
            "vendor": device.vendor,
            "model": device.model,
            "serial": device.serial,
            "firmware": device.firmware,
            "os_version": device.os_version,
            "management_ip": str(device.management_ip) if device.management_ip else None,
            "management_mac": str(device.management_mac) if device.management_mac else None,
            "platform": device.platform,
            "status": device.status,
        },
        "role": role,
        "metadata": {
            "location": device.location,
            "rack": device.rack,
            "owner": device.owner,
            "criticality": device.criticality,
            "description": device.description,
        },
        "lifecycle": {
            "created_at": device.created_at.isoformat() if getattr(device, "created_at", None) else None,
            "first_seen_at": device.first_seen_at.isoformat() if device.first_seen_at else None,
            "last_seen_at": device.last_seen_at.isoformat() if device.last_seen_at else None,
        },
        "relationships": {
            "interfaces": ifaces,
            "neighbors": [
                {
                    "local_interface": n.local_interface,
                    "remote_hostname": n.remote_hostname,
                    "remote_interface": n.remote_interface,
                    "protocol": n.protocol,
                }
                for n in neighbors
            ],
            "vlans": [{"vlan_id": v.vlan_id, "name": v.name} for v in vlans],
            "links": link_stats,
            "dependencies": [
                {
                    "id": str(r.id),
                    "source_device_id": str(r.source_device_id),
                    "target_device_id": str(r.target_device_id),
                    "rel_type": r.rel_type,
                }
                for r in rels
            ],
            "fdb_sample": [
                {
                    "mac": str(f.mac),
                    "vlan_id": f.vlan_id,
                    "interface": f.interface,
                }
                for f in fdb
            ],
        },
        "audit": [
            {
                "id": str(a.id),
                "action": a.action,
                "created_at": a.created_at.isoformat() if a.created_at else None,
                "details": a.details or {},
            }
            for a in audit
        ],
    }


class RoleOverrideBody(BaseModel):
    role: str = Field(..., min_length=2, max_length=32)
    reason: str | None = None


@router.post("/devices/{device_id}/role/detect")
async def detect_device_role(
    device_id: UUID,
    session: Annotated[AsyncSession, Depends(get_db)],
    _user: Annotated[Any, Depends(require_permission("inventory:read"))],
) -> dict[str, Any]:
    device = await session.get(DeviceModel, device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    detection = await _detect_and_persist(session, device, persist=True)
    return {
        "device_id": str(device_id),
        "auto_detected_role": detection["role"],
        "confidence": detection["confidence"],
        "reasons": detection["reasons"],
        "signals": detection["signals"],
        "source": "auto",
    }


@router.patch("/devices/{device_id}/role")
async def override_device_role(
    device_id: UUID,
    body: RoleOverrideBody,
    session: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[Any, Depends(require_permission("discovery:write"))],
) -> dict[str, Any]:
    device = await session.get(DeviceModel, device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    role = body.role.lower().strip()
    device.network_role = role
    device.role_confidence = 100.0
    device.role_reasons = [body.reason or "Manual override"]
    device.role_source = "manual"
    session.add(
        AuditEventModel(
            id=uuid4(),
            actor_user_id=getattr(user, "id", None),
            action="device.role_override",
            resource_type="device",
            resource_id=str(device_id),
            details={"role": role, "reason": body.reason},
        )
    )
    await session.commit()
    return {"device_id": str(device_id), "role": role, "source": "manual", "confidence": 100.0}


@router.post("/devices/roles/detect-all")
async def detect_all_roles(
    session: Annotated[AsyncSession, Depends(get_db)],
    _user: Annotated[Any, Depends(require_permission("discovery:write"))],
) -> dict[str, Any]:
    devices = (await session.execute(select(DeviceModel))).scalars().all()
    updated = 0
    results = []
    for device in devices:
        if device.role_source == "manual":
            continue
        detection = await _detect_and_persist(session, device, persist=True)
        updated += 1
        results.append({"device_id": str(device.id), "hostname": device.hostname, **detection})
    return {"updated": updated, "items": results[:200]}


@router.get("/trace/mac")
async def trace_mac(
    session: Annotated[AsyncSession, Depends(get_db)],
    _user: Annotated[Any, Depends(require_permission("topology:read"))],
    q: str = Query(..., min_length=2, description="MAC, IP, or hostname"),
) -> dict[str, Any]:
    query = q.strip()
    sources: list[str] = []
    mac: str | None = None
    ip: str | None = None
    hostname: str | None = None
    connected_device_id: UUID | None = None
    port: str | None = None
    vlan_id: int | None = None
    endpoint_device_id: UUID | None = None

    # 1) Try as MAC via FDB / ARP / device & interface MACs
    maybe_mac = _norm_mac(query)
    if re.fullmatch(r"([0-9a-f]{2}:){5}[0-9a-f]{2}", maybe_mac):
        mac = maybe_mac
        fdb_rows = (await session.execute(select(FdbEntryModel).limit(8000))).scalars().all()
        fdb_hit = next((r for r in fdb_rows if str(r.mac).lower() == mac), None)
        if fdb_hit:
            sources.append("fdb")
            connected_device_id = fdb_hit.device_id
            port = fdb_hit.interface
            vlan_id = fdb_hit.vlan_id

        arp_rows = (await session.execute(select(ArpEntryModel).limit(8000))).scalars().all()
        arp_hit = next((r for r in arp_rows if str(r.mac).lower() == mac), None)
        if arp_hit:
            sources.append("arp")
            ip = str(arp_hit.ip)
            if not connected_device_id:
                connected_device_id = arp_hit.device_id
                port = arp_hit.interface or port

        devices = (await session.execute(select(DeviceModel))).scalars().all()
        for d in devices:
            if d.management_mac and str(d.management_mac).lower() == mac:
                sources.append("device.management_mac")
                endpoint_device_id = d.id
                hostname = d.hostname
                ip = ip or (str(d.management_ip) if d.management_ip else None)
                break
        if not endpoint_device_id:
            iface_rows = (await session.execute(select(InterfaceModel).limit(20000))).scalars().all()
            iface_hit = next((i for i in iface_rows if i.mac and str(i.mac).lower() == mac), None)
            if iface_hit:
                sources.append("interface.mac")
                endpoint_device_id = iface_hit.device_id
                d = await session.get(DeviceModel, iface_hit.device_id)
                hostname = d.hostname if d else None

    # 2) IP / hostname lookup
    if not sources:
        devices = (await session.execute(select(DeviceModel))).scalars().all()
        qlow = query.lower()
        for d in devices:
            if (d.management_ip and str(d.management_ip) == query) or (
                d.hostname and d.hostname.lower() == qlow
            ):
                sources.append("device")
                endpoint_device_id = d.id
                hostname = d.hostname
                ip = str(d.management_ip) if d.management_ip else None
                mac = str(d.management_mac) if d.management_mac else None
                break
        if not endpoint_device_id:
            addr = (
                await session.execute(
                    select(IpAddressModel).where(IpAddressModel.address == query).limit(1)
                )
            ).scalar_one_or_none()
            if addr:
                sources.append("ipam")
                ip = str(addr.address)
                mac = str(addr.mac) if addr.mac else None
                hostname = addr.hostname
                endpoint_device_id = addr.device_id
                if mac and not connected_device_id:
                    fdb_rows = (await session.execute(select(FdbEntryModel).limit(5000))).scalars().all()
                    fdb_hit = next((r for r in fdb_rows if str(r.mac).lower() == str(mac).lower()), None)
                    if fdb_hit:
                        connected_device_id = fdb_hit.device_id
                        port = fdb_hit.interface
                        vlan_id = fdb_hit.vlan_id
                        sources.append("fdb")

    if not sources:
        return {
            "query": query,
            "found": False,
            "mac": mac,
            "ip": ip,
            "hostname": hostname,
            "path": [],
            "sources": [],
        }

    connected = await session.get(DeviceModel, connected_device_id) if connected_device_id else None
    endpoint = await session.get(DeviceModel, endpoint_device_id) if endpoint_device_id else None

    # Build path: endpoint → access → … → core (or just connected switch)
    path: list[dict[str, Any]] = []
    if endpoint:
        path.append(
            {
                "device_id": str(endpoint.id),
                "hostname": endpoint.hostname,
                "role": endpoint.network_role,
                "interface": None,
            }
        )
    if connected and (not endpoint or connected.id != endpoint.id):
        path.append(
            {
                "device_id": str(connected.id),
                "hostname": connected.hostname,
                "role": connected.network_role,
                "interface": port,
            }
        )
        # Walk toward core via cable path heuristic: pick highest-rank neighbor chain
        # Use BFS toward a core/firewall device if present
        cores = (
            await session.execute(
                select(DeviceModel).where(DeviceModel.network_role.in_(("core", "firewall", "router")))
            )
        ).scalars().all()
        if cores:
            target = cores[0]
            interfaces = (await session.execute(select(InterfaceModel))).scalars().all()
            interfaces_by_id = {
                str(i.id): {"id": str(i.id), "device_id": str(i.device_id), "name": i.name}
                for i in interfaces
            }
            devices_map = {
                str(d.id): {"id": str(d.id), "hostname": d.hostname, "network_role": d.network_role}
                for d in (await session.execute(select(DeviceModel))).scalars().all()
            }
            links = (
                await session.execute(select(LinkModel))
            ).scalars().all()
            link_dicts = [
                {
                    "id": str(link.id),
                    "interface_a_id": str(link.interface_a_id),
                    "interface_b_id": str(link.interface_b_id),
                }
                for link in links
            ]
            from netatlas.domain.services import CablePathResolver

            hops = CablePathResolver().resolve(
                from_device_id=connected.id,
                to_device_id=target.id,
                devices=devices_map,
                links=link_dicts,
                interfaces_by_id=interfaces_by_id,
            )
            for hop in hops[1:]:
                path.append(
                    {
                        "device_id": hop.device_id,
                        "hostname": hop.hostname,
                        "role": devices_map.get(hop.device_id, {}).get("network_role"),
                        "interface": hop.interface,
                    }
                )

    return {
        "query": query,
        "found": True,
        "mac": mac,
        "ip": ip,
        "hostname": hostname or (endpoint.hostname if endpoint else None),
        "endpoint_device_id": str(endpoint_device_id) if endpoint_device_id else None,
        "connected_device_id": str(connected_device_id) if connected_device_id else None,
        "connected_hostname": connected.hostname if connected else None,
        "port": port,
        "vlan_id": vlan_id,
        "path": path,
        "sources": sources,
    }


@router.get("/vlans")
async def list_vlan_intelligence(
    session: Annotated[AsyncSession, Depends(get_db)],
    _user: Annotated[Any, Depends(require_permission("inventory:read"))],
) -> dict[str, Any]:
    # Aggregate from per-device vlans + interface native_vlan + link vlans + vlan_objects
    per_device = (await session.execute(select(VlanModel))).scalars().all()
    objects = (await session.execute(select(VlanObjectModel))).scalars().all()
    obj_by_id = {o.vlan_id: o for o in objects}

    agg: dict[int, dict[str, Any]] = {}
    for v in per_device:
        bucket = agg.setdefault(
            v.vlan_id,
            {
                "vlan_id": v.vlan_id,
                "name": v.name,
                "description": None,
                "networks": [],
                "device_ids": set(),
                "ports": [],
                "device_count": 0,
            },
        )
        bucket["device_ids"].add(str(v.device_id))
        if v.name and not bucket["name"]:
            bucket["name"] = v.name

    ifaces = (await session.execute(select(InterfaceModel).where(InterfaceModel.native_vlan.is_not(None)))).scalars().all()
    for i in ifaces:
        vid = int(i.native_vlan)  # type: ignore[arg-type]
        bucket = agg.setdefault(
            vid,
            {
                "vlan_id": vid,
                "name": None,
                "description": None,
                "networks": [],
                "device_ids": set(),
                "ports": [],
                "device_count": 0,
            },
        )
        bucket["device_ids"].add(str(i.device_id))
        bucket["ports"].append({"device_id": str(i.device_id), "interface": i.name, "tagged": False})

    for vid, o in obj_by_id.items():
        bucket = agg.setdefault(
            vid,
            {
                "vlan_id": vid,
                "name": o.name,
                "description": o.description,
                "networks": list(o.networks or []),
                "device_ids": set(),
                "ports": [],
                "device_count": 0,
            },
        )
        bucket["name"] = bucket["name"] or o.name
        bucket["description"] = o.description
        bucket["networks"] = list(o.networks or [])

    devices = {
        str(d.id): d
        for d in (await session.execute(select(DeviceModel))).scalars().all()
    }
    items = []
    for vid, bucket in sorted(agg.items(), key=lambda x: x[0]):
        roles = {devices[i].network_role for i in bucket["device_ids"] if i in devices}
        path = []
        for layer in ("core", "distribution", "access"):
            if layer in roles:
                path.append(layer)
        items.append(
            {
                "vlan_id": vid,
                "name": bucket["name"] or f"VLAN {vid}",
                "description": bucket["description"],
                "networks": bucket["networks"],
                "device_count": len(bucket["device_ids"]),
                "devices": [
                    {
                        "id": i,
                        "hostname": devices[i].hostname if i in devices else i,
                        "role": devices[i].network_role if i in devices else None,
                    }
                    for i in list(bucket["device_ids"])[:40]
                ],
                "ports": bucket["ports"][:40],
                "topology_path": path,
            }
        )
    return {"total": len(items), "items": items}


@router.get("/vlans/{vlan_id}")
async def get_vlan_intelligence(
    vlan_id: int,
    session: Annotated[AsyncSession, Depends(get_db)],
    _user: Annotated[Any, Depends(require_permission("inventory:read"))],
) -> dict[str, Any]:
    data = await list_vlan_intelligence(session, _user)
    for item in data["items"]:
        if item["vlan_id"] == vlan_id:
            return item
    raise HTTPException(status_code=404, detail="VLAN not found")


@router.get("/audit/timeline")
async def audit_timeline(
    session: Annotated[AsyncSession, Depends(get_db)],
    _user: Annotated[Any, Depends(require_permission("inventory:read"))],
    resource_type: str | None = None,
    resource_id: str | None = None,
    limit: int = Query(100, ge=1, le=500),
) -> dict[str, Any]:
    stmt = select(AuditEventModel).order_by(AuditEventModel.created_at.desc()).limit(limit)
    if resource_type:
        stmt = stmt.where(AuditEventModel.resource_type == resource_type)
    if resource_id:
        stmt = stmt.where(AuditEventModel.resource_id == resource_id)
    rows = (await session.execute(stmt)).scalars().all()

    # Merge with recent snapshots as synthetic timeline events
    snaps = (
        await session.execute(select(SnapshotModel).order_by(SnapshotModel.created_at.desc()).limit(30))
    ).scalars().all()
    events = [
        {
            "id": str(a.id),
            "kind": "audit",
            "action": a.action,
            "resource_type": a.resource_type,
            "resource_id": a.resource_id,
            "ts": a.created_at.isoformat() if a.created_at else None,
            "details": a.details or {},
        }
        for a in rows
    ]
    for s in snaps:
        events.append(
            {
                "id": str(s.id),
                "kind": "snapshot",
                "action": "snapshot.created",
                "resource_type": "snapshot",
                "resource_id": str(s.id),
                "ts": s.created_at.isoformat() if s.created_at else None,
                "details": {"label": s.label, "summary": s.summary or {}},
            }
        )
    events.sort(key=lambda e: e.get("ts") or "", reverse=True)
    return {"items": events[:limit]}


@router.get("/audit/objects/{resource_type}/{resource_id}")
async def object_history(
    resource_type: str,
    resource_id: str,
    session: Annotated[AsyncSession, Depends(get_db)],
    _user: Annotated[Any, Depends(require_permission("inventory:read"))],
) -> dict[str, Any]:
    rows = (
        await session.execute(
            select(AuditEventModel)
            .where(
                AuditEventModel.resource_type == resource_type,
                AuditEventModel.resource_id == resource_id,
            )
            .order_by(AuditEventModel.created_at.desc())
            .limit(100)
        )
    ).scalars().all()
    lifecycle = {}
    if resource_type == "device":
        try:
            device = await session.get(DeviceModel, UUID(resource_id))
        except Exception:
            device = None
        if device:
            lifecycle = {
                "created_at": device.created_at.isoformat() if getattr(device, "created_at", None) else None,
                "first_seen_at": device.first_seen_at.isoformat() if device.first_seen_at else None,
                "last_seen_at": device.last_seen_at.isoformat() if device.last_seen_at else None,
                "hostname": device.hostname,
                "firmware": device.firmware,
            }
    return {
        "resource_type": resource_type,
        "resource_id": resource_id,
        "lifecycle": lifecycle,
        "changes": [
            {
                "id": str(a.id),
                "action": a.action,
                "ts": a.created_at.isoformat() if a.created_at else None,
                "details": a.details or {},
            }
            for a in rows
        ],
    }


@router.get("/cable-map")
async def cable_map(
    session: Annotated[AsyncSession, Depends(get_db)],
    _user: Annotated[Any, Depends(require_permission("topology:read"))],
) -> dict[str, Any]:
    """Cable Map mode: device↔interface↔cable↔panel (panels may be empty)."""
    links = (await session.execute(select(LinkModel))).scalars().all()
    interfaces = {
        str(i.id): i for i in (await session.execute(select(InterfaceModel))).scalars().all()
    }
    devices = {
        str(d.id): d for d in (await session.execute(select(DeviceModel))).scalars().all()
    }
    panels = (await session.execute(select(PatchPanelModel))).scalars().all()
    cables = (await session.execute(select(CableModel))).scalars().all()

    derived = []
    for link in links:
        a = interfaces.get(str(link.interface_a_id))
        b = interfaces.get(str(link.interface_b_id))
        if not a or not b:
            continue
        da = devices.get(str(a.device_id))
        db = devices.get(str(b.device_id))
        derived.append(
            {
                "kind": "logical_link",
                "link_id": str(link.id),
                "a": {
                    "device_id": str(a.device_id),
                    "hostname": da.hostname if da else None,
                    "interface": a.name,
                },
                "cable": {"type": "inferred", "label": link.discovery_method},
                "panel": None,
                "b": {
                    "device_id": str(b.device_id),
                    "hostname": db.hostname if db else None,
                    "interface": b.name,
                },
            }
        )

    explicit = []
    for c in cables:
        explicit.append(
            {
                "kind": "cable",
                "id": str(c.id),
                "label": c.label,
                "cable_type": c.cable_type,
                "a": {
                    "device_id": str(c.a_device_id) if c.a_device_id else None,
                    "interface_id": str(c.a_interface_id) if c.a_interface_id else None,
                    "panel_id": str(c.a_panel_id) if c.a_panel_id else None,
                    "port": c.a_port,
                },
                "b": {
                    "device_id": str(c.b_device_id) if c.b_device_id else None,
                    "interface_id": str(c.b_interface_id) if c.b_interface_id else None,
                    "panel_id": str(c.b_panel_id) if c.b_panel_id else None,
                    "port": c.b_port,
                },
            }
        )

    return {
        "panels": [
            {
                "id": str(p.id),
                "name": p.name,
                "location": p.location,
                "rack": p.rack,
                "port_count": p.port_count,
            }
            for p in panels
        ],
        "cables": explicit,
        "inferred_paths": derived[:500],
        "model_ready": True,
    }


@router.get("/topology/layout")
async def topology_layout(
    session: Annotated[AsyncSession, Depends(get_db)],
    _user: Annotated[Any, Depends(require_permission("topology:read"))],
) -> dict[str, Any]:
    devices = (await session.execute(select(DeviceModel))).scalars().all()
    # Auto-detect roles for unknowns (non-destructive batch for layout quality)
    for d in devices:
        if d.role_source != "manual" and (not d.network_role or d.network_role == "unknown"):
            await _detect_and_persist(session, d, persist=True)
    devices = (await session.execute(select(DeviceModel))).scalars().all()
    links = (await session.execute(select(LinkModel))).scalars().all()
    interfaces = (await session.execute(select(InterfaceModel))).scalars().all()
    iface_by_id = {str(i.id): i for i in interfaces}

    device_dicts = [_device_row_dict(d) for d in devices]
    edges = []
    for link in links:
        a = iface_by_id.get(str(link.interface_a_id))
        b = iface_by_id.get(str(link.interface_b_id))
        if not a or not b:
            continue
        edges.append({"source": str(a.device_id), "target": str(b.device_id)})
    layout = HierarchicalLayout().assign(device_dicts, edges)
    return {
        "algorithm": "role-hierarchy",
        "layers": ["firewall", "router", "core", "distribution", "access", "wireless", "server", "unknown"],
        "nodes": layout,
    }


class MetadataBody(BaseModel):
    location: str | None = None
    rack: str | None = None
    owner: str | None = None
    criticality: str | None = None
    description: str | None = None


@router.patch("/devices/{device_id}/metadata")
async def update_device_metadata(
    device_id: UUID,
    body: MetadataBody,
    session: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[Any, Depends(require_permission("discovery:write"))],
) -> dict[str, Any]:
    device = await session.get(DeviceModel, device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    for field in ("location", "rack", "owner", "criticality", "description"):
        val = getattr(body, field)
        if val is not None:
            setattr(device, field, val)
    session.add(
        AuditEventModel(
            id=uuid4(),
            actor_user_id=getattr(user, "id", None),
            action="device.metadata_update",
            resource_type="device",
            resource_id=str(device_id),
            details=body.model_dump(exclude_none=True),
        )
    )
    await session.commit()
    return _device_row_dict(device)
