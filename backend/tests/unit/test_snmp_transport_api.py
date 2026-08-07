"""pysnmp 6 asyncio HLAPI compatibility."""

from __future__ import annotations

import asyncio
import time

from netatlas.infrastructure.collectors.base.snmp_transport import (
    SnmpTransport,
    check_pysnmp,
)


def test_pysnmp_library_loads() -> None:
    ok, detail = check_pysnmp()
    assert ok is True, detail


def test_async_get_actually_waits_for_timeout() -> None:
    """Regression: broken pyasn1/sync path returned None in ~4ms without network I/O."""

    async def _run() -> float:
        t = SnmpTransport()
        t0 = time.time()
        await t.get("127.0.0.1", "1.3.6.1.2.1.1.1.0", timeout=0.4)
        return time.time() - t0

    elapsed = asyncio.run(_run())
    # Must wait for UDP timeout (not instant library failure).
    assert elapsed >= 0.3, f"SNMP GET returned too fast ({elapsed:.3f}s) — library likely broken"
