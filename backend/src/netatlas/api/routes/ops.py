"""Discovery, snapshot, IPAM, export, system routes."""

from __future__ import annotations

import ipaddress
import json
from datetime import UTC, datetime
from typing import Annotated, Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from netatlas.api.deps import get_db, get_vault, require_permission
from netatlas.config import Settings, get_settings
from netatlas.domain.entities import DiscoveryJob, DiscoverySeed
from netatlas.domain.services import SnapshotComparer
from netatlas.domain.value_objects import JobStatus
from netatlas.infrastructure.export.exporters import TopologyExporter
from netatlas.infrastructure.persistence.models import (
    CredentialProfileModel,
    DeviceModel,
    InterfaceModel,
    IpAddressModel,
    IpPrefixModel,
    LinkModel,
)
from netatlas.infrastructure.persistence.repositories import (
    SqlAlchemyDiscoveryJobRepository,
    SqlAlchemyDiscoverySeedRepository,
    SqlAlchemySnapshotRepository,
)
from netatlas.infrastructure.security.vault import AesGcmSecretVault

discovery_router = APIRouter(prefix="/discovery", tags=["discovery"])
snapshots_router = APIRouter(prefix="/snapshots", tags=["snapshots"])
ipam_router = APIRouter(prefix="/ipam", tags=["ipam"])
export_router = APIRouter(prefix="/export", tags=["export"])
system_router = APIRouter(tags=["system"])
credentials_router = APIRouter(prefix="/credentials", tags=["credentials"])
vmware_router = APIRouter(prefix="/vmware", tags=["vmware"])
docker_router = APIRouter(prefix="/docker", tags=["docker"])

# In-process progress hub for websocket fans (workers publish via Redis in production).
_PROGRESS: dict[str, list[dict[str, Any]]] = {}


class SeedCreate(BaseModel):
    target: str
    label: str | None = None
    credential_profile_ids: list[UUID] = Field(default_factory=list)


class JobCreate(BaseModel):
    seed_ids: list[UUID] = Field(default_factory=list)
    scan_mode: str = Field(default="deep")
    options: dict[str, Any] = Field(default_factory=dict)


class SnapshotDiffRequest(BaseModel):
    left_id: UUID
    right_id: UUID


class PrefixCreate(BaseModel):
    prefix: str
    description: str | None = None


class ExportRequest(BaseModel):
    format: str
    scope: str = "topology"


class CredentialCreate(BaseModel):
    name: str
    protocol: str
    secret: dict[str, Any]


@discovery_router.get("/seeds")
async def list_seeds(
    session: Annotated[AsyncSession, Depends(get_db)],
    _user: Annotated[Any, Depends(require_permission("discovery:read"))],
) -> list[dict[str, Any]]:
    seeds = await SqlAlchemyDiscoverySeedRepository(session).list()
    return [
        {
            "id": str(s.id),
            "target": s.target,
            "label": s.label,
            "enabled": s.enabled,
            "credential_profile_ids": [str(x) for x in s.credential_profile_ids],
        }
        for s in seeds
    ]


@discovery_router.post("/seeds", status_code=201)
async def create_seed(
    body: SeedCreate,
    session: Annotated[AsyncSession, Depends(get_db)],
    _user: Annotated[Any, Depends(require_permission("discovery:write"))],
) -> dict[str, Any]:
    # Validate target
    try:
        if "/" in body.target:
            ipaddress.ip_network(body.target, strict=False)
        else:
            ipaddress.ip_address(body.target)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"Invalid target: {exc}") from exc
    seed = DiscoverySeed(
        id=uuid4(),
        target=body.target,
        label=body.label,
        enabled=True,
        credential_profile_ids=body.credential_profile_ids,
    )
    await SqlAlchemyDiscoverySeedRepository(session).add(seed)
    await session.commit()
    return {
        "id": str(seed.id),
        "target": seed.target,
        "label": seed.label,
        "enabled": seed.enabled,
    }


@discovery_router.delete("/seeds/{seed_id}")
async def delete_seed(
    seed_id: UUID,
    session: Annotated[AsyncSession, Depends(get_db)],
    _user: Annotated[Any, Depends(require_permission("discovery:write"))],
) -> dict[str, str]:
    await SqlAlchemyDiscoverySeedRepository(session).delete(seed_id)
    await session.commit()
    return {"status": "ok"}


@discovery_router.get("/jobs")
async def list_jobs(
    session: Annotated[AsyncSession, Depends(get_db)],
    _user: Annotated[Any, Depends(require_permission("discovery:read"))],
) -> list[dict[str, Any]]:
    jobs = await SqlAlchemyDiscoveryJobRepository(session).list()
    return [_job_dict(j) for j in jobs]


