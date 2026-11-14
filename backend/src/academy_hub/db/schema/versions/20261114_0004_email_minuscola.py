"""Email delle persone sempre minuscole: chiave verso l'identità OIDC (US-16, ADR-0008).

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-14 22:00:00.000000
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0004"
down_revision: str | Sequence[str] | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Con il vincolo, l'indice UNIQUE già esistente vale anche senza distinguere
    # maiuscole e minuscole, e la ricerca per email resta un confronto esatto.
    op.execute("UPDATE persone SET email = lower(email) WHERE email <> lower(email)")
    op.create_check_constraint("email_minuscola", "persone", "email = lower(email)")


def downgrade() -> None:
    op.drop_constraint("email_minuscola", "persone", type_="check")
