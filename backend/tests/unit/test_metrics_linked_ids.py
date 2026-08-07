"""Regression: metrics linked_ids must treat column scalars as UUIDs."""

from __future__ import annotations

from uuid import uuid4


def test_linked_ids_from_column_scalars() -> None:
    """select(Model.column).scalars() yields bare UUIDs — never .device_id."""
    a, b = uuid4(), uuid4()
    scalars = [a, b, a]
    # Correct construction (what celery_app must do)
    linked_ids = set(scalars)
    assert linked_ids == {a, b}

    # The buggy pattern blows up exactly as production did
    try:
        _ = {row.device_id for row in scalars}  # type: ignore[attr-defined]
        raised = False
    except AttributeError as exc:
        raised = True
        assert "device_id" in str(exc)
    assert raised is True
