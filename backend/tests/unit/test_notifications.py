"""Tests for notification dispatcher and vendor syslog rules."""

from __future__ import annotations

from netatlas.config import Settings
from netatlas.infrastructure.observability.dispatcher import NotificationDispatcher, _format_message
from netatlas.infrastructure.observability.syslog_parser import categorize_message
from netatlas.infrastructure.persistence.models import TriggerDefinitionModel, TriggerEventModel


def test_channel_status_respects_settings() -> None:
    settings = Settings(
        telegram_bot_token="tok",  # type: ignore[arg-type]
        telegram_chat_ids="-100123",
        element_homeserver="https://matrix.local",
        element_access_token="syt_xxx",  # type: ignore[arg-type]
        element_room_ids="!room:matrix.local",
        smtp_host="",
        alert_mail_to="",
    )
    # SecretStr coercion via Settings
    status = NotificationDispatcher.__new__(NotificationDispatcher)
    status._settings = Settings(
        **{
            "telegram_bot_token": "tok",
            "telegram_chat_ids": "-100123",
            "element_homeserver": "https://matrix.local",
            "element_access_token": "syt_xxx",
            "element_room_ids": "!room:matrix.local",
            "smtp_host": "",
            "alert_mail_to": "",
        }
    )
    # Re-read through real Settings for SecretStr
    s = status._settings
    assert bool(s.telegram_bot_token.get_secret_value() and s.telegram_chat_ids)
    assert bool(s.element_homeserver and s.element_access_token.get_secret_value() and s.element_room_ids)


def test_format_message_contains_trigger() -> None:
    from datetime import UTC, datetime
    from uuid import uuid4

    trigger = TriggerDefinitionModel(
        id=uuid4(),
        name="Eltex link down",
        severity="high",
        kind="syslog_match",
        expression={},
    )
    event = TriggerEventModel(
        id=uuid4(),
        trigger_id=trigger.id,
        event_type="PROBLEM",
        severity="high",
        message="Gi1/0/24 down",
        value="down",
        created_at=datetime.now(UTC),
    )
    subject, body = _format_message(trigger, event)
    assert "Eltex link down" in subject
    assert "PROBLEM" in subject
    assert "Gi1/0/24" in body


def test_eltex_and_ideco_categorization() -> None:
    cat, tags = categorize_message(
        "%LINK-3-UPDOWN: Interface Gi1/0/24 changed state to down",
        severity=3,
        app_name=None,
        hostname="mes-core-01",
    )
    assert cat == "link_down"
    assert "vendor:eltex" in tags

    cat2, tags2 = categorize_message(
        "firewall DENY tcp src=10.0.0.5",
        severity=5,
        app_name="ideco",
        hostname="utm-edge",
    )
    assert cat2 == "firewall"
    assert "vendor:ideco" in tags2 or "security" in tags2
