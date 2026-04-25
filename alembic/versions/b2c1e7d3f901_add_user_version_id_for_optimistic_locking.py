"""add_user_version_id_for_optimistic_locking

Revision ID: b2c1e7d3f901
Revises: 5ac7db1d4f3c
Create Date: 2026-04-25 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b2c1e7d3f901"
down_revision: Union[str, Sequence[str], None] = "5ac7db1d4f3c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("version_id", sa.Integer(), nullable=False, server_default=sa.text("1")),
    )


def downgrade() -> None:
    op.drop_column("users", "version_id")