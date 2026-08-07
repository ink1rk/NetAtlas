"""SNMP credential candidate merge / probe ordering."""

from __future__ import annotations

from netatlas.workers.celery_app import _merge_snmp_candidates


def test_merge_snmp_candidates_device_first_then_global() -> None:
    device = [{"snmp": {"community": "wrong", "version": 2}, "_profile_id": "a"}]
    global_c = [
        {"snmp": {"community": "wrong", "version": 2}, "_profile_id": "a"},
        {"snmp": {"community": "secret", "version": 2}, "_profile_id": "b"},
        {"snmp": {"community": "public", "version": 2}},
    ]
    merged = _merge_snmp_candidates(device, global_c)
    communities = [c["snmp"]["community"] for c in merged]
    assert communities == ["wrong", "secret", "public"]


def test_merge_snmp_candidates_dedupes_case() -> None:
    merged = _merge_snmp_candidates(
        [{"snmp": {"community": "Public", "version": 2}}],
        [{"snmp": {"community": "public", "version": 2}}],
    )
    assert len(merged) == 1
