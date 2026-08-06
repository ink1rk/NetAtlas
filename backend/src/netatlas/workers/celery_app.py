"""Celery application and tasks."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any
from uuid import UUID

from celery import Celery

from netatlas.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

celery_app = Celery(
    "netatlas",
    broker=settings.rabbitmq_url,
    backend=settings.redis_url,
)
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_routes={
        "netatlas.workers.tasks.run_discovery_job": {"queue": "discovery"},
        "netatlas.workers.tasks.collect_metrics": {"queue": "metrics"},
        "netatlas.workers.tasks.evaluate_triggers": {"queue": "maintenance"},
        "netatlas.workers.tasks.purge_observability": {"queue": "maintenance"},
    },
    beat_schedule={
        "evaluate-triggers": {
            "task": "netatlas.workers.tasks.evaluate_triggers",
            "schedule": float(settings.trigger_eval_interval_seconds),
        },
        "collect-metrics": {
            "task": "netatlas.workers.tasks.collect_metrics",
            "schedule": float(settings.metrics_interval_seconds),
        },
        "purge-observability": {
            "task": "netatlas.workers.tasks.purge_observability",
            "schedule": 3600.0,
        },
    },
)


def main() -> None:
    celery_app.start()


@celery_app.task(name="netatlas.workers.tasks.run_discovery_job")
def run_discovery_job(job_id: str) -> dict[str, Any]:
    return asyncio.run(_run_discovery(UUID(job_id)))


@celery_app.task(name="netatlas.workers.tasks.collect_metrics")
def collect_metrics() -> dict[str, Any]:
    return asyncio.run(_collect_metrics())


@celery_app.task(name="netatlas.workers.tasks.evaluate_triggers")
def evaluate_triggers() -> dict[str, Any]:
    return asyncio.run(_evaluate_triggers())


@celery_app.task(name="netatlas.workers.tasks.purge_observability")
def purge_observability() -> dict[str, Any]:
    return asyncio.run(_purge_observability())


async def _run_discovery(job_id: UUID) -> dict[str, Any]:
    from netatlas.application.use_cases.discovery import DiscoveryOrchestrator
    from netatlas.infrastructure.collectors.base.registry import build_default_registry
    from netatlas.infrastructure.persistence.models import CredentialProfileModel
    from netatlas.infrastructure.persistence.repositories import (
        SqlAlchemyDeviceRepository,
        SqlAlchemyDiscoveryJobRepository,
        SqlAlchemyDiscoverySeedRepository,
        SqlAlchemyInterfaceRepository,
        SqlAlchemyLinkRepository,
        SqlAlchemySnapshotRepository,
    )
    from netatlas.infrastructure.persistence.session import SessionLocal
    from netatlas.infrastructure.security.vault import AesGcmSecretVault
    from sqlalchemy import select

    async with SessionLocal() as session:
        vault = AesGcmSecretVault(get_settings().master_key_b64.get_secret_value())

        async def credential_loader(seeds: list[Any]) -> dict[str, Any]:
            creds: dict[str, Any] = {"snmp": {"community": "public", "version": 2}}
            profile_ids: list[UUID] = []
            for seed in seeds:
                profile_ids.extend(seed.credential_profile_ids)
            if not profile_ids:
                return creds
            rows = (
                await session.execute(
                    select(CredentialProfileModel).where(CredentialProfileModel.id.in_(profile_ids))
                )
            ).scalars().all()
            for row in rows:
                plaintext = vault.decrypt(row.ciphertext, row.nonce, key_version=row.key_version)
                payload = json.loads(plaintext.decode("utf-8"))
                if row.protocol.startswith("snmp"):
                    creds["snmp"] = payload
                elif row.protocol == "ssh":
                    creds["ssh"] = payload
                elif row.protocol in {"esxi", "vsphere"}:
                    creds["vsphere"] = payload
                    creds["esxi"] = payload
                elif row.protocol == "unifi":
                    creds["unifi"] = payload
                elif row.protocol == "proxmox":
                    creds["proxmox"] = payload
                elif row.protocol == "ideco":
                    # may contain ssh and/or snmp overlays
                    if "ssh" in payload:
                        creds["ssh"] = payload["ssh"]
                    if "snmp" in payload:
                        creds["snmp"] = payload["snmp"]
                    creds["ideco"] = payload
                elif row.protocol == "docker":
                    creds["docker"] = payload
            return creds

        async def progress_callback(_jid: UUID, _payload: dict[str, Any]) -> None:
            # Commit mid-run so API/UI see progress and cancel flags
            await session.commit()

        orch = DiscoveryOrchestrator(
            jobs=SqlAlchemyDiscoveryJobRepository(session),
            seeds=SqlAlchemyDiscoverySeedRepository(session),
            devices=SqlAlchemyDeviceRepository(session),
            interfaces=SqlAlchemyInterfaceRepository(session),
            links=SqlAlchemyLinkRepository(session),
            snapshots=SqlAlchemySnapshotRepository(session),
            registry=build_default_registry(),
            credential_loader=credential_loader,
            progress_callback=progress_callback,
        )
        job = await orch.run(job_id)
        await session.commit()
        return {"id": str(job.id), "status": job.status.value, "stats": job.stats}


async def _collect_metrics() -> dict[str, Any]:
    # Placeholder metrics sweep — real collectors invoked per device in subsequent cycles.
    logger.info("Metrics collection tick")
    return {"status": "ok"}


async def _evaluate_triggers() -> dict[str, Any]:
    from netatlas.infrastructure.observability.dispatcher import NotificationDispatcher
    from netatlas.infrastructure.observability.trigger_engine import TriggerEngine
    from netatlas.infrastructure.persistence.session import SessionLocal

    async with SessionLocal() as session:
        settings = get_settings()
        engine = TriggerEngine(session, NotificationDispatcher(session, settings))
        stats = await engine.evaluate_all()
        await session.commit()
        logger.info("Trigger evaluation stats=%s", stats)
        return stats


async def _purge_observability() -> dict[str, Any]:
    from netatlas.infrastructure.observability.ingest import SyslogIngestService
    from netatlas.infrastructure.persistence.session import SessionLocal

    async with SessionLocal() as session:
        deleted = await SyslogIngestService(session, get_settings()).purge_expired()
        await session.commit()
        return {"deleted_events": deleted}
