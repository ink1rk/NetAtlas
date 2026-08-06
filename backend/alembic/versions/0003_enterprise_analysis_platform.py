"""Enterprise Analysis Platform: interface-centric Link Health columns + VLAN gateway.

Revision ID: 0003_enterprise_analysis
Revises: 0002_device_intelligence
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "0003_enterprise_analysis"
down_revision: Union[str, None] = "0002_device_intelligence"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Interface-centric topology + Link Health (additive; safe on existing installs)
    op.execute("ALTER TABLE links ADD COLUMN IF NOT EXISTS media VARCHAR(16) NOT NULL DEFAULT 'unknown'")
    op.execute("ALTER TABLE links ADD COLUMN IF NOT EXISTS link_status VARCHAR(16) NOT NULL DEFAULT 'unknown'")
    op.execute("ALTER TABLE links ADD COLUMN IF NOT EXISTS crc_errors BIGINT")
    op.execute("ALTER TABLE links ADD COLUMN IF NOT EXISTS drops BIGINT")
    op.execute("ALTER TABLE links ADD COLUMN IF NOT EXISTS rx_utilization_pct DOUBLE PRECISION")
    op.execute("ALTER TABLE links ADD COLUMN IF NOT EXISTS tx_utilization_pct DOUBLE PRECISION")
    op.execute("ALTER TABLE links ADD COLUMN IF NOT EXISTS sfp_vendor VARCHAR(128)")
    op.execute("ALTER TABLE links ADD COLUMN IF NOT EXISTS sfp_model VARCHAR(128)")
    op.execute("ALTER TABLE links ADD COLUMN IF NOT EXISTS sfp_serial VARCHAR(128)")
    op.execute("ALTER TABLE links ADD COLUMN IF NOT EXISTS rx_optical_dbm DOUBLE PRECISION")
    op.execute("ALTER TABLE links ADD COLUMN IF NOT EXISTS tx_optical_dbm DOUBLE PRECISION")
    op.execute("ALTER TABLE links ADD COLUMN IF NOT EXISTS temperature_c DOUBLE PRECISION")
    op.execute("ALTER TABLE links ADD COLUMN IF NOT EXISTS voltage DOUBLE PRECISION")
    op.execute("ALTER TABLE links ADD COLUMN IF NOT EXISTS health VARCHAR(16) NOT NULL DEFAULT 'unknown'")
    op.execute("ALTER TABLE links ADD COLUMN IF NOT EXISTS health_reasons JSONB NOT NULL DEFAULT '[]'::jsonb")
    # VLAN Explorer — explicit gateway (in addition to auto-aggregated networks)
    op.execute("ALTER TABLE vlan_objects ADD COLUMN IF NOT EXISTS gateway VARCHAR(64)")


def downgrade() -> None:
    op.execute("ALTER TABLE vlan_objects DROP COLUMN IF EXISTS gateway")
    for col in (
        "media",
        "link_status",
        "crc_errors",
        "drops",
        "rx_utilization_pct",
        "tx_utilization_pct",
        "sfp_vendor",
        "sfp_model",
        "sfp_serial",
        "rx_optical_dbm",
        "tx_optical_dbm",
        "temperature_c",
        "voltage",
        "health",
        "health_reasons",
    ):
        op.execute(f"ALTER TABLE links DROP COLUMN IF EXISTS {col}")
