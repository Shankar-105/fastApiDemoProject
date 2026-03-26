"""add_last_seen_at_to_users

Revision ID: f87ab2d91c3e
Revises: c1f4f99c7a10
Create Date: 2026-03-26 14:20:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "f87ab2d91c3e"
down_revision: Union[str, Sequence[str], None] = "c1f4f99c7a10"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "last_seen_at")
