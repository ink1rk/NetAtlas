"""SSH read-only transport adapter."""

from __future__ import annotations

import logging
from typing import Any

from netatlas.infrastructure.security.readonly_guard import ReadOnlyCommandGuard

logger = logging.getLogger(__name__)


class SshTransport:
    def __init__(self) -> None:
        self._guard = ReadOnlyCommandGuard()

    async def exec(
        self,
        host: str,
        command: str,
        *,
        username: str,
        password: str | None = None,
        private_key: str | None = None,
        platform: str = "generic",
        timeout: float = 20.0,
        port: int = 22,
    ) -> str:
        self._guard.assert_allowed(command, platform=platform)
        try:
            import asyncssh
        except Exception as exc:  # noqa: BLE001
            logger.warning("asyncssh unavailable: %s", exc)
            return ""

        connect_kwargs: dict[str, Any] = {
            "host": host,
            "port": port,
            "username": username,
            "known_hosts": None,
            "login_timeout": timeout,
        }
        if private_key:
            connect_kwargs["client_keys"] = [asyncssh.import_private_key(private_key)]
        elif password is not None:
            connect_kwargs["password"] = password

        try:
            async with asyncssh.connect(**connect_kwargs) as conn:
                result = await asyncio_wait_exec(conn, command, timeout)
                return result
        except Exception as exc:  # noqa: BLE001
            logger.debug("SSH exec failed host=%s cmd=%s err=%s", host, command, exc)
            return ""


async def asyncio_wait_exec(conn: Any, command: str, timeout: float) -> str:
    result = await conn.run(command, check=False, timeout=timeout)
    stdout = result.stdout or ""
    return str(stdout)
