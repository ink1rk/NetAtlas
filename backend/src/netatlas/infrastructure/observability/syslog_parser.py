"""Syslog parsers for RFC3164 and RFC5424."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any


_RFC5424 = re.compile(
    r"^<(?P<pri>\d+)>"
    r"(?P<version>\d+)\s+"
    r"(?P<timestamp>\S+)\s+"
    r"(?P<hostname>\S+)\s+"
    r"(?P<app>\S+)\s+"
    r"(?P<proc>\S+)\s+"
    r"(?P<msgid>\S+)\s+"
    r"(?P<rest>.*)$"
)
_RFC3164 = re.compile(
    r"^<(?P<pri>\d+)>"
    r"(?P<timestamp>[A-Z][a-z]{2}\s+\d{1,2}\s+\d{2}:\d{2}:\d{2})\s+"
    r"(?P<hostname>\S+)\s+"
    r"(?P<message>.*)$"
)


@dataclass(slots=True)
class ParsedSyslog:
    facility: int
    severity: int
    hostname: str | None
    app_name: str | None
    proc_id: str | None
    msg_id: str | None
    message: str
    event_at: datetime | None
    raw: str
    extras: dict[str, Any]


def parse_syslog(raw: str, *, received_at: datetime | None = None) -> ParsedSyslog:
    text = raw.strip("\x00").strip()
    received = received_at or datetime.now(UTC)
    m5424 = _RFC5424.match(text)
    if m5424:
        pri = int(m5424.group("pri"))
        facility, severity = divmod(pri, 8)
        ts = _parse_ts(m5424.group("timestamp"), received)
        rest = m5424.group("rest")
        # Structured data may precede message
        message = rest
        if rest.startswith("["):
            # skip SD elements best-effort
            idx = rest.rfind("] ")
            if idx != -1:
                message = rest[idx + 2 :]
            elif rest.endswith("]"):
                message = ""
        return ParsedSyslog(
            facility=facility,
            severity=severity,
            hostname=_nil(m5424.group("hostname")),
            app_name=_nil(m5424.group("app")),
            proc_id=_nil(m5424.group("proc")),
            msg_id=_nil(m5424.group("msgid")),
            message=message or text,
            event_at=ts,
            raw=text,
            extras={"format": "rfc5424", "version": m5424.group("version")},
        )

    m3164 = _RFC3164.match(text)
    if m3164:
        pri = int(m3164.group("pri"))
        facility, severity = divmod(pri, 8)
        ts = _parse_bsd_ts(m3164.group("timestamp"), received)
        return ParsedSyslog(
            facility=facility,
            severity=severity,
            hostname=m3164.group("hostname"),
            app_name=None,
            proc_id=None,
            msg_id=None,
            message=m3164.group("message"),
            event_at=ts,
            raw=text,
            extras={"format": "rfc3164"},
        )

    # Bare message fallback
    return ParsedSyslog(
        facility=1,
        severity=6,
        hostname=None,
        app_name=None,
        proc_id=None,
        msg_id=None,
        message=text,
        event_at=received,
        raw=text,
        extras={"format": "raw"},
    )


def categorize_message(
    message: str,
    *,
    severity: int,
    app_name: str | None,
    hostname: str | None = None,
) -> tuple[str, list[str]]:
    """Lightweight SIEM categorization with Ideco/Eltex/Mikrotik/UniFi hints."""
    lower = message.lower()
    host = (hostname or "").lower()
    app = (app_name or "").lower()
    tags: list[str] = []
    category = "syslog"

    # Vendor hints from hostname / app
    if any(x in host for x in ("ideco", "utm", "fw")) or "ideco" in app:
        tags.append("vendor:ideco")
    if any(x in host for x in ("mes", "eltex", "esr")) or "eltex" in app:
        tags.append("vendor:eltex")
    if "mikrotik" in host or "routeros" in app or host.startswith("mt-"):
        tags.append("vendor:mikrotik")
    if any(x in host for x in ("unifi", "udm", "usw", "uap")):
        tags.append("vendor:unifi")

    rules = [
        (
            (
                "failed password",
                "authentication failure",
                "invalid user",
                "login failed",
                "auth fail",
                "неверн",  # Ideco RU
                "ошибка аутентификации",
            ),
            "auth_failure",
            ["auth", "security"],
        ),
        (("accepted password", "session opened", "login success", "успешн"), "auth_success", ["auth"]),
        (
            (
                "link down",
                "interface down",
                "went down",
                "oper-status down",
                "changed state to down",
                "link-3-updown",
                "%link-3-updown",
            ),
            "link_down",
            ["network"],
        ),
        (("link up", "interface up", "went up", "changed state to up"), "link_up", ["network"]),
        (("bgp", "ospf", "neighbor down", "adjacency"), "routing", ["network"]),
        (
            (
                "firewall",
                "deny",
                "drop packet",
                "blocked",
                "drop:",
                "reject",
                "ids/ips",
                "запрещ",
                "блокир",
            ),
            "firewall",
            ["security"],
        ),
        (("virus", "malware", "ids", "ips alert", "intrusion"), "threat", ["security", "ids"]),
        (("disk", "filesystem", "inode"), "storage", ["system"]),
        (("cpu", "memory", "oom", "load average", "high temperature"), "resource", ["system"]),
        (("dhcp", "lease"), "dhcp", ["network"]),
        (("vpn", "ipsec", "wireguard", "openvpn", "l2tp", "sstp"), "vpn", ["network", "security"]),
        (("stp", "topology change", "root bridge"), "stp", ["network"]),
        (("poe", "power inline"), "poe", ["network"]),
        (("config", "configuration changed", "configure"), "config_change", ["audit"]),
    ]
    for needles, cat, t in rules:
        if any(n in lower for n in needles):
            category = cat
            tags.extend(t)
            break
    if severity <= 2:
        tags.append("critical")
    elif severity <= 3:
        tags.append("error")
    if app_name:
        tags.append(f"app:{app_name.lower()}")
    seen: set[str] = set()
    uniq = []
    for tag in tags:
        if tag not in seen:
            seen.add(tag)
            uniq.append(tag)
    return category, uniq


def _nil(value: str) -> str | None:
    return None if value == "-" else value


def _parse_ts(value: str, fallback: datetime) -> datetime | None:
    if value == "-":
        return fallback
    try:
        if value.endswith("Z"):
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        return datetime.fromisoformat(value)
    except ValueError:
        return fallback


def _parse_bsd_ts(value: str, fallback: datetime) -> datetime | None:
    try:
        # RFC3164 has no year — assume current UTC year
        dt = parsedate_to_datetime(f"{value} {fallback.year} +0000")
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt
    except Exception:
        return fallback
