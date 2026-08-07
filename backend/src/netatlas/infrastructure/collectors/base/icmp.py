"""ICMP probe helper."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


async def icmp_probe(host: str, *, timeout: float = 1.0, count: int = 1) -> bool:
    try:
        from icmplib import async_ping
    except Exception as exc:  # noqa: BLE001
        logger.warning("icmplib unavailable: %s", exc)
        return False
    # Prefer privileged ICMP (NET_RAW in compose); fall back to unprivileged UDP ping.
    for privileged in (True, False):
        try:
            result = await async_ping(host, count=count, timeout=timeout, privileged=privileged)
            if result.is_alive:
                return True
        except Exception as exc:  # noqa: BLE001
            logger.debug("ICMP probe failed host=%s privileged=%s err=%s", host, privileged, exc)
    return False