@discovery_router.post("/jobs", status_code=202)
async def start_job(
    body: JobCreate,
    session: Annotated[AsyncSession, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    _user: Annotated[Any, Depends(require_permission("discovery:write"))],
) -> dict[str, Any]:
    mode = (body.scan_mode or "deep").lower()
    if mode not in {"fast", "deep", "topology"}:
        raise HTTPException(status_code=400, detail="scan_mode must be fast|deep|topology")
    timeouts = {
        "fast": {"icmp_timeout": 0.4, "snmp_timeout": 1.5, "ssh_timeout": 10.0},
        "deep": {"icmp_timeout": 1.0, "snmp_timeout": 3.0, "ssh_timeout": 25.0},
        "topology": {"icmp_timeout": 0.8, "snmp_timeout": 2.5, "ssh_timeout": 20.0},
    }.get(mode, {"icmp_timeout": 1.0, "snmp_timeout": 2.0, "ssh_timeout": 20.0})
    job = DiscoveryJob(
        id=uuid4(),
        status=JobStatus.PENDING,
        started_at=None,
        finished_at=None,
        config={
            "seed_ids": [str(x) for x in body.seed_ids],
            "scan_mode": mode,
            "topology_discovery": mode in ("deep", "topology"),
            "deep_scan": mode == "deep",
            **timeouts,
            **(body.options or {}),
        },
        stats={},
    )
    await SqlAlchemyDiscoveryJobRepository(session).add(job)
    await session.commit()
    # Enqueue celery task when broker available; also support inline for dev.
    try:
        from netatlas.workers.tasks import run_discovery_job

        run_discovery_job.delay(str(job.id))
    except Exception:
        # Fallback: mark pending; operator can run worker
        pass
    return _job_dict(job)


@discovery_router.get("/jobs/{job_id}")
async def get_job(
    job_id: UUID,
    session: Annotated[AsyncSession, Depends(get_db)],
    _user: Annotated[Any, Depends(require_permission("discovery:read"))],
) -> dict[str, Any]:
    job = await SqlAlchemyDiscoveryJobRepository(session).get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return _job_dict(job)


def _job_dict(job: DiscoveryJob) -> dict[str, Any]:
    return {
        "id": str(job.id),
        "status": job.status.value,
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "finished_at": job.finished_at.isoformat() if job.finished_at else None,
        "stats": job.stats,
        "error": job.error,
        "config": {
            "scan_mode": (job.config or {}).get("scan_mode"),
            "seed_ids": (job.config or {}).get("seed_ids") or [],
            "topology_discovery": (job.config or {}).get("topology_discovery"),
            "deep_scan": (job.config or {}).get("deep_scan"),
        },
    }


@snapshots_router.get("")
async def list_snapshots(
    session: Annotated[AsyncSession, Depends(get_db)],
    _user: Annotated[Any, Depends(require_permission("snapshots:read"))],
) -> list[dict[str, Any]]:
    snaps = await SqlAlchemySnapshotRepository(session).list()
    return [
        {
            "id": str(s.id),
            "label": s.label,
            "created_at": s.created_at.isoformat() if s.created_at else None,
            "checksum": s.checksum,
            "summary": s.summary,
        }
        for s in snaps
    ]


@snapshots_router.get("/{snapshot_id}")
async def get_snapshot(
    snapshot_id: UUID,
    session: Annotated[AsyncSession, Depends(get_db)],
    _user: Annotated[Any, Depends(require_permission("snapshots:read"))],
) -> dict[str, Any]:
    snap = await SqlAlchemySnapshotRepository(session).get(snapshot_id)
    if not snap:
        raise HTTPException(status_code=404, detail="Snapshot not found")
    return {
        "id": str(snap.id),
        "label": snap.label,
        "created_at": snap.created_at.isoformat(),
        "checksum": snap.checksum,
        "summary": snap.summary,
        "payload": snap.payload,
    }


@snapshots_router.post("/diff")
async def diff_snapshots(
    body: SnapshotDiffRequest,
    session: Annotated[AsyncSession, Depends(get_db)],
    _user: Annotated[Any, Depends(require_permission("snapshots:read"))],
) -> dict[str, Any]:
    repo = SqlAlchemySnapshotRepository(session)
    left = await repo.get(body.left_id)
    right = await repo.get(body.right_id)
    if not left or not right:
        raise HTTPException(status_code=404, detail="Snapshot not found")
    return SnapshotComparer().compare(left.payload, right.payload)


@ipam_router.get("/prefixes")
async def list_prefixes(
    session: Annotated[AsyncSession, Depends(get_db)],
    _user: Annotated[Any, Depends(require_permission("ipam:read"))],
) -> list[dict[str, Any]]:
    prefixes = (await session.execute(select(IpPrefixModel))).scalars().all()
    result = []
    for p in prefixes:
        used = (
            await session.execute(
                select(func.count()).select_from(IpAddressModel).where(
                    IpAddressModel.prefix_id == p.id, IpAddressModel.status == "used"
                )
            )
        ).scalar_one()
        conflicts = (
            await session.execute(
                select(func.count()).select_from(IpAddressModel).where(
                    IpAddressModel.prefix_id == p.id, IpAddressModel.is_conflict.is_(True)
                )
            )
        ).scalar_one()
        net = ipaddress.ip_network(str(p.prefix), strict=False)
        total = net.num_addresses
        free = max(total - int(used), 0)
        result.append(
            {
                "id": str(p.id),
                "prefix": str(p.prefix),
                "description": p.description,
                "status": p.status,
                "used": int(used),
                "free": free,
                "conflicts": int(conflicts),
            }
        )
    return result


@ipam_router.post("/prefixes", status_code=201)
async def create_prefix(
    body: PrefixCreate,
    session: Annotated[AsyncSession, Depends(get_db)],
    _user: Annotated[Any, Depends(require_permission("ipam:write"))],
) -> dict[str, Any]:
    try:
        net = ipaddress.ip_network(body.prefix, strict=False)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    existing = (
        await session.execute(select(IpPrefixModel).where(IpPrefixModel.prefix == str(net)))
    ).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=409, detail="Prefix already exists")
    m = IpPrefixModel(id=uuid4(), prefix=str(net), description=body.description, status="active")
    session.add(m)
    await session.commit()
    return {
        "id": str(m.id),
        "prefix": str(m.prefix),
        "description": m.description,
        "status": m.status,
        "used": 0,
        "free": net.num_addresses,
        "conflicts": 0,
    }


