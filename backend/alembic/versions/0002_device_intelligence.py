"""Device intelligence schema: roles, metadata, vlan_objects, relationships, cable map.

Revision ID: 0002_device_intelligence
Revises: 0001_initial
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002_device_intelligence"
down_revision: Union[str, None] = "0001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Additive device columns — IF NOT EXISTS via raw SQL for idempotency with bootstrap
    op.execute("ALTER TABLE devices ADD COLUMN IF NOT EXISTS network_role VARCHAR(32) NOT NULL DEFAULT 'unknown'")
    op.execute("ALTER TABLE devices ADD COLUMN IF NOT EXISTS role_confidence DOUBLE PRECISION NOT NULL DEFAULT 0")
    op.execute("ALTER TABLE devices ADD COLUMN IF NOT EXISTS role_reasons JSONB NOT NULL DEFAULT '[]'::jsonb")
    op.execute("ALTER TABLE devices ADD COLUMN IF NOT EXISTS role_source VARCHAR(16) NOT NULL DEFAULT 'auto'")
    op.execute("ALTER TABLE devices ADD COLUMN IF NOT EXISTS location VARCHAR(255)")
    op.execute("ALTER TABLE devices ADD COLUMN IF NOT EXISTS rack VARCHAR(128)")
    op.execute("ALTER TABLE devices ADD COLUMN IF NOT EXISTS owner VARCHAR(128)")
    op.execute("ALTER TABLE devices ADD COLUMN IF NOT EXISTS criticality VARCHAR(32) NOT NULL DEFAULT 'normal'")
    op.execute("ALTER TABLE devices ADD COLUMN IF NOT EXISTS description TEXT")
    op.execute("CREATE INDEX IF NOT EXISTS ix_devices_network_role ON devices (network_role)")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS vlan_objects (
            id UUID PRIMARY KEY,
            vlan_id INTEGER NOT NULL UNIQUE,
            name VARCHAR(128),
            description TEXT,
            networks VARCHAR[],
            attributes JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS device_relationships (
            id UUID PRIMARY KEY,
            source_device_id UUID NOT NULL REFERENCES devices(id) ON DELETE CASCADE,
            target_device_id UUID NOT NULL REFERENCES devices(id) ON DELETE CASCADE,
            rel_type VARCHAR(64) NOT NULL DEFAULT 'connected',
            attributes JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (source_device_id, target_device_id, rel_type)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS topology_history (
            id UUID PRIMARY KEY,
            snapshot_id UUID REFERENCES snapshots(id),
            discovery_job_id UUID REFERENCES discovery_jobs(id),
            label VARCHAR(255) NOT NULL DEFAULT '',
            summary JSONB NOT NULL DEFAULT '{}'::jsonb,
            graph JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS patch_panels (
            id UUID PRIMARY KEY,
            name VARCHAR(128) NOT NULL,
            location VARCHAR(255),
            rack VARCHAR(128),
            port_count INTEGER NOT NULL DEFAULT 24,
            attributes JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS cables (
            id UUID PRIMARY KEY,
            label VARCHAR(128),
            cable_type VARCHAR(32) NOT NULL DEFAULT 'unknown',
            a_device_id UUID REFERENCES devices(id) ON DELETE SET NULL,
            a_interface_id UUID REFERENCES interfaces(id) ON DELETE SET NULL,
            a_panel_id UUID REFERENCES patch_panels(id) ON DELETE SET NULL,
            a_port VARCHAR(64),
            b_device_id UUID REFERENCES devices(id) ON DELETE SET NULL,
            b_interface_id UUID REFERENCES interfaces(id) ON DELETE SET NULL,
            b_panel_id UUID REFERENCES patch_panels(id) ON DELETE SET NULL,
            b_port VARCHAR(64),
            link_id UUID REFERENCES links(id) ON DELETE SET NULL,
            attributes JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS cables")
    op.execute("DROP TABLE IF EXISTS patch_panels")
    op.execute("DROP TABLE IF EXISTS topology_history")
    op.execute("DROP TABLE IF EXISTS device_relationships")
    op.execute("DROP TABLE IF EXISTS vlan_objects")
    # Keep device columns on downgrade to avoid data loss
