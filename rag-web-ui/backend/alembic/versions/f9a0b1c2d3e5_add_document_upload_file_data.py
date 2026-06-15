"""add file_data column to document_uploads

Revision ID: f9a0b1c2d3e5
Revises: e8f9a0b1c2d4
Create Date: 2026-06-08 16:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "f9a0b1c2d3e5"
down_revision: Union[str, None] = "e8f9a0b1c2d4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_exists(conn, schema: str, table: str, column: str) -> bool:
    return bool(
        conn.execute(
            sa.text(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_schema = :schema AND table_name = :table "
                "AND column_name = :column"
            ),
            {"schema": schema, "table": table, "column": column},
        ).scalar()
    )


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
        if _column_exists(conn, schema, "document_uploads", "file_data"):
            continue
        op.execute(
            sa.text(
                f'ALTER TABLE "{schema}"."document_uploads" '
                "ADD COLUMN IF NOT EXISTS file_data BYTEA"
            )
        )


def downgrade() -> None:
    conn = op.get_bind()
    for schema in ("rag_private", "public"):
        if not _table_exists(conn, schema, "document_uploads"):
            continue
        if not _column_exists(conn, schema, "document_uploads", "file_data"):
            continue
        op.drop_column("document_uploads", "file_data", schema=schema)
