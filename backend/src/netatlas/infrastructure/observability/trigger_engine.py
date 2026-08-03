"""Zabbix-like trigger evaluation engine."""

from __future__ import annotations

import logging
import re
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from netatlas.infrastructure.persistence.models import (
    DeviceMetricModel,
    DeviceModel,
    InterfaceModel,
    ObservabilityEventModel,
    TriggerDefinitionModel,
    TriggerEventModel,
)
from netatlas.infrastructure.observability.smtp_notifier import SmtpNotifier

logger = logging.getLogger(__name__)


class TriggerEngine:
    def __init__(self, session: AsyncSession, notifier: SmtpNotifier | None = None) -> None:
        self._session = session
        self._notifier = notifier

    async def evaluate_all(self) -> dict[str, int]:
        triggers = (
            await self._session.execute(
                select(TriggerDefinitionModel).where(TriggerDefinitionModel.enabled.is_(True))
            )
        ).scalars().all()
        stats = {"evaluated": 0, "problems": 0, "recovered": 0}
        for trigger in triggers:
            stats["evaluated"] += 1
            problem, value, message = await self._eval_one(trigger)
            changed = await self._apply_state(trigger, problem=problem, value=value, message=message)
            if changed == "PROBLEM":
                stats["problems"] += 1
            elif changed == "OK":
                stats["recovered"] += 1
        return stats

    async def evaluate_syslog_event(self, event: ObservabilityEventModel) -> None:
        triggers = (
            await self._session.execute(
                select(TriggerDefinitionModel).where(
                    TriggerDefinitionModel.enabled.is_(True),
                    TriggerDefinitionModel.kind == "syslog_match",
                )
            )
        ).scalars().all()
        for trigger in triggers:
            expr = trigger.expression or {}
            if trigger.device_id and event.device_id and trigger.device_id != event.device_id:
                continue
            if expr.get("category") and expr["category"] != event.category:
                continue
            if expr.get("min_severity") is not None and (event.severity or 7) > int(expr["min_severity"]):
                continue
            pattern = expr.get("regex")
            if pattern and not re.search(pattern, event.message or "", re.I):
                continue
            source_re = expr.get("source_ip_regex")
            if source_re and event.source_ip and not re.search(source_re, str(event.source_ip)):
                continue
            await self._apply_state(
                trigger,
                problem=True,
                value=event.message[:500],
                message=f"Syslog match on {event.hostname or event.source_ip}: {event.message[:200]}",
            )

    async def _eval_one(self, trigger: TriggerDefinitionModel) -> tuple[bool, str | None, str]:
        kind = trigger.kind
        expr = trigger.expression or {}
        if kind == "metric_threshold":
            return await self._eval_metric(trigger, expr)
        if kind == "interface_status":
            return await self._eval_interface(trigger, expr)
        if kind == "absence":
            return await self._eval_absence(trigger, expr)
        if kind == "siem_correlation":
            return await self._eval_siem(trigger, expr)
        if kind == "syslog_match":
            # evaluated on ingest path; keep current state during periodic pass
            return trigger.status == "problem", trigger.last_value, trigger.description or trigger.name
        return False, None, f"Unknown trigger kind {kind}"

    async def _eval_metric(
        self, trigger: TriggerDefinitionModel, expr: dict[str, Any]
    ) -> tuple[bool, str | None, str]:
        metric = expr.get("metric", "cpu_percent")
        op = expr.get("op", "gt")
        threshold = float(expr.get("threshold", 90))
        minutes = int(expr.get("for_minutes", 5))
        since = datetime.now(UTC) - timedelta(minutes=minutes)
        stmt = select(DeviceMetricModel).where(DeviceMetricModel.collected_at >= since)
        if trigger.device_id:
            stmt = stmt.where(DeviceMetricModel.device_id == trigger.device_id)
        rows = (await self._session.execute(stmt.order_by(DeviceMetricModel.collected_at.desc()).limit(50))).scalars().all()
        if not rows:
            return False, None, "No metric samples"
        values = []
        for row in rows:
            val = getattr(row, metric, None)
            if val is None and isinstance(row.extras, dict):
                val = row.extras.get(metric)
            if val is not None:
                values.append(float(val))
        if not values:
            return False, None, f"Metric {metric} missing"
        current = values[0]
        ok_cmp = {
            "gt": current > threshold,
            "gte": current >= threshold,
            "lt": current < threshold,
            "lte": current <= threshold,
            "eq": current == threshold,
        }.get(op, current > threshold)
        return ok_cmp, str(current), f"{metric}={current} {op} {threshold}"

    async def _eval_interface(
        self, trigger: TriggerDefinitionModel, expr: dict[str, Any]
    ) -> tuple[bool, str | None, str]:
        name = expr.get("interface")
        stmt = select(InterfaceModel)
        if trigger.device_id:
            stmt = stmt.where(InterfaceModel.device_id == trigger.device_id)
        if name:
            stmt = stmt.where(InterfaceModel.name == name)
        rows = (await self._session.execute(stmt)).scalars().all()
        down = [r for r in rows if (r.oper_status or "").lower() == "down" and (r.admin_status or "").lower() == "up"]
        if down:
            names = ", ".join(r.name for r in down[:5])
            return True, names, f"Interface(s) down: {names}"
        return False, "up", "All watched interfaces up"

    async def _eval_absence(
        self, trigger: TriggerDefinitionModel, expr: dict[str, Any]
    ) -> tuple[bool, str | None, str]:
        minutes = int(expr.get("for_minutes", 15))
        since = datetime.now(UTC) - timedelta(minutes=minutes)
        stmt = select(func.count()).select_from(ObservabilityEventModel).where(
            ObservabilityEventModel.received_at >= since
        )
        if trigger.device_id:
            stmt = stmt.where(ObservabilityEventModel.device_id == trigger.device_id)
        source_ip = expr.get("source_ip")
        if source_ip:
            stmt = stmt.where(ObservabilityEventModel.source_ip == source_ip)
        count = int((await self._session.execute(stmt)).scalar_one())
        problem = count == 0
        return problem, str(count), f"Events in last {minutes}m: {count}"

    async def _eval_siem(
        self, trigger: TriggerDefinitionModel, expr: dict[str, Any]
    ) -> tuple[bool, str | None, str]:
        category = expr.get("category", "auth_failure")
        threshold = int(expr.get("count", 5))
        minutes = int(expr.get("for_minutes", 5))
        since = datetime.now(UTC) - timedelta(minutes=minutes)
        stmt = select(func.count()).select_from(ObservabilityEventModel).where(
            ObservabilityEventModel.category == category,
            ObservabilityEventModel.received_at >= since,
        )
        if trigger.device_id:
            stmt = stmt.where(ObservabilityEventModel.device_id == trigger.device_id)
        count = int((await self._session.execute(stmt)).scalar_one())
        return count >= threshold, str(count), f"{category} count={count} threshold={threshold}"

    async def _apply_state(
        self,
        trigger: TriggerDefinitionModel,
        *,
        problem: bool,
        value: str | None,
        message: str,
    ) -> str | None:
        desired = "problem" if problem else "ok"
        trigger.last_value = value
        if trigger.status == desired:
            return None
        previous = trigger.status
        trigger.status = desired
        trigger.last_change_at = datetime.now(UTC)
        event_type = "PROBLEM" if problem else "OK"
        te = TriggerEventModel(
            id=uuid4(),
            trigger_id=trigger.id,
            event_type=event_type,
            severity=trigger.severity,
            message=message,
            value=value,
            extras={"previous": previous},
        )
        self._session.add(te)
        await self._session.flush()
        if trigger.notify_smtp and self._notifier:
            await self._notifier.notify_trigger(trigger, te)
        logger.info("Trigger %s -> %s (%s)", trigger.name, event_type, message)
        return event_type
