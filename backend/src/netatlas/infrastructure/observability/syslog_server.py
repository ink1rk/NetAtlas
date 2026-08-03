"""UDP/TCP/(optional TLS) syslog receiver process."""

from __future__ import annotations

import asyncio
import logging
import ssl
from datetime import UTC, datetime
from pathlib import Path

from netatlas.config import get_settings
from netatlas.infrastructure.observability.dispatcher import NotificationDispatcher
from netatlas.infrastructure.observability.ingest import SyslogIngestService
from netatlas.infrastructure.observability.trigger_engine import TriggerEngine
from netatlas.infrastructure.persistence.session import SessionLocal

logger = logging.getLogger("netatlas.syslog")


async def _ingest_and_evaluate(raw: str, source_ip: str | None) -> None:
    async with SessionLocal() as session:
        settings = get_settings()
        ingest = SyslogIngestService(session, settings)
        event = await ingest.ingest(raw, source_ip=source_ip, received_at=datetime.now(UTC))
        engine = TriggerEngine(session, NotificationDispatcher(session, settings))
        await engine.evaluate_syslog_event(event)
        await session.commit()


class SyslogProtocol(asyncio.DatagramProtocol):
    def __init__(self) -> None:
        self._queue: asyncio.Queue[tuple[str, str | None]] = asyncio.Queue(maxsize=10000)

    def datagram_received(self, data: bytes, addr: tuple[str, int]) -> None:  # type: ignore[override]
        try:
            text = data.decode("utf-8", errors="replace")
        except Exception:
            return
        try:
            self._queue.put_nowait((text, addr[0]))
        except asyncio.QueueFull:
            logger.warning("Syslog UDP queue full; dropping message from %s", addr[0])

    async def worker(self) -> None:
        while True:
            raw, source_ip = await self._queue.get()
            try:
                await _ingest_and_evaluate(raw, source_ip)
            except Exception:
                logger.exception("Failed to ingest syslog from %s", source_ip)
            finally:
                self._queue.task_done()


async def handle_stream_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    peer = writer.get_extra_info("peername")
    source_ip = peer[0] if peer else None
    buffer = b""
    try:
        while True:
            chunk = await reader.read(4096)
            if not chunk:
                break
            buffer += chunk
            while b"\n" in buffer:
                line, buffer = buffer.split(b"\n", 1)
                text = line.decode("utf-8", errors="replace").strip("\x00\r")
                if not text:
                    continue
                await _ingest_and_evaluate(text, source_ip)
    except Exception:
        logger.exception("Stream syslog client error from %s", source_ip)
    finally:
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass


def _build_tls_context(cert_file: str, key_file: str) -> ssl.SSLContext:
    if not Path(cert_file).is_file() or not Path(key_file).is_file():
        raise FileNotFoundError(f"TLS syslog cert/key not found: {cert_file} / {key_file}")
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    ctx.load_cert_chain(certfile=cert_file, keyfile=key_file)
    return ctx


async def run_syslog_server() -> None:
    settings = get_settings()
    logging.basicConfig(level=logging.INFO)
    loop = asyncio.get_running_loop()
    protocol = SyslogProtocol()
    transport, _ = await loop.create_datagram_endpoint(
        lambda: protocol,
        local_addr=(settings.syslog_udp_host, settings.syslog_udp_port),
    )
    tcp_server = await asyncio.start_server(
        handle_stream_client,
        host=settings.syslog_udp_host,
        port=settings.syslog_tcp_port,
    )
    servers = [tcp_server]
    if settings.syslog_tls_enable:
        ssl_ctx = _build_tls_context(settings.syslog_tls_cert_file, settings.syslog_tls_key_file)
        tls_server = await asyncio.start_server(
            handle_stream_client,
            host=settings.syslog_udp_host,
            port=settings.syslog_tls_port,
            ssl=ssl_ctx,
        )
        servers.append(tls_server)
        logger.info("Syslog TLS listening on %s:%s", settings.syslog_udp_host, settings.syslog_tls_port)

    worker = asyncio.create_task(protocol.worker())
    logger.info(
        "Syslog server listening udp/%s:%s tcp/%s:%s",
        settings.syslog_udp_host,
        settings.syslog_udp_port,
        settings.syslog_udp_host,
        settings.syslog_tcp_port,
    )
    try:
        await asyncio.gather(*(server.serve_forever() for server in servers))
    finally:
        worker.cancel()
        transport.close()
        for server in servers:
            server.close()
            await server.wait_closed()


def main() -> None:
    asyncio.run(run_syslog_server())


if __name__ == "__main__":
    main()
