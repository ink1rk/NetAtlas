"""External system connectors (integration-ready stubs).

NetAtlas keeps inventory/topology as the source of operational truth.
Connectors sync or enrich data from CMDB / monitoring / DCIM systems.

Implementations are intentionally not wired yet — only contracts.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class Connector(Protocol):
    """Base connector contract for outbound/inbound integrations."""

    name: str
    system: str

    async def health(self) -> dict[str, Any]:
        """Return connector readiness: {ok: bool, detail: str}."""
        ...

    async def sync(self, *, dry_run: bool = True) -> dict[str, Any]:
        """Pull/push a batch. Default dry_run must not mutate remote systems."""
        ...


@runtime_checkable
class DeviceEnricher(Protocol):
    """Enrich NetAtlas devices from an external source of record."""

    async def enrich_device(self, device_id: str) -> dict[str, Any]:
        ...


class ConnectorRegistry:
    """In-process registry of available connectors/plugins."""

    def __init__(self) -> None:
        self._items: dict[str, Connector] = {}

    def register(self, connector: Connector) -> None:
        self._items[connector.name] = connector

    def get(self, name: str) -> Connector | None:
        return self._items.get(name)

    def list(self) -> list[str]:
        return sorted(self._items)


registry = ConnectorRegistry()
