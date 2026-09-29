"""add deck title column

Revision ID: a2b3c4d5e6f7
Revises: 1ff2a658bf73
Create Date: 2026-09-29
"""
from alembic import op
import sqlalchemy as sa

revision = "a2b3c4d5e6f7"
down_revision = "1ff2a658bf73"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "decks",
        sa.Column("title", sa.String(200), nullable=False, server_default="Presentation"),
    )


def downgrade() -> None:
    op.drop_column("decks", "title")
