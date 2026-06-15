"""create app tables in rag_private when missing

Revision ID: e8f9a0b1c2d4
Revises: d8f9a0b1c2d3
Create Date: 2026-06-08 14:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from app.db.schema import APP_TABLES, VECTOR_TABLES

revision: str = "e8f9a0b1c2d4"
down_revision: Union[str, None] = "d8f9a0b1c2d3"
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

    if _table_in_schema(conn, SCHEMA_NAME, "users"):
        return

    for table_name in (*APP_TABLES, *VECTOR_TABLES):
        if _table_in_schema(conn, "public", table_name):
            _move_table("public", SCHEMA_NAME, table_name)

    if _table_in_schema(conn, SCHEMA_NAME, "users"):
        return

    # Neither schema has tables — create from SQLAlchemy models in rag_private
    from app.models.base import Base
    import app.models.user  # noqa: F401
    import app.models.knowledge  # noqa: F401
    import app.models.chat  # noqa: F401
    import app.models.api_key  # noqa: F401

    Base.metadata.create_all(bind=conn, checkfirst=True)


def downgrade() -> None:
    pass
