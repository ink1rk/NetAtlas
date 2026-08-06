"""Resolve encrypted credential profiles into collector credential dicts."""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from netatlas.infrastructure.persistence.models import (
    CredentialProfileModel,
    DeviceCredentialModel,
    DiscoverySeedModel,
)
from netatlas.infrastructure.security.vault import AesGcmSecretVault


async def list_snmp_profile_ids(session: AsyncSession) -> list[UUID]:
    """All SNMPv2/v3 credential profile IDs (stable order by name)."""
    rows = (
        await session.execute(
            select(CredentialProfileModel.id)
            .where(CredentialProfileModel.protocol.in_(("snmpv2", "snmpv3", "snmp")))
            .order_by(CredentialProfileModel.name)
        )
    ).scalars().all()
    return list(rows)


def _dedupe_uuids(ids: list[UUID]) -> list[UUID]:
    seen: set[UUID] = set()
    out: list[UUID] = []
    for pid in ids:
        if pid in seen:
            continue
        seen.add(pid)
        out.append(pid)
    return out


async def discovery_profile_ids(
    session: AsyncSession,
    seeds: list[Any],
    *,
    include_global_snmp: bool = True,
) -> list[UUID]:
    """Profiles for a discovery run: seed attachments first, then all SNMP profiles.

    Operators often create an SNMPv2 profile and assign it to devices, but forget
    to attach it to the discovery seed. Without a global fallback, fingerprinting
    only tries `public` and every host lands as Unknown Device.
    """
    profile_ids: list[UUID] = []
    for seed in seeds:
        for pid in list(getattr(seed, "credential_profile_ids", None) or []):
            profile_ids.append(pid if isinstance(pid, UUID) else UUID(str(pid)))
    if include_global_snmp:
        profile_ids.extend(await list_snmp_profile_ids(session))
    return _dedupe_uuids(profile_ids)


async def bind_profiles_to_all_seeds(
    session: AsyncSession,
    profile_ids: list[UUID],
) -> int:
    """Union `profile_ids` into every discovery seed. Returns seeds updated."""
    if not profile_ids:
        return 0
    seeds = (await session.execute(select(DiscoverySeedModel))).scalars().all()
    updated = 0
    wanted = {str(pid) for pid in profile_ids}
    for seed in seeds:
        current = [str(x) for x in (seed.credential_profile_ids or [])]
        merged = list(dict.fromkeys([*current, *wanted]))
        if merged != current:
            seed.credential_profile_ids = merged
            updated += 1
    if updated:
        await session.flush()
    return updated


