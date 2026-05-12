"""add search trgm indexes

Revision ID: a4d7c9e2b1f0
Revises: f2a6c1d4b8e9
Create Date: 2026-05-06 00:00:03.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a4d7c9e2b1f0"
down_revision: Union[str, Sequence[str], None] = "f2a6c1d4b8e9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        "ix_users_username_lower",
        "users",
        [sa.text("lower(username)")],
        unique=False,
    )
    op.create_index(
        "ix_posts_hashtags",
        "posts",
        ["hashtags"],
        unique=False,
        postgresql_where=sa.text("hashtags IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_posts_hashtags", table_name="posts")
    op.drop_index("ix_users_username_lower", table_name="users")
