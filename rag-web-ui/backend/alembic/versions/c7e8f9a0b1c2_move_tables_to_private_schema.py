"""move tables to rag_private schema

Revision ID: c7e8f9a0b1c2
Revises: a1f4c5d8e9b0
Create Date: 2026-06-02 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from app.db.schema import APP_TABLES, SCHEMA_MIGRATION_REVISION, VECTOR_TABLES

# revision identifiers, used by Alembic.
revision: str = SCHEMA_MIGRATION_REVISION
down_revision: Union[str, None] = "a1f4c5d8e9b0"
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
    op.execute(sa.text(f'GRANT USAGE ON SCHEMA "{SCHEMA_NAME}" TO CURRENT_USER'))
    op.execute(sa.text(f'GRANT CREATE ON SCHEMA "{SCHEMA_NAME}" TO CURRENT_USER'))

    conn = op.get_bind()
    for table_name in (*APP_TABLES, *VECTOR_TABLES):
        in_public = _table_in_schema(conn, "public", table_name)
        in_private = _table_in_schema(conn, SCHEMA_NAME, table_name)
        if in_public and in_private:
            op.execute(sa.text(f'DROP TABLE IF EXISTS "public"."{table_name}" CASCADE'))
        elif in_public:
            _move_table("public", SCHEMA_NAME, table_name)

    in_public_ver = _table_in_schema(conn, "public", "alembic_version")
    in_private_ver = _table_in_schema(conn, SCHEMA_NAME, "alembic_version")
    if in_public_ver and in_private_ver:
        op.execute(sa.text('DROP TABLE IF EXISTS "public"."alembic_version" CASCADE'))
    elif in_public_ver:
        _move_table("public", SCHEMA_NAME, "alembic_version")


def downgrade() -> None:
    conn = op.get_bind()
    for table_name in reversed((*APP_TABLES, *VECTOR_TABLES)):
        if _table_in_schema(conn, SCHEMA_NAME, table_name):
            _move_table(SCHEMA_NAME, "public", table_name)

    if _table_in_schema(conn, SCHEMA_NAME, "alembic_version"):
        _move_table(SCHEMA_NAME, "public", "alembic_version")
