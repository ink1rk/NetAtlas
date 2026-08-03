"""initial schema marker

Revision ID: 0001_initial
Revises:
Create Date: 2026-08-03
"""
from typing import Sequence, Union

revision: str = "0001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Schema is created via SQLAlchemy metadata at API startup for MVP bootstrap.
    # Future revisions must be generated with `alembic revision --autogenerate`.
    pass


def downgrade() -> None:
    pass
