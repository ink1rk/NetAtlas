"""Multi-channel alert dispatcher: SMTP, Telegram, Element (Matrix)."""

from __future__ import annotations

import asyncio
import logging
import smtplib
import ssl
import uuid
from datetime import UTC, datetime
from email.message import EmailMessage
from typing import Any
from urllib.parse import quote
from uuid import uuid4

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from netatlas.config import Settings
from netatlas.infrastructure.persistence.models import (
    AlertNotificationModel,
    TriggerDefinitionModel,
    TriggerEventModel,
)

logger = logging.getLogger(__name__)


class NotificationDispatcher:
    """Fan-out PROBLEM/OK notifications to all enabled local/self-hosted channels."""

    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self._session = session
        self._settings = settings

    def channel_status(self) -> dict[str, bool]:
        return {
            "smtp": bool(self._settings.smtp_host and self._settings.alert_mail_to),
            "telegram": bool(
                self._settings.telegram_bot_token.get_secret_value()
                and self._settings.telegram_chat_ids
            ),
            "element": bool(
                self._settings.element_homeserver
                and self._settings.element_access_token.get_secret_value()
                and self._settings.element_room_ids
            ),
        }

    async def notify_trigger(self, trigger: TriggerDefinitionModel, event: TriggerEventModel) -> None:
        subject, body = _format_message(trigger, event)
        status = self.channel_status()
        tasks: list[tuple[str, str, Any]] = []

        if getattr(trigger, "notify_smtp", True) and status["smtp"]:
            for dest in _split(self._settings.alert_mail_to):
                tasks.append(("smtp", dest, lambda d=dest: self._send_smtp(d, subject, body)))

        if getattr(trigger, "notify_telegram", True) and status["telegram"]:
            for chat_id in _split(self._settings.telegram_chat_ids):
                tasks.append(
                    ("telegram", chat_id, lambda c=chat_id: self._send_telegram(c, body))
                )

        if getattr(trigger, "notify_element", True) and status["element"]:
            for room_id in _split(self._settings.element_room_ids):
                tasks.append(
                    ("element", room_id, lambda r=room_id: self._send_element(r, body))
                )

        if not tasks:
            logger.debug("No notification channels configured/enabled for %s", trigger.name)
            return

        for channel, destination, sender in tasks:
            note = AlertNotificationModel(
                id=uuid4(),
                trigger_event_id=event.id,
                channel=channel,
                destination=destination,
                subject=subject,
                body=body,
                status="pending",
            )
            self._session.add(note)
            await self._session.flush()
            try:
                await sender()
                note.status = "sent"
                note.sent_at = datetime.now(UTC)
            except Exception as exc:  # noqa: BLE001
                logger.exception("%s notify failed dest=%s", channel, destination)
                note.status = "failed"
                note.error = str(exc)
            await self._session.flush()

    async def _send_smtp(self, destination: str, subject: str, body: str) -> None:
        await asyncio.to_thread(self._smtp_sync, destination, subject, body)

    def _smtp_sync(self, destination: str, subject: str, body: str) -> None:
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

    async def _send_telegram(self, chat_id: str, body: str) -> None:
        token = self._settings.telegram_bot_token.get_secret_value()
        # Telegram requires egress to api.telegram.org unless a local Bot API server is set.
        base = (self._settings.telegram_api_base or "https://api.telegram.org").rstrip("/")
        url = f"{base}/bot{token}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": body[:4000],
            "disable_web_page_preview": True,
        }
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            data = resp.json()
            if not data.get("ok", True) and "ok" in data:
                raise RuntimeError(f"Telegram API error: {data}")

    async def _send_element(self, room_id: str, body: str) -> None:
        """Send m.room.message via Matrix Client-Server API (Element / Synapse / Dendrite)."""
        homeserver = self._settings.element_homeserver.rstrip("/")
        token = self._settings.element_access_token.get_secret_value()
        txn_id = uuid.uuid4().hex
        encoded_room = quote(room_id, safe="")
        url = f"{homeserver}/_matrix/client/v3/rooms/{encoded_room}/send/m.room.message/{txn_id}"
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        payload = {"msgtype": "m.text", "body": body[:60000]}
        verify = self._settings.element_verify_tls
        async with httpx.AsyncClient(timeout=30.0, verify=verify) as client:
            resp = await client.put(url, headers=headers, json=payload)
            resp.raise_for_status()


# Backward-compatible alias used by existing imports
class SmtpNotifier(NotificationDispatcher):
    """Deprecated name — use NotificationDispatcher."""

    @property
    def configured(self) -> bool:
        return any(self.channel_status().values())


def _format_message(trigger: TriggerDefinitionModel, event: TriggerEventModel) -> tuple[str, str]:
    subject = f"[NetAtlas][{event.event_type}][{trigger.severity.upper()}] {trigger.name}"
    body = (
        f"NetAtlas alert\n"
        f"Trigger: {trigger.name}\n"
        f"Event: {event.event_type}\n"
        f"Severity: {trigger.severity}\n"
        f"Message: {event.message}\n"
        f"Value: {event.value}\n"
        f"Time (UTC): {event.created_at.isoformat() if event.created_at else datetime.now(UTC).isoformat()}\n"
    )
    return subject, body


def _split(value: str) -> list[str]:
    return [part.strip() for part in (value or "").split(",") if part.strip()]
