"""Chiave di idempotenza della richiesta d'iscrizione (US-04, ADR-0006).

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-14 20:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | Sequence[str] | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("iscrizioni", sa.Column("chiave_idempotenza", sa.String(64), nullable=True))
    op.create_index(
        "uq_iscrizioni_chiave_idempotenza",
        "iscrizioni",
        ["persona_id", "chiave_idempotenza"],
        unique=True,
        postgresql_where=sa.text("chiave_idempotenza IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_iscrizioni_chiave_idempotenza", table_name="iscrizioni")
    op.drop_column("iscrizioni", "chiave_idempotenza")
