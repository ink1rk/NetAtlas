"""SNMP read-only transport adapter."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from netatlas.infrastructure.security.readonly_guard import SnmpReadOnlyGuard

logger = logging.getLogger(__name__)


class SnmpTransport:
    """Thin async wrapper that hard-blocks SNMP SET."""

    def __init__(self) -> None:
        self._guard = SnmpReadOnlyGuard()

    async def get(
        self,
        host: str,
        oid: str,
        *,
        community: str = "public",
        version: int = 2,
        timeout: float = 2.0,
        **v3: Any,
    ) -> str | None:
        self._guard.assert_allowed("get")
        return await asyncio.to_thread(
            self._sync_get, host, oid, community, version, timeout, v3
        )

    async def walk(
        self,
        host: str,
        oid: str,
        *,
        community: str = "public",
        version: int = 2,
        timeout: float = 2.0,
        **v3: Any,
    ) -> list[tuple[str, str]]:
        self._guard.assert_allowed("walk")
        return await asyncio.to_thread(
            self._sync_walk, host, oid, community, version, timeout, v3
        )

    def _sync_get(
        self,
        host: str,
        oid: str,
        community: str,
        version: int,
        timeout: float,
        v3: dict[str, Any],
    ) -> str | None:
        try:
            from pysnmp.hlapi import (  # type: ignore[import-untyped]
                CommunityData,
                ContextData,
                ObjectIdentity,
                ObjectType,
                SnmpEngine,
                UdpTransportTarget,
                UsmUserData,
                getCmd,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("pysnmp unavailable: %s", exc)
            return None

        auth: Any
        if version == 3:
            auth = UsmUserData(
                v3.get("username", ""),
                v3.get("auth_key"),
                v3.get("priv_key"),
            )
        else:
            auth = CommunityData(community, mpModel=1 if version == 2 else 0)

        iterator = getCmd(
            SnmpEngine(),
            auth,
            UdpTransportTarget((host, 161), timeout=timeout, retries=1),
            ContextData(),
            ObjectType(ObjectIdentity(oid)),
        )
        error_indication, error_status, _error_index, var_binds = next(iterator)
        if error_indication or error_status:
            logger.debug("SNMP GET failed host=%s oid=%s err=%s", host, oid, error_indication or error_status)
            return None
        return str(var_binds[0][1])

    def _sync_walk(
        self,
        host: str,
        oid: str,
        community: str,
        version: int,
        timeout: float,
        v3: dict[str, Any],
    ) -> list[tuple[str, str]]:
        try:
            from pysnmp.hlapi import (  # type: ignore[import-untyped]
                CommunityData,
                ContextData,
                ObjectIdentity,
                ObjectType,
                SnmpEngine,
                UdpTransportTarget,
                UsmUserData,
                nextCmd,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("pysnmp unavailable: %s", exc)
            return []

        auth: Any
        if version == 3:
            auth = UsmUserData(
                v3.get("username", ""),
                v3.get("auth_key"),
                v3.get("priv_key"),
            )
        else:
            auth = CommunityData(community, mpModel=1 if version == 2 else 0)

        results: list[tuple[str, str]] = []
        for error_indication, error_status, _error_index, var_binds in nextCmd(
            SnmpEngine(),
            auth,
            UdpTransportTarget((host, 161), timeout=timeout, retries=1),
            ContextData(),
            ObjectType(ObjectIdentity(oid)),
            lexicographicMode=False,
        ):
            if error_indication or error_status:
                break
            for name, val in var_binds:
                results.append((str(name), str(val)))
            if len(results) > 5000:
                break
        return results
