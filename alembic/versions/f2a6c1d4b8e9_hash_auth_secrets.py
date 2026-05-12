"""hash auth secrets

Revision ID: f2a6c1d4b8e9
Revises: e9b7c6a5d4f2
Create Date: 2026-05-06 00:00:02.000000

"""
from typing import Sequence, Union
import hashlib

from alembic import op
import sqlalchemy as sa


revision: str = "f2a6c1d4b8e9"
down_revision: Union[str, Sequence[str], None] = "e9b7c6a5d4f2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def upgrade() -> None:
    bind = op.get_bind()
    refresh_tokens = sa.table(
        "refresh_tokens",
        sa.column("id", sa.Integer),
        sa.column("token", sa.String),
    )
    otps = sa.table(
        "otps",
        sa.column("id", sa.Integer),
        sa.column("otp", sa.String),
    )

    refresh_rows = bind.execute(
        sa.select(refresh_tokens.c.id, refresh_tokens.c.token)
    ).mappings()
    for row in refresh_rows:
        token = row["token"]
        if token and len(token) != 64:
            bind.execute(
                refresh_tokens.update()
                .where(refresh_tokens.c.id == row["id"])
                .values(token=_sha256_hex(token))
            )

    otp_rows = bind.execute(
        sa.select(otps.c.id, otps.c.otp)
    ).mappings()
    for row in otp_rows:
        otp = row["otp"]
        if otp and len(otp) != 64:
            bind.execute(
                otps.update()
                .where(otps.c.id == row["id"])
                .values(otp=_sha256_hex(otp))
            )


def downgrade() -> None:
    pass
