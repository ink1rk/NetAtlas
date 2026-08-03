"""Observability API: syslog search, triggers, alerts, SIEM hits."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from netatlas.api.deps import CurrentUser, get_db, require_permission
from netatlas.config import Settings, get_settings
from netatlas.infrastructure.persistence.models import (
    AlertNotificationModel,
    ObservabilityEventModel,
    SiemCorrelationHitModel,
    TriggerDefinitionModel,
    TriggerEventModel,
)

router = APIRouter(prefix="/observability", tags=["observability"])


class TriggerCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    enabled: bool = True
    severity: str = "warning"
    kind: str
    expression: dict[str, Any] = Field(default_factory=dict)
    recovery_expression: dict[str, Any] | None = None
    notify_smtp: bool = True
    notify_telegram: bool = True
    notify_element: bool = True
    device_id: UUID | None = None


class TriggerUpdate(BaseModel):
    description: str | None = None
    enabled: bool | None = None
    severity: str | None = None
    expression: dict[str, Any] | None = None
    recovery_expression: dict[str, Any] | None = None
    notify_smtp: bool | None = None
    notify_telegram: bool | None = None
    notify_element: bool | None = None


@router.get("/events")
async def list_events(
    session: Annotated[AsyncSession, Depends(get_db)],
    _user: Annotated[Any, Depends(require_permission("observability:read"))],
    q: str | None = None,
    category: str | None = None,
    source_ip: str | None = None,
    severity_max: int | None = Query(None, ge=0, le=7),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
) -> dict[str, Any]:
    stmt = select(ObservabilityEventModel)
    count_stmt = select(func.count()).select_from(ObservabilityEventModel)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(ObservabilityEventModel.message.ilike(like))
        count_stmt = count_stmt.where(ObservabilityEventModel.message.ilike(like))
    if category:
        stmt = stmt.where(ObservabilityEventModel.category == category)
        count_stmt = count_stmt.where(ObservabilityEventModel.category == category)
    if source_ip:
        stmt = stmt.where(ObservabilityEventModel.source_ip == source_ip)
        count_stmt = count_stmt.where(ObservabilityEventModel.source_ip == source_ip)
    if severity_max is not None:
        stmt = stmt.where(ObservabilityEventModel.severity <= severity_max)
        count_stmt = count_stmt.where(ObservabilityEventModel.severity <= severity_max)
    total = int((await session.execute(count_stmt)).scalar_one())
    rows = (
        await session.execute(
            stmt.order_by(ObservabilityEventModel.received_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).scalars().all()
    return {
        "items": [_event_dict(r) for r in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/triggers")
async def list_triggers(
    session: Annotated[AsyncSession, Depends(get_db)],
    _user: Annotated[Any, Depends(require_permission("observability:read"))],
) -> list[dict[str, Any]]:
    rows = (
        await session.execute(select(TriggerDefinitionModel).order_by(TriggerDefinitionModel.name))
    ).scalars().all()
    return [_trigger_dict(r) for r in rows]


@router.post("/triggers", status_code=201)
async def create_trigger(
    body: TriggerCreate,
    session: Annotated[AsyncSession, Depends(get_db)],
    _user: Annotated[Any, Depends(require_permission("observability:write"))],
) -> dict[str, Any]:
    existing = (
        await session.execute(select(TriggerDefinitionModel).where(TriggerDefinitionModel.name == body.name))
    ).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=409, detail="Trigger name already exists")
    row = TriggerDefinitionModel(
        id=uuid4(),
        name=body.name,
        description=body.description,
        enabled=body.enabled,
        severity=body.severity,
        kind=body.kind,
        expression=body.expression,
        recovery_expression=body.recovery_expression,
        notify_smtp=body.notify_smtp,
        notify_telegram=body.notify_telegram,
        notify_element=body.notify_element,
        device_id=body.device_id,
        status="ok",
    )
    session.add(row)
    await session.commit()
    return _trigger_dict(row)


@router.patch("/triggers/{trigger_id}")
async def update_trigger(
    trigger_id: UUID,
    body: TriggerUpdate,
    session: Annotated[AsyncSession, Depends(get_db)],
    _user: Annotated[Any, Depends(require_permission("observability:write"))],
) -> dict[str, Any]:
    row = await session.get(TriggerDefinitionModel, trigger_id)
    if not row:
        raise HTTPException(status_code=404, detail="Trigger not found")
    data = body.model_dump(exclude_unset=True)
    for key, value in data.items():
        setattr(row, key, value)
    await session.commit()
    return _trigger_dict(row)


@router.delete("/triggers/{trigger_id}")
async def delete_trigger(
    trigger_id: UUID,
    session: Annotated[AsyncSession, Depends(get_db)],
    _user: Annotated[Any, Depends(require_permission("observability:write"))],
) -> dict[str, str]:
    row = await session.get(TriggerDefinitionModel, trigger_id)
    if not row:
        raise HTTPException(status_code=404, detail="Trigger not found")
    await session.delete(row)
    await session.commit()
    return {"status": "ok"}


@router.get("/alerts")
async def list_alerts(
    session: Annotated[AsyncSession, Depends(get_db)],
    _user: Annotated[Any, Depends(require_permission("observability:read"))],
    event_type: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
) -> dict[str, Any]:
    stmt = select(TriggerEventModel)
    if event_type:
        stmt = stmt.where(TriggerEventModel.event_type == event_type.upper())
    total = int(
        (
            await session.execute(select(func.count()).select_from(stmt.subquery()))
        ).scalar_one()
    )
    rows = (
        await session.execute(
            stmt.order_by(TriggerEventModel.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).scalars().all()
    return {
        "items": [
            {
                "id": str(r.id),
                "trigger_id": str(r.trigger_id),
                "event_type": r.event_type,
                "severity": r.severity,
                "message": r.message,
                "value": r.value,
                "acknowledged": r.acknowledged,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.post("/alerts/{alert_id}/ack")
async def ack_alert(
    alert_id: UUID,
    session: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(require_permission("observability:write"))],
) -> dict[str, Any]:
    row = await session.get(TriggerEventModel, alert_id)
    if not row:
        raise HTTPException(status_code=404, detail="Alert not found")
    row.acknowledged = True
    row.acknowledged_at = datetime.now(UTC)
    row.acknowledged_by = user.id
    await session.commit()
    return {"id": str(row.id), "acknowledged": True}


@router.get("/siem/hits")
async def siem_hits(
    session: Annotated[AsyncSession, Depends(get_db)],
    _user: Annotated[Any, Depends(require_permission("observability:read"))],
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
) -> dict[str, Any]:
    total = int(
        (await session.execute(select(func.count()).select_from(SiemCorrelationHitModel))).scalar_one()
    )
    rows = (
        await session.execute(
            select(SiemCorrelationHitModel)
            .order_by(SiemCorrelationHitModel.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).scalars().all()
    return {
        "items": [
            {
                "id": str(r.id),
                "rule_name": r.rule_name,
                "title": r.title,
                "severity": r.severity,
                "source_ip": str(r.source_ip) if r.source_ip else None,
                "device_id": str(r.device_id) if r.device_id else None,
                "details": r.details,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/notifications")
async def list_notifications(
    session: Annotated[AsyncSession, Depends(get_db)],
    _user: Annotated[Any, Depends(require_permission("observability:read"))],
) -> list[dict[str, Any]]:
    rows = (
        await session.execute(
            select(AlertNotificationModel).order_by(AlertNotificationModel.created_at.desc()).limit(100)
        )
    ).scalars().all()
    return [
        {
            "id": str(r.id),
            "channel": r.channel,
            "destination": r.destination,
            "subject": r.subject,
            "status": r.status,
            "error": r.error,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "sent_at": r.sent_at.isoformat() if r.sent_at else None,
        }
        for r in rows
    ]


@router.get("/status")
async def observability_status(
    session: Annotated[AsyncSession, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    _user: Annotated[Any, Depends(require_permission("observability:read"))],
) -> dict[str, Any]:
    from netatlas.infrastructure.observability.dispatcher import NotificationDispatcher

    events = int((await session.execute(select(func.count()).select_from(ObservabilityEventModel))).scalar_one())
    problems = int(
        (
            await session.execute(
                select(func.count()).select_from(TriggerDefinitionModel).where(
                    TriggerDefinitionModel.status == "problem"
                )
            )
        ).scalar_one()
    )
    channels = NotificationDispatcher(session, settings).channel_status()
    return {
        "syslog": {
            "udp_port": settings.syslog_udp_port,
            "tcp_port": settings.syslog_tcp_port,
            "tls_enabled": settings.syslog_tls_enable,
            "tls_port": settings.syslog_tls_port if settings.syslog_tls_enable else None,
            "retention_days": settings.syslog_retention_days,
        },
        "channels": channels,
        "smtp_configured": channels["smtp"],
        "telegram_configured": channels["telegram"],
        "element_configured": channels["element"],
        "events_stored": events,
        "triggers_in_problem": problems,
    }


def _event_dict(r: ObservabilityEventModel) -> dict[str, Any]:
    return {
        "id": str(r.id),
        "device_id": str(r.device_id) if r.device_id else None,
        "source_ip": str(r.source_ip) if r.source_ip else None,
        "received_at": r.received_at.isoformat() if r.received_at else None,
        "event_at": r.event_at.isoformat() if r.event_at else None,
        "facility": r.facility,
        "severity": r.severity,
        "hostname": r.hostname,
        "app_name": r.app_name,
        "message": r.message,
        "category": r.category,
        "tags": r.tags or [],
    }


def _trigger_dict(r: TriggerDefinitionModel) -> dict[str, Any]:
    return {
        "id": str(r.id),
        "name": r.name,
        "description": r.description,
        "enabled": r.enabled,
        "severity": r.severity,
        "kind": r.kind,
        "expression": r.expression,
        "recovery_expression": r.recovery_expression,
        "notify_smtp": r.notify_smtp,
        "notify_telegram": getattr(r, "notify_telegram", True),
        "notify_element": getattr(r, "notify_element", True),
        "status": r.status,
        "last_change_at": r.last_change_at.isoformat() if r.last_change_at else None,
        "last_value": r.last_value,
        "device_id": str(r.device_id) if r.device_id else None,
    }