@ipam_router.get("/prefixes/{prefix_id}/addresses")
async def list_addresses(
    prefix_id: UUID,
    session: Annotated[AsyncSession, Depends(get_db)],
    _user: Annotated[Any, Depends(require_permission("ipam:read"))],
    status: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
) -> dict[str, Any]:
    stmt = select(IpAddressModel).where(IpAddressModel.prefix_id == prefix_id)
    if status:
        stmt = stmt.where(IpAddressModel.status == status)
    total = (
        await session.execute(select(func.count()).select_from(stmt.subquery()))
    ).scalar_one()
    rows = (
        await session.execute(stmt.offset((page - 1) * page_size).limit(page_size))
    ).scalars().all()
    return {
        "items": [
            {
                "id": str(a.id),
                "address": str(a.address),
                "status": a.status,
                "mac": str(a.mac) if a.mac else None,
                "hostname": a.hostname,
                "is_conflict": a.is_conflict,
            }
            for a in rows
        ],
        "total": int(total),
        "page": page,
        "page_size": page_size,
    }


@ipam_router.get("/conflicts")
async def list_conflicts(
    session: Annotated[AsyncSession, Depends(get_db)],
    _user: Annotated[Any, Depends(require_permission("ipam:read"))],
) -> list[dict[str, Any]]:
    rows = (
        await session.execute(select(IpAddressModel).where(IpAddressModel.is_conflict.is_(True)))
    ).scalars().all()
    return [
        {
            "id": str(a.id),
            "address": str(a.address),
            "hostname": a.hostname,
            "mac": str(a.mac) if a.mac else None,
        }
        for a in rows
    ]


@export_router.post("")
async def export_topology(
    body: ExportRequest,
    session: Annotated[AsyncSession, Depends(get_db)],
    _user: Annotated[Any, Depends(require_permission("export:write"))],
) -> dict[str, Any]:
    from netatlas.api.routes.topology import topology_graph

    graph = await topology_graph(session, _user)
    exporter = TopologyExporter()
    content, content_type = exporter.export(
        format=body.format, nodes=graph["nodes"], edges=graph["edges"]
    )
    job_id = uuid4()
    # Persist to /tmp export cache path inside container volume in production.
    path = f"/tmp/netatlas-export-{job_id}.{body.format}"
    with open(path, "wb") as fh:
        fh.write(content)
    return {
        "id": str(job_id),
        "status": "completed",
        "download_url": f"/api/v1/export/{job_id}/download?format={body.format}",
        "content_type": content_type,
        "size": len(content),
    }


@export_router.get("/{job_id}/download")
async def download_export(
    job_id: UUID,
    format: str = "json",
    _user: Annotated[Any, Depends(require_permission("export:write"))] = None,
) -> Any:
    from fastapi.responses import FileResponse

    path = f"/tmp/netatlas-export-{job_id}.{format}"
    return FileResponse(path, filename=f"netatlas-{job_id}.{format}")


