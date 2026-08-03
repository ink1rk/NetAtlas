"""Outbound SMTP notifier for trigger PROBLEM/OK events."""

from __future__ import annotations

import asyncio
import logging
import smtplib
import ssl
from datetime import UTC, datetime
from email.message import EmailMessage
from typing import Any
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from netatlas.config import Settings
from netatlas.infrastructure.persistence.models import (
    AlertNotificationModel,
    TriggerDefinitionModel,
    TriggerEventModel,
)

logger = logging.getLogger(__name__)


class SmtpNotifier:
    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self._session = session
        self._settings = settings

    @property
    def configured(self) -> bool:
        return bool(self._settings.smtp_host and self._settings.alert_mail_to)

    async def notify_trigger(self, trigger: TriggerDefinitionModel, event: TriggerEventModel) -> None:
        if not self.configured:
            logger.debug("SMTP not configured; skip notify for %s", trigger.name)
            return
        subject = f"[NetAtlas][{event.event_type}][{trigger.severity.upper()}] {trigger.name}"
        body = (
            f"Trigger: {trigger.name}\n"
            f"Event: {event.event_type}\n"
            f"Severity: {trigger.severity}\n"
            f"Message: {event.message}\n"
            f"Value: {event.value}\n"
            f"Time (UTC): {event.created_at.isoformat() if event.created_at else datetime.now(UTC).isoformat()}\n"
        )
        destinations = [x.strip() for x in self._settings.alert_mail_to.split(",") if x.strip()]
        for dest in destinations:
            note = AlertNotificationModel(
                id=uuid4(),
                trigger_event_id=event.id,
                channel="smtp",
                destination=dest,
                subject=subject,
                body=body,
                status="pending",
            )
            self._session.add(note)
            await self._session.flush()
            try:
                await asyncio.to_thread(self._send, dest, subject, body)
                note.status = "sent"
                note.sent_at = datetime.now(UTC)
            except Exception as exc:  # noqa: BLE001
                logger.exception("SMTP send failed")
                note.status = "failed"
                note.error = str(exc)
            await self._session.flush()

    def _send(self, destination: str, subject: str, body: str) -> None:
        msg = EmailMessage()
        msg["From"] = self._settings.smtp_from
        msg["To"] = destination
        msg["Subject"] = subject
        msg.set_content(body)

        password = self._settings.smtp_password.get_secret_value()
        if self._settings.smtp_use_ssl:
            context = ssl.create_default_context()
            with smtplib.SMTP_SSL(
                self._settings.smtp_host, self._settings.smtp_port, context=context, timeout=30
            ) as smtp:
                if self._settings.smtp_username:
                    smtp.login(self._settings.smtp_username, password)
                smtp.send_message(msg)
            return

        with smtplib.SMTP(self._settings.smtp_host, self._settings.smtp_port, timeout=30) as smtp:
            smtp.ehlo()
            if self._settings.smtp_use_tls:
                context = ssl.create_default_context()
                smtp.starttls(context=context)
                smtp.ehlo()
            if self._settings.smtp_username:
                smtp.login(self._settings.smtp_username, password)
            smtp.send_message(msg)
