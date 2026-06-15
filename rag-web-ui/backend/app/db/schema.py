from typing import Optional

from sqlalchemy import text
from sqlalchemy.engine import Connection

from app.core.config import settings

SCHEMA_MIGRATION_REVISION = "c7e8f9a0b1c2"

APP_TABLES = (
    "users",
    "knowledge_bases",
    "documents",
    "document_chunks",
    "chats",
    "chat_knowledge_bases",
    "messages",
    "processing_tasks",
    "document_uploads",
    "api_keys",
)

VECTOR_TABLES = (
    "langchain_pg_collection",
    "langchain_pg_embedding",
)


def target_schema() -> Optional[str]:
    name = (settings.POSTGRES_SCHEMA or "").strip()
    if not name or name.lower() == "public":
        return None
    return name


def quoted_schema(schema: str) -> str:
    return f'"{schema.replace(chr(34), chr(34) * 2)}"'


def table_exists(connection: Connection, schema: str, table_name: str) -> bool:
    return bool(
        connection.execute(
            text(
                "SELECT 1 FROM information_schema.tables "
                "WHERE table_schema = :schema AND table_name = :table_name"
            ),
            {"schema": schema, "table_name": table_name},
        ).scalar()
    )


def resolve_version_table_schema(connection: Connection) -> Optional[str]:
    schema = target_schema()
    if not schema:
        return None
    if table_exists(connection, schema, "alembic_version"):
        return schema
    if table_exists(connection, "public", "alembic_version"):
        return None
    return schema


def apply_search_path(connection: Connection) -> None:
    schema = target_schema()
    if not schema:
        return
    qschema = quoted_schema(schema)
    if table_exists(connection, "public", "alembic_version"):
        connection.execute(text(f"SET search_path TO public, {qschema}"))
        return
    connection.execute(text(f"SET search_path TO {qschema}, public"))