@credentials_router.get("")
async def list_credentials(
    session: Annotated[AsyncSession, Depends(get_db)],
    _user: Annotated[Any, Depends(require_permission("credentials:write"))],
) -> list[dict[str, Any]]:
    rows = (await session.execute(select(CredentialProfileModel))).scalars().all()
    return [
        {
            "id": str(r.id),
            "name": r.name,
            "protocol": r.protocol,
            "key_version": r.key_version,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]


@credentials_router.post("", status_code=201)
async def create_credential(
    body: CredentialCreate,
    session: Annotated[AsyncSession, Depends(get_db)],
    vault: Annotated[AesGcmSecretVault, Depends(get_vault)],
    _user: Annotated[Any, Depends(require_permission("credentials:write"))],
) -> dict[str, Any]:
    plaintext = json.dumps(body.secret).encode("utf-8")
    ciphertext, nonce, key_version = vault.encrypt(plaintext)
    m = CredentialProfileModel(
        id=uuid4(),
        name=body.name,
        protocol=body.protocol,
        ciphertext=ciphertext,
        nonce=nonce,
        key_version=key_version,
    )
    session.add(m)
    await session.commit()
    return {"id": str(m.id), "name": m.name, "protocol": m.protocol, "key_version": m.key_version}


@system_router.get("/healthz")
async def healthz(settings: Annotated[Settings, Depends(get_settings)]) -> dict[str, str]:
    return {"status": "ok", "version": settings.version}


@system_router.get("/readyz")
async def readyz(
    session: Annotated[AsyncSession, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict[str, Any]:
    checks: dict[str, str] = {}
    try:
        await session.execute(select(func.now()))
        checks["postgres"] = "ok"
    except Exception as exc:  # noqa: BLE001
        checks["postgres"] = f"error: {exc}"
    try:
        import redis.asyncio as redis

        client = redis.from_url(settings.redis_url)
        await client.ping()
        await client.aclose()
        checks["redis"] = "ok"
    except Exception as exc:  # noqa: BLE001
        checks["redis"] = f"error: {exc}"
    ok = all(v == "ok" for v in checks.values())
    if not ok:
        raise HTTPException(status_code=503, detail={"status": "not_ready", "checks": checks})
    return {"status": "ready", "checks": checks}


@vmware_router.get("/hosts")
async def vmware_hosts(
    session: Annotated[AsyncSession, Depends(get_db)],
    _user: Annotated[Any, Depends(require_permission("inventory:read"))],
) -> list[dict[str, Any]]:
    rows = (
        await session.execute(
            select(DeviceModel).where(DeviceModel.platform.in_(("esxi", "vsphere")))
        )
    ).scalars().all()
    return [
        {
            "id": str(d.id),
            "hostname": d.hostname,
            "management_ip": str(d.management_ip) if d.management_ip else None,
            "os_version": d.os_version,
            "platform": d.platform,
            "attributes": d.attributes,
        }
        for d in rows
    ]


@docker_router.get("/hosts")
async def docker_hosts(
    session: Annotated[AsyncSession, Depends(get_db)],
    _user: Annotated[Any, Depends(require_permission("inventory:read"))],
) -> list[dict[str, Any]]:
    rows = (
        await session.execute(select(DeviceModel).where(DeviceModel.platform == "docker_host"))
    ).scalars().all()
    return [
        {
            "id": str(d.id),
            "hostname": d.hostname,
            "management_ip": str(d.management_ip) if d.management_ip else None,
            "os_version": d.os_version,
        }
        for d in rows
    ]


@system_router.get("/stack/platforms")
async def stack_platforms(
    _user: Annotated[Any, Depends(require_permission("system:read"))] = None,
) -> dict[str, Any]:
    """Return the primary supported estate for UI badges/filters."""
    return {
        "primary": [
            {"id": "eltex", "vendor": "Eltex", "roles": ["switch", "router"]},
            {"id": "mikrotik", "vendor": "Mikrotik", "roles": ["router", "wireless", "cpe"]},
            {"id": "unifi", "vendor": "Ubiquiti UniFi", "roles": ["wifi", "switch", "gateway"]},
            {"id": "proxmox", "vendor": "Proxmox VE", "roles": ["hypervisor"]},
            {"id": "vsphere", "vendor": "VMware vSphere/ESXi", "roles": ["hypervisor"]},
            {"id": "ideco", "vendor": "Ideco", "roles": ["firewall", "utm"]},
            {"id": "kyocera", "vendor": "Kyocera", "roles": ["printer"]},
        ],
        "optional": [
            {"id": "linux", "vendor": "Linux"},
            {"id": "windows", "vendor": "Windows"},
            {"id": "docker_host", "vendor": "Docker"},
            {"id": "cisco_ios", "vendor": "Cisco IOS (legacy)"},
        ],
    }


async def discovery_ws(websocket: WebSocket, job_id: str) -> None:
    await websocket.accept()
    try:
        # Replay buffered events then poll.
        for event in _PROGRESS.get(job_id, []):
            await websocket.send_json(event)
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        return
