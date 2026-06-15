from sqlalchemy import create_engine, text

from app.core.config import settings
from app.db.schema import APP_TABLES, VECTOR_TABLES

def clean_database():
    engine = create_engine(
        settings.get_database_url,
        connect_args=settings.postgres_connect_args,
    )
    schema = settings.effective_postgres_schema
    prefix = f'"{schema}".' if schema else ""
    tables = (
        "processing_tasks",
        "document_uploads",
        "alembic_version",
        *reversed(APP_TABLES),
        *reversed(VECTOR_TABLES),
    )
    with engine.connect() as conn:
        for table_name in tables:
            conn.execute(text(f"DROP TABLE IF EXISTS {prefix}{table_name} CASCADE"))
        conn.commit()

if __name__ == "__main__":
    clean_database()
    print("Database cleaned successfully") 