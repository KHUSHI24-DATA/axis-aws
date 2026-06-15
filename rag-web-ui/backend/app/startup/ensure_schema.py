"""Ensure app tables exist in the configured PostgreSQL schema (e.g. rag_private)."""
from sqlalchemy import create_engine, text, inspect

from app.core.config import settings
from app.models.base import Base
import app.models.user  # noqa: F401
import app.models.knowledge  # noqa: F401
import app.models.chat  # noqa: F401
import app.models.api_key  # noqa: F401


def _ensure_document_upload_columns(conn, schema: str | None) -> None:
    if not schema:
        return
    inspector = inspect(conn)
    if "document_uploads" not in inspector.get_table_names(schema=schema):
        return
    columns = {c["name"] for c in inspector.get_columns("document_uploads", schema=schema)}
    if "file_data" not in columns:
        print(f"Adding missing {schema}.document_uploads.file_data column ...")
        conn.execute(
            text(
                f'ALTER TABLE "{schema}"."document_uploads" '
                "ADD COLUMN IF NOT EXISTS file_data BYTEA"
            )
        )
        conn.commit()


def ensure_tables() -> None:
    schema = settings.effective_postgres_schema
    engine = create_engine(
        settings.get_database_url,
        connect_args=settings.postgres_connect_args,
    )
    with engine.connect() as conn:
        if schema:
            conn.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{schema}"'))
            conn.commit()
        inspector = inspect(conn)
        existing = set(inspector.get_table_names(schema=schema)) if schema else set(inspector.get_table_names())
        if "users" in existing:
            _ensure_document_upload_columns(conn, schema)
            print(f"Schema tables OK ({schema or 'public'})")
            return
        print(f"Creating missing tables in schema {schema or 'public'} ...")
        Base.metadata.create_all(bind=conn)
        conn.commit()
        _ensure_document_upload_columns(conn, schema)
        print("Schema tables created.")


if __name__ == "__main__":
    ensure_tables()
