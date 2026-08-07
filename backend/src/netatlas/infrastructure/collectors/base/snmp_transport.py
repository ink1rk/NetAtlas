"""SNMP read-only transport adapter (pysnmp-lextudio 6.x asyncio HLAPI)."""

from __future__ import annotations

import logging
from typing import Any

from netatlas.infrastructure.security.readonly_guard import SnmpReadOnlyGuard

logger = logging.getLogger(__name__)

_SNMP_NULL_MARKERS = (
    "nosuchobject",
    "nosuchinstance",
    "endofmibview",
    "no such object currently exists at this oid",
    "no such instance currently exists at this oid",
)

# Last library/transport error visible to probe logs (process-local).
_LAST_ERROR: str | None = None


def get_last_snmp_error() -> str | None:
    return _LAST_ERROR


def _set_last_error(msg: str | None) -> None:
    global _LAST_ERROR
    _LAST_ERROR = msg


def _clean_snmp_value(raw: Any) -> str | None:
    """Return None for SNMP null / exception syntax values from pysnmp."""
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None
    lowered = text.lower()
    if lowered in _SNMP_NULL_MARKERS or lowered.startswith("no such "):
        return None
    return text


def check_pysnmp() -> tuple[bool, str]:
    """Return (ok, detail) — used by probes so silent import failures are visible."""
    try:
        from pysnmp.hlapi.asyncio import (  # noqa: F401
            CommunityData,
            ContextData,
            ObjectIdentity,
            ObjectType,
            SnmpEngine,
            UdpTransportTarget,
            bulkWalkCmd,
            getCmd,
        )

        _ = getCmd
        return True, "pysnmp asyncio hlapi ok"
    except Exception as exc:  # noqa: BLE001
        return False, f"pysnmp unavailable: {exc}"


class SnmpTransport:
    """Async SNMP GET/WALK — hard-blocks SNMP SET via readonly guard."""

    def __init__(self) -> None:
        self._guard = SnmpReadOnlyGuard()

    def _auth(self, community: str, version: int, v3: dict[str, Any]) -> Any:
        from pysnmp.hlapi.asyncio import CommunityData, UsmUserData

        if version == 3:
            return UsmUserData(
                v3.get("username", ""),
                v3.get("auth_key"),
                v3.get("priv_key"),
            )
        comm = (community or "public").strip() or "public"
        return CommunityData(comm, mpModel=1 if version == 2 else 0)

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
        ok, detail = check_pysnmp()
        if not ok:
            _set_last_error(detail)
            logger.error(detail)
            return None
        try:
            from pysnmp.hlapi.asyncio import (
                ContextData,
                ObjectIdentity,
                ObjectType,
                SnmpEngine,
                UdpTransportTarget,
                getCmd,
            )
        except Exception as exc:  # noqa: BLE001
            _set_last_error(f"pysnmp import failed: {exc}")
            logger.error("pysnmp unavailable: %s", exc)
            return None

        try:
            error_indication, error_status, _error_index, var_binds = await getCmd(
                SnmpEngine(),
                self._auth(community, version, v3),
                UdpTransportTarget((host, 161), timeout=float(timeout), retries=1),
                ContextData(),
                ObjectType(ObjectIdentity(oid)),
            )
        except Exception as exc:  # noqa: BLE001
            _set_last_error(f"SNMP GET exception host={host}: {exc}")
            logger.warning("SNMP GET exception host=%s oid=%s: %s", host, oid, exc)
            return None

        if error_indication or error_status:
            err = str(error_indication or error_status)
            _set_last_error(f"SNMP GET host={host} oid={oid}: {err}")
            logger.info(
                "SNMP GET failed host=%s oid=%s err=%s community=%s",
                host,
                oid,
                err,
                community if version != 3 else "(v3)",
            )
            return None
        if not var_binds:
            _set_last_error(f"SNMP GET host={host}: empty var_binds")
            return None
        value = _clean_snmp_value(var_binds[0][1])
        if value is not None:
            _set_last_error(None)
        return value

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
        ok, detail = check_pysnmp()
        if not ok:
            _set_last_error(detail)
            logger.error(detail)
            return []
        try:
            from pysnmp.hlapi.asyncio import (
                ContextData,
                ObjectIdentity,
                ObjectType,
                SnmpEngine,
                UdpTransportTarget,
                bulkWalkCmd,
            )
        except Exception as exc:  # noqa: BLE001
            _set_last_error(f"pysnmp import failed: {exc}")
            logger.error("pysnmp unavailable: %s", exc)
            return []

        results: list[tuple[str, str]] = []
        try:
            async for error_indication, error_status, _error_index, var_binds in bulkWalkCmd(
                SnmpEngine(),
                self._auth(community, version, v3),
                UdpTransportTarget((host, 161), timeout=float(timeout), retries=1),
                ContextData(),
                0,
                25,
                ObjectType(ObjectIdentity(oid)),
                lexicographicMode=False,
            ):
                if error_indication or error_status:
                    if not results:
                        err = str(error_indication or error_status)
                        _set_last_error(f"SNMP WALK host={host} oid={oid}: {err}")
                        logger.info(
                            "SNMP WALK failed host=%s oid=%s err=%s",
                            host,
                            oid,
                            err,
                        )
                    break
                for name, val in var_binds:
                    cleaned = _clean_snmp_value(val)
                    if cleaned is not None:
                        results.append((str(name), cleaned))
                if len(results) > 5000:
                    break
        except Exception as exc:  # noqa: BLE001
            _set_last_error(f"SNMP WALK exception host={host}: {exc}")
            logger.warning("SNMP WALK exception host=%s oid=%s: %s", host, oid, exc)
            return results
        return results
