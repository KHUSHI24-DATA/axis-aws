"""Ensure app tables exist in the configured PostgreSQL schema (e.g. rag_private)."""
from sqlalchemy import create_engine, text, inspect

from app.core.config import settings
from app.models.base import Base
import app.models.user  # noqa: F401
import app.models.knowledge  # noqa: F401
import app.models.chat  # noqa: F401
import app.models.api_key  # noqa: F401

CODE_BRANCH_TABLES = ("document_contents", "document_faqs", "faq_feedbacks")


def _table_columns(conn, schema: str | None, table: str) -> set[str]:
    inspector = inspect(conn)
    if table not in inspector.get_table_names(schema=schema):
        return set()
    return {c["name"] for c in inspector.get_columns(table, schema=schema)}


def _ensure_code_branch_tables(conn, schema: str | None) -> None:
    """Create or repair FAQ/content tables required by the Code branch."""
    if not schema:
        return

    inspector = inspect(conn)
    existing = set(inspector.get_table_names(schema=schema))
    faq_columns = _table_columns(conn, schema, "document_faqs")

    # Legacy document_faqs from main branch used knowledge_base_id / review_status.
    if faq_columns and "knowledge_base_id" in faq_columns:
        print(f"Replacing legacy {schema}.document_faqs table with Code branch schema ...")
        conn.execute(text(f'DROP TABLE IF EXISTS "{schema}"."document_faqs" CASCADE'))
        conn.commit()
        existing.discard("document_faqs")

    missing = [t for t in CODE_BRANCH_TABLES if t not in existing]
    if missing:
        print(f"Creating missing tables in {schema}: {', '.join(missing)}")
        tables_to_create = [
            t for t in Base.metadata.sorted_tables if t.name in missing
        ]
        Base.metadata.create_all(bind=conn, tables=tables_to_create)
        conn.commit()


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
            _ensure_code_branch_tables(conn, schema)
            print(f"Schema tables OK ({schema or 'public'})")
            return
        print(f"Creating missing tables in schema {schema or 'public'} ...")
        Base.metadata.create_all(bind=conn)
        conn.commit()
        _ensure_document_upload_columns(conn, schema)
        print("Schema tables created.")


if __name__ == "__main__":
    ensure_tables()
