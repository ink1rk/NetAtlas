"""Plugin hooks for extending NetAtlas without core rewrites.

Plugins differ from collectors (device protocols) and connectors (external SoR):
they attach to product events — discovery finished, snapshot created, role detected.
"""

from __future__ import annotations

from typing import Any, Awaitable, Callable, Protocol

HookHandler = Callable[..., Awaitable[None] | None]


class Plugin(Protocol):
    name: str

    def register(self, hooks: "HookBus") -> None:
        ...


class HookBus:
    """Minimal event bus for plugin registration."""

    def __init__(self) -> None:
        self._handlers: dict[str, list[HookHandler]] = {}

    def on(self, event: str, handler: HookHandler) -> None:
        self._handlers.setdefault(event, []).append(handler)

    async def emit(self, event: str, payload: dict[str, Any] | None = None) -> None:
        for handler in self._handlers.get(event, []):
            result = handler(payload or {})
            if hasattr(result, "__await__"):
                await result  # type: ignore[misc]


# Known events (contracts only — emit sites will be wired later):
# - discovery.completed
# - snapshot.created
# - device.role_detected
# - topology.changed

hooks = HookBus()
