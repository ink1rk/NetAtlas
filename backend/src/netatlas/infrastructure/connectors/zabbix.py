"""Zabbix connector stub — monitoring metric/alert sync (not implemented).

Future scope:
- map NetAtlas devices → Zabbix hosts by management IP / hostname
- import trigger problems into observability timeline
- export inventory tags (role, criticality, location)
"""

from __future__ import annotations

from typing import Any


class ZabbixConnector:
    name = "zabbix"
    system = "zabbix"

    def __init__(self, *, api_url: str | None = None, token: str | None = None) -> None:
        self.api_url = api_url
        self.token = token

    async def health(self) -> dict[str, Any]:
        return {
            "ok": False,
            "detail": "stub — configure ZABBIX_API_URL / token and implement JSON-RPC client",
            "configured": bool(self.api_url and self.token),
        }

    async def sync(self, *, dry_run: bool = True) -> dict[str, Any]:
        return {
            "dry_run": dry_run,
            "imported_hosts": 0,
            "imported_problems": 0,
            "status": "not_implemented",
        }
