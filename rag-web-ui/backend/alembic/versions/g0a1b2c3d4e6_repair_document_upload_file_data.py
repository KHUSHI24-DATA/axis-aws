"""repair document_uploads.file_data column if missing

Revision ID: g0a1b2c3d4e6
Revises: f9a0b1c2d3e5
Create Date: 2026-06-08 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "g0a1b2c3d4e6"
down_revision: Union[str, None] = "f9a0b1c2d3e5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_exists(conn, schema: str, table: str) -> bool:
    return bool(
        conn.execute(
            sa.text(
                "SELECT 1 FROM information_schema.tables "
                "WHERE table_schema = :schema AND table_name = :table"
            ),
            {"schema": schema, "table": table},
        ).scalar()
    )


def upgrade() -> None:
    conn = op.get_bind()
    for schema in ("rag_private", "public"):
        if not _table_exists(conn, schema, "document_uploads"):
            continue
        op.execute(
            sa.text(
                f'ALTER TABLE "{schema}"."document_uploads" '
                "ADD COLUMN IF NOT EXISTS file_data BYTEA"
            )
        )


def downgrade() -> None:
    pass
