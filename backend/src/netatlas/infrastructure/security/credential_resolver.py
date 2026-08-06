"""Resolve encrypted credential profiles into collector credential dicts."""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from netatlas.infrastructure.persistence.models import CredentialProfileModel, DeviceCredentialModel
from netatlas.infrastructure.security.vault import AesGcmSecretVault


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
