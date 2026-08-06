"""Small helpers for credential rotation ordering."""

from __future__ import annotations

from uuid import uuid4

from netatlas.infrastructure.security.credential_resolver import _dedupe_uuids


def test_dedupe_uuids_preserves_order() -> None:
    a, b, c = uuid4(), uuid4(), uuid4()
    assert _dedupe_uuids([a, b, a, c, b]) == [a, b, c]
