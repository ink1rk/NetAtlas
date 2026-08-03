"""RBAC permission codes and role defaults."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Permission:
    code: str
    description: str


PERMISSIONS: tuple[Permission, ...] = (
    Permission("inventory:read", "Read devices and interfaces"),
    Permission("topology:read", "Read topology and cable paths"),
    Permission("discovery:read", "Read discovery jobs and seeds"),
    Permission("discovery:write", "Manage seeds and start discovery"),
    Permission("snapshots:read", "Read snapshots and diffs"),
    Permission("ipam:read", "Read IPAM"),
    Permission("ipam:write", "Register prefixes in IPAM"),
    Permission("monitoring:read", "Read metrics"),
    Permission("export:write", "Export topology/inventory"),
    Permission("credentials:write", "Manage credential profiles"),
    Permission("users:write", "Manage users and roles"),
    Permission("audit:read", "Read audit log"),
    Permission("system:read", "Read system health details"),
)

ROLE_PERMISSIONS: dict[str, frozenset[str]] = {
    "viewer": frozenset(
        {
            "inventory:read",
            "topology:read",
            "discovery:read",
            "snapshots:read",
            "ipam:read",
            "monitoring:read",
            "system:read",
        }
    ),
    "operator": frozenset(
        {
            "inventory:read",
            "topology:read",
            "discovery:read",
            "discovery:write",
            "snapshots:read",
            "ipam:read",
            "ipam:write",
            "monitoring:read",
            "export:write",
            "system:read",
        }
    ),
    "admin": frozenset(p.code for p in PERMISSIONS),
}