def merge_profile_payload(creds: dict[str, Any], protocol: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Merge one decrypted profile into the transport credential bag."""
    if protocol.startswith("snmp"):
        creds["snmp"] = payload
    elif protocol == "ssh":
        creds["ssh"] = payload
    elif protocol in {"esxi", "vsphere"}:
        creds["vsphere"] = payload
        creds["esxi"] = payload
    elif protocol == "unifi":
        creds["unifi"] = payload
    elif protocol == "proxmox":
        creds["proxmox"] = payload
    elif protocol == "ideco":
        if "ssh" in payload:
            creds["ssh"] = payload["ssh"]
        if "snmp" in payload:
            creds["snmp"] = payload["snmp"]
        creds["ideco"] = payload
    elif protocol == "docker":
        creds["docker"] = payload
    else:
        creds[protocol] = payload
    return creds


async def load_profiles(
    session: AsyncSession,
    vault: AesGcmSecretVault,
    profile_ids: list[UUID],
    *,
    default_snmp: bool = True,
) -> dict[str, Any]:
    creds: dict[str, Any] = {}
    if default_snmp:
        creds["snmp"] = {"community": "public", "version": 2}
    if not profile_ids:
        return creds
    rows = (
        await session.execute(select(CredentialProfileModel).where(CredentialProfileModel.id.in_(profile_ids)))
    ).scalars().all()
    for row in rows:
        plaintext = vault.decrypt(row.ciphertext, row.nonce, key_version=row.key_version)
        payload = json.loads(plaintext.decode("utf-8"))
        merge_profile_payload(creds, row.protocol, payload)
    return creds


async def load_profile_candidates(
    session: AsyncSession,
    vault: AesGcmSecretVault,
    profile_ids: list[UUID],
    *,
    default_snmp: bool = True,
) -> list[dict[str, Any]]:
    """Credential Manager rotation: one candidate credential bag per profile.

    Unlike `load_profiles` (which merges everything into a single bag, so only
    the last SNMP profile survives), this returns profiles individually so the
    discovery orchestrator can try each SNMP profile in turn until one answers,
    then remember which one worked (`_profile_id`). SSH/API profiles are still
    merged into every candidate so non-SNMP collection isn't affected by
    rotation. A default public/v2c candidate is appended last as a fallback.
    Candidate order follows `profile_ids` (seed attachments first).
    """
    if not profile_ids:
        return [{"snmp": {"community": "public", "version": 2}}] if default_snmp else []
    rows = (
        await session.execute(select(CredentialProfileModel).where(CredentialProfileModel.id.in_(profile_ids)))
    ).scalars().all()
    by_id = {row.id: row for row in rows}
    non_snmp: dict[str, Any] = {}
    snmp_candidates: list[dict[str, Any]] = []
    for pid in _dedupe_uuids(profile_ids):
        row = by_id.get(pid)
        if row is None:
            continue
        plaintext = vault.decrypt(row.ciphertext, row.nonce, key_version=row.key_version)
        payload = json.loads(plaintext.decode("utf-8"))
        if row.protocol.startswith("snmp"):
            # Normalize wire format for collectors (UI stores snmpv2 without version).
            snmp_payload = dict(payload)
            if "version" not in snmp_payload:
                snmp_payload["version"] = 3 if row.protocol == "snmpv3" else 2
            if row.protocol == "snmpv2" and "community" in snmp_payload:
                snmp_payload.setdefault("community", snmp_payload["community"])
            snmp_candidates.append({"snmp": snmp_payload, "_profile_id": str(row.id)})
        else:
            merge_profile_payload(non_snmp, row.protocol, payload)
    # Append public last only when it is not already present among candidates.
    if default_snmp:
        communities = {
            str((c.get("snmp") or {}).get("community") or "").lower()
            for c in snmp_candidates
        }
        if "public" not in communities:
            snmp_candidates.append({"snmp": {"community": "public", "version": 2}})
    if not snmp_candidates and default_snmp:
        snmp_candidates.append({"snmp": {"community": "public", "version": 2}})
    return [{**non_snmp, **cand} for cand in snmp_candidates]


async def load_device_credentials(
    session: AsyncSession,
    vault: AesGcmSecretVault,
    device_id: UUID,
    *,
    default_snmp: bool = False,
) -> dict[str, Any]:
    links = (
        await session.execute(
            select(DeviceCredentialModel).where(DeviceCredentialModel.device_id == device_id)
        )
    ).scalars().all()
    profile_ids = [link.credential_profile_id for link in links]
    return await load_profiles(session, vault, profile_ids, default_snmp=default_snmp)


async def bind_device_credentials(
    session: AsyncSession,
    device_id: UUID,
    profile_ids: list[UUID],
) -> int:
    """Attach credential profiles to a device (idempotent). Returns newly created links."""
    if not profile_ids:
        return 0
    existing = {
        row.credential_profile_id
        for row in (
            await session.execute(
                select(DeviceCredentialModel).where(DeviceCredentialModel.device_id == device_id)
            )
        ).scalars().all()
    }
    created = 0
    from uuid import uuid4

    for pid in profile_ids:
        if pid in existing:
            continue
        # ensure profile exists
        profile = await session.get(CredentialProfileModel, pid)
        if not profile:
            continue
        session.add(
            DeviceCredentialModel(
                id=uuid4(),
                device_id=device_id,
                credential_profile_id=pid,
            )
        )
        created += 1
    if created:
        await session.flush()
    return created
