"""Read-only guards for SSH and SNMP transports."""

from __future__ import annotations

import re

from netatlas.domain.errors import WriteOperationForbiddenError


_FORBIDDEN_SSH_PATTERNS = (
    r"\bconfigure\b",
    r"\bconf\s+t\b",
    r"\bwrite\b",
    r"\bcopy\s+running",
    r"\bcopy\s+run",
    r"\breload\b",
    r"\bdelete\b",
    r"\berase\b",
    r"\bno\s+",
    r"\bset\b",
    r"\badd\b",
    r"\bremove\b",
    r"\benable\b",
    r"\busername\b",
    r"\bsnmp-server\b",
    r"\bvlan\s+\d+\b",
    r"\binterface\s+\S+\b.*\b(shutdown|no shutdown|switchport|ip address)\b",
    r"/system\s+reboot",
    r"/system\s+reset",
    r"\biptables\s+-A\b",
    r"\brm\s+",
    r"\bmkfs\b",
    r"\bdd\s+if=",
)

_COMPILED = [re.compile(p, re.IGNORECASE) for p in _FORBIDDEN_SSH_PATTERNS]

# Explicit allow prefixes per platform family (checked after forbid).
ALLOWED_SSH_PREFIXES: dict[str, tuple[str, ...]] = {
    "cisco_ios": (
        "show ",
        "terminal length 0",
    ),
    "mikrotik": (
        "/system ",
        "/interface ",
        "/ip neighbor",
        "/ip arp",
        "/ip address",
        "/ip route print",
        "/bridge ",
        "/routing ",
    ),
    "eltex": (
        "show ",
        "terminal length 0",
    ),
    "linux": (
        "hostnamectl",
        "uname ",
        "cat /proc/",
        "ip -j ",
        "ip link",
        "ip addr",
        "ip neigh",
        "ip route",
        "lldpctl",
        "docker ",
        "free -",
        "uptime",
        "nproc",
        "lsblk",
        "dmidecode",
    ),
    "windows": (
        "hostname",
        "ipconfig",
        "get-netadapter",
        "get-netneighbor",
        "get-ciminstance",
        "systeminfo",
    ),
    "generic": ("show ", "hostname", "uname", "ip ", "cat /proc/"),
}


class ReadOnlyCommandGuard:
    """Rejects any SSH command that could mutate device state."""

    def assert_allowed(self, command: str, *, platform: str = "generic") -> None:
        normalized = " ".join(command.strip().split())
        if not normalized:
            raise WriteOperationForbiddenError("Empty SSH command rejected")
        for pattern in _COMPILED:
            if pattern.search(normalized):
                raise WriteOperationForbiddenError(
                    f"Write-like SSH command rejected: {normalized}"
                )
        prefixes = ALLOWED_SSH_PREFIXES.get(platform, ALLOWED_SSH_PREFIXES["generic"])
        if not any(normalized.lower().startswith(p.lower()) for p in prefixes):
            raise WriteOperationForbiddenError(
                f"SSH command not in allow-list for platform {platform}: {normalized}"
            )


class SnmpReadOnlyGuard:
    """Blocks SNMP SET operations at the adapter boundary."""

    ALLOWED_OPS = frozenset({"get", "getnext", "getbulk", "walk", "bulk_walk"})

    def assert_allowed(self, operation: str) -> None:
        op = operation.lower().strip()
        if op not in self.ALLOWED_OPS:
            raise WriteOperationForbiddenError(f"SNMP operation forbidden: {operation}")
