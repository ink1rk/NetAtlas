"""Resolve a MAC address for a locally-reachable IP via the host's ARP/neighbor table.

Used as a last resort for Unknown Device classification: when no collector
plugin can talk to a host (SNMP/SSH closed, unmanaged appliance, IoT device),
the only fact we can still learn is its Layer-2 address from the discovery
worker's own kernel neighbor table (populated as a side effect of the ICMP
probe). This is read-only and touches no network device.
"""

from __future__ import annotations

import asyncio
import logging
import re

logger = logging.getLogger(__name__)

_MAC_RE = re.compile(r"(?:[0-9a-fA-F]{2}[:-]){5}[0-9a-fA-F]{2}")


async def resolve_local_mac(ip: str, *, timeout: float = 1.5) -> str | None:
    """Best-effort local neighbor-table lookup. Returns lowercase colon MAC or None."""
    for cmd in (
        ["ip", "neighbor", "show", "to", ip],
        ["arp", "-n", ip],
    ):
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )
            try:
                stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            except TimeoutError:
                proc.kill()
                continue
            text = (stdout or b"").decode("utf-8", errors="ignore")
            match = _MAC_RE.search(text)
            if match:
                return match.group(0).lower().replace("-", ":")
        except (FileNotFoundError, OSError) as exc:
            logger.debug("local_arp command unavailable cmd=%s err=%s", cmd[0], exc)
            continue
    return None


async def reverse_dns(ip: str, *, timeout: float = 1.0) -> str | None:
    """Best-effort reverse DNS lookup; returns short hostname or None."""
    try:
        loop = asyncio.get_running_loop()
        result = await asyncio.wait_for(loop.getnameinfo((ip, 0)), timeout=timeout)
        host = result[0] if result else None
        if host and host != ip:
            return host.split(".")[0]
    except Exception as exc:  # noqa: BLE001
        logger.debug("reverse_dns failed ip=%s err=%s", ip, exc)
    return None
