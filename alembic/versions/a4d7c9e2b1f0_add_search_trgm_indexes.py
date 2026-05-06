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
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.create_index(
        "ix_users_username_trgm",
        "users",
        ["username"],
        unique=False,
        postgresql_using="gin",
        postgresql_ops={"username": "gin_trgm_ops"},
    )
    op.create_index(
        "ix_posts_hashtags_trgm",
        "posts",
        ["hashtags"],
        unique=False,
        postgresql_using="gin",
        postgresql_ops={"hashtags": "gin_trgm_ops"},
        postgresql_where=sa.text("hashtags IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_posts_hashtags_trgm", table_name="posts")
    op.drop_index("ix_users_username_trgm", table_name="users")
