"""Generic CMDB connector stub (ServiceNow / iTop / custom).

Future scope:
- map CI classes to NetAtlas device roles
- pull owner/criticality/location metadata
- emit change tickets from snapshot diffs (opt-in)
"""

from __future__ import annotations

from typing import Any


class CmdbConnector:
    name = "cmdb"
    system = "cmdb"

    def __init__(self, *, api_url: str | None = None, token: str | None = None) -> None:
        self.api_url = api_url
        self.token = token

    async def health(self) -> dict[str, Any]:
        return {
            "ok": False,
            "detail": "stub — configure CMDB endpoint and implement CI sync",
            "configured": bool(self.api_url and self.token),
        }

    async def sync(self, *, dry_run: bool = True) -> dict[str, Any]:
        return {
            "dry_run": dry_run,
            "cis_matched": 0,
            "metadata_updated": 0,
            "status": "not_implemented",
        }

    async def enrich_device(self, device_id: str) -> dict[str, Any]:
        return {"device_id": device_id, "status": "not_implemented"}
