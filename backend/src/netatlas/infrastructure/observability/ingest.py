"""Persist syslog events and run lightweight SIEM correlation."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from netatlas.config import Settings
from netatlas.infrastructure.observability.syslog_parser import ParsedSyslog, categorize_message, parse_syslog
from netatlas.infrastructure.persistence.models import (
    DeviceModel,
    ObservabilityEventModel,
    SiemCorrelationHitModel,
)

logger = logging.getLogger(__name__)


class SyslogIngestService:
    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self._session = session
        self._settings = settings

    async def ingest(
        self,
        raw: str,
        *,
        source_ip: str | None,
        received_at: datetime | None = None,
    ) -> ObservabilityEventModel:
        received = received_at or datetime.now(UTC)
        parsed = parse_syslog(raw, received_at=received)
        category, tags = categorize_message(parsed.message, severity=parsed.severity, app_name=parsed.app_name)
        device_id = await self._resolve_device(source_ip, parsed.hostname)
        event = ObservabilityEventModel(
            id=uuid4(),
            device_id=device_id,
            source_ip=source_ip,
            received_at=received,
            event_at=parsed.event_at,
            facility=parsed.facility,
            severity=parsed.severity,
            hostname=parsed.hostname,
            app_name=parsed.app_name,
            proc_id=parsed.proc_id,
            msg_id=parsed.msg_id,
            message=parsed.message,
            raw=parsed.raw,
            category=category,
            tags=tags,
            extras=parsed.extras,
        )
        self._session.add(event)
        await self._session.flush()
        await self._correlate(event)
        return event

    async def purge_expired(self) -> int:
        cutoff = datetime.now(UTC) - timedelta(days=self._settings.syslog_retention_days)
        result = await self._session.execute(
            delete(ObservabilityEventModel).where(ObservabilityEventModel.received_at < cutoff)
        )
        return int(result.rowcount or 0)

    async def _resolve_device(self, source_ip: str | None, hostname: str | None) -> UUID | None:
        if source_ip:
            row = (
                await self._session.execute(
                    select(DeviceModel).where(DeviceModel.management_ip == source_ip)
                )
            ).scalar_one_or_none()
            if row:
                return row.id
        if hostname:
            row = (
                await self._session.execute(
                    select(DeviceModel).where(func.lower(DeviceModel.hostname) == hostname.lower())
                )
            ).scalar_one_or_none()
            if row:
                return row.id
        return None

    async def _correlate(self, event: ObservabilityEventModel) -> None:
        """Partial SIEM: auth failure bursts from same source."""
        if event.category != "auth_failure" or not event.source_ip:
            return
        window = datetime.now(UTC) - timedelta(seconds=self._settings.siem_correlation_window_seconds)
        rows = (
            await self._session.execute(
                select(ObservabilityEventModel.id)
                .where(
                    ObservabilityEventModel.category == "auth_failure",
                    ObservabilityEventModel.source_ip == event.source_ip,
                    ObservabilityEventModel.received_at >= window,
                )
                .limit(50)
            )
        ).scalars().all()
        if len(rows) < 5:
            return
        self._session.add(
            SiemCorrelationHitModel(
                id=uuid4(),
                rule_name="auth_failure_burst",
                title=f"Authentication failure burst from {event.source_ip}",
                severity="high",
                source_ip=str(event.source_ip),
                device_id=event.device_id,
                event_ids=[str(x) for x in rows],
                details={"count": len(rows), "window_seconds": self._settings.siem_correlation_window_seconds},
            )
        )
        await self._session.flush()
