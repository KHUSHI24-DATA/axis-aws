#!/bin/sh

# exit on error
set -e

DB_HOST="${POSTGRES_SERVER:-pgvector}"
DB_PORT="${POSTGRES_PORT:-5432}"
echo "Waiting for PostgreSQL at ${DB_HOST}:${DB_PORT}..."
while ! nc -z "$DB_HOST" "$DB_PORT"; do
  sleep 1
done
echo "PostgreSQL started"

echo "Ensuring pgvector extension and private schema..."
python -c "
import os
import psycopg
host = os.environ.get('POSTGRES_SERVER', 'localhost')
port = int(os.environ.get('POSTGRES_PORT', '5432'))
user = os.environ.get('POSTGRES_USER', 'ragwebui')
password = os.environ.get('POSTGRES_PASSWORD', 'ragwebui')
db = os.environ.get('POSTGRES_DATABASE', 'ragwebui')
schema = (os.environ.get('POSTGRES_SCHEMA') or 'rag_private').strip()
conn = psycopg.connect(host=host, port=port, user=user, password=password, dbname=db)
conn.execute('CREATE EXTENSION IF NOT EXISTS vector')
if schema and schema.lower() != 'public':
    conn.execute(f'CREATE SCHEMA IF NOT EXISTS \"{schema}\"')
    conn.execute(f'GRANT USAGE ON SCHEMA \"{schema}\" TO \"{user}\"')
    conn.execute(f'GRANT CREATE ON SCHEMA \"{schema}\" TO \"{user}\"')
conn.commit()
conn.close()
print('pgvector extension and schema ready')
" || echo "pgvector/schema step skipped"

echo "Running migrations..."
if alembic upgrade head; then
  echo "Migrations completed successfully"
else
  echo "Migration failed"
  exit 1
fi

echo "Ensuring schema tables..."
python -m app.startup.ensure_schema || echo "ensure_schema step skipped"

echo "Starting application..."
if [ "$ENVIRONMENT" = "development" ]; then
  uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
else
  uvicorn app.main:app --host 0.0.0.0 --port 8000
fi
