"""ensure tables exist in rag_private schema

Revision ID: d8f9a0b1c2d3
Revises: c7e8f9a0b1c2
Create Date: 2026-06-08 14:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from app.db.schema import APP_TABLES, VECTOR_TABLES

revision: str = "d8f9a0b1c2d3"
down_revision: Union[str, None] = "c7e8f9a0b1c2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA_NAME = "rag_private"


def _table_in_schema(conn, schema: str, table_name: str) -> bool:
    return bool(
        conn.execute(
            sa.text(
                "SELECT 1 FROM information_schema.tables "
                "WHERE table_schema = :schema AND table_name = :table_name"
            ),
            {"schema": schema, "table_name": table_name},
        ).scalar()
    )


def _move_table(schema_from: str, schema_to: str, table_name: str) -> None:
    op.execute(
        sa.text(
            f'ALTER TABLE "{schema_from}"."{table_name}" SET SCHEMA "{schema_to}"'
        )
    )


def upgrade() -> None:
    op.execute(sa.text(f'CREATE SCHEMA IF NOT EXISTS "{SCHEMA_NAME}"'))
    conn = op.get_bind()
    for table_name in (*APP_TABLES, *VECTOR_TABLES):
        in_public = _table_in_schema(conn, "public", table_name)
        in_private = _table_in_schema(conn, SCHEMA_NAME, table_name)
        if in_public and not in_private:
            _move_table("public", SCHEMA_NAME, table_name)
    if _table_in_schema(conn, "public", "alembic_version") and not _table_in_schema(
        conn, SCHEMA_NAME, "alembic_version"
    ):
        _move_table("public", SCHEMA_NAME, "alembic_version")


def downgrade() -> None:
    pass
