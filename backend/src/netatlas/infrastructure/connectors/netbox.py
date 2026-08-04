"""NetBox connector stub — DCIM/IPAM enrichment (not implemented).

Future scope:
- reconcile sites/racks/devices with NetBox DCIM
- import cable/patch-panel objects into Cable Map
- push discovered interfaces/VLANs as NetBox candidates (opt-in)
"""

from __future__ import annotations

from typing import Any


class NetBoxConnector:
    name = "netbox"
    system = "netbox"

    def __init__(self, *, api_url: str | None = None, token: str | None = None) -> None:
        self.api_url = api_url
        self.token = token

    async def health(self) -> dict[str, Any]:
        return {
            "ok": False,
            "detail": "stub — configure NETBOX_URL / token and implement REST client",
            "configured": bool(self.api_url and self.token),
        }

    async def sync(self, *, dry_run: bool = True) -> dict[str, Any]:
        return {
            "dry_run": dry_run,
            "devices_matched": 0,
            "cables_imported": 0,
            "status": "not_implemented",
        }

    async def enrich_device(self, device_id: str) -> dict[str, Any]:
        return {"device_id": device_id, "status": "not_implemented"}
