"""add_email_verified_to_users

Revision ID: 5ac7db1d4f3c
Revises: f87ab2d91c3e
Create Date: 2026-03-26 19:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "5ac7db1d4f3c"
down_revision: Union[str, Sequence[str], None] = "f87ab2d91c3e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("email_verified", sa.Boolean(), server_default=sa.text("true"), nullable=False),
    )
    op.alter_column("users", "email_verified", server_default=sa.text("false"))


def downgrade() -> None:
    op.drop_column("users", "email_verified")
