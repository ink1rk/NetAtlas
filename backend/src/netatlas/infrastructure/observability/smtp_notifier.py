"""Backward-compatible re-export — use NotificationDispatcher."""

from netatlas.infrastructure.observability.dispatcher import NotificationDispatcher, SmtpNotifier

__all__ = ["NotificationDispatcher", "SmtpNotifier"]
