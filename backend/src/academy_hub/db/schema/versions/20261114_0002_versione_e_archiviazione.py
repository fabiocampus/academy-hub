"""Versione per la concorrenza ottimistica su corsi ed edizioni; archiviazione dei corsi.

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-14 16:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | Sequence[str] | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("corsi", sa.Column("archiviato_il", sa.DateTime(timezone=True), nullable=True))
    op.add_column("corsi", sa.Column("versione", sa.Integer(), server_default="1", nullable=False))
    op.add_column(
        "edizioni", sa.Column("versione", sa.Integer(), server_default="1", nullable=False)
    )


def downgrade() -> None:
    op.drop_column("edizioni", "versione")
    op.drop_column("corsi", "versione")
    op.drop_column("corsi", "archiviato_il")
