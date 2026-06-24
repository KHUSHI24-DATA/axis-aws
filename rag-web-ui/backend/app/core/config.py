from functools import lru_cache
from typing import List, Optional

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    PROJECT_NAME: str = "RAG Web UI"  # Project name
    VERSION: str = "0.1.0"  # Project version
    API_V1_STR: str = "/api"  # API version string

    # General configuration
    # Note: keep auth enabled by default for safety; disable via `.env` when desired.
    AUTH_ENABLED: bool = True
    DEFAULT_USER_ID: str = "admin"

    # Document processing config
    CHUNK_SIZE: int = 1000
    CHUNK_OVERLAP: int = 200
    USE_SEMANTIC_CHUNKING: bool = True

    # FAQ generation
    FAQ_GENERATION_ENABLED: bool = True
    FAQ_MAX_FAQS: int = 30
    FAQ_MIN_FAQS: int = 3
    FAQ_GENERATION_TIMEOUT: int = 120
    LOCAL_UPLOAD_DIR: str = "/app/uploads"
    # local = disk under LOCAL_UPLOAD_DIR; s3 = ephemeral uploads in S3_UPLOAD_BUCKET
    UPLOAD_STORAGE: str = "local"
    S3_UPLOAD_BUCKET: str = ""
    AWS_REGION: str = "ap-south-1"
    # Keep in sync with `.env.example` and frontend upload accept lists.
    SUPPORTED_EXTENSIONS: str = (
        ".pdf,.docx,.md,.txt,.pptx,.ppt,.xlsx,.xls"
    )

    @property
    def supported_extensions_list(self) -> List[str]:
        return [ext.strip() for ext in self.SUPPORTED_EXTENSIONS.split(",") if ext.strip()]

    # PostgreSQL settings (primary relational DB)
    POSTGRES_SERVER: str = "pgvector"
    POSTGRES_PORT: int = 5432
    POSTGRES_USER: str = "ragwebui"
    POSTGRES_PASSWORD: str = "ragwebui"
    POSTGRES_DATABASE: str = "ragwebui"
    # PostgreSQL schema for app + pgvector tables (default: rag_private, not public)
    POSTGRES_SCHEMA: str = "rag_private"
    SQLALCHEMY_DATABASE_URI: Optional[str] = None

    @property
    def effective_postgres_schema(self) -> Optional[str]:
        name = (self.POSTGRES_SCHEMA or "").strip()
        if not name or name.lower() == "public":
            return None
        return name

    @property
    def postgres_connect_args(self) -> dict:
        schema = self.effective_postgres_schema
        if not schema:
            return {}
        return {"options": f"-csearch_path={schema},public"}

    @property
    def get_database_url(self) -> str:
        if self.SQLALCHEMY_DATABASE_URI:
            return self.SQLALCHEMY_DATABASE_URI
        return (
            f"postgresql+psycopg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_SERVER}:{self.POSTGRES_PORT}/{self.POSTGRES_DATABASE}"
        )

    # JWT settings
    SECRET_KEY: str = "your-secret-key-here"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 10080

    # Chat Provider settings
    CHAT_PROVIDER: str = "openai"

    # Embeddings settings
    EMBEDDINGS_PROVIDER: str = "openai"

    # MinIO settings
    MINIO_ENDPOINT: str = "localhost:9000"
    MINIO_ACCESS_KEY: str = "minioadmin"
    MINIO_SECRET_KEY: str = "minioadmin"
    MINIO_BUCKET_NAME: str = "documents"

    # OpenAI settings
    OPENAI_API_BASE: str = "https://api.openai.com/v1"
    OPENAI_API_KEY: str = "your-openai-api-key-here"
    OPENAI_MODEL: str = "gpt-4"
    OPENAI_EMBEDDINGS_MODEL: str = "text-embedding-ada-002"

    # Azure OpenAI settings
    AZURE_OPENAI_ENDPOINT: str = ""
    AZURE_OPENAI_API_VERSION: str = "2024-02-01"
    AZURE_OPENAI_API_KEY: str = ""
    AZURE_OPENAI_DEPLOYMENT: str = ""
    AZURE_OPENAI_EMBEDDINGS_DEPLOYMENT: str = ""

    # DashScope settings
    DASH_SCOPE_API_KEY: str = ""
    DASH_SCOPE_EMBEDDINGS_MODEL: str = ""

    # AWS Bedrock embeddings settings
    AWS_BEDROCK_REGION: str = ""
    AWS_BEDROCK_EMBEDDINGS_MODEL: str = "amazon.titan-embed-text-v2:0"
    AWS_BEDROCK_PROFILE: str = ""
    AWS_ACCESS_KEY_ID: str = ""
    AWS_SECRET_ACCESS_KEY: str = ""
    AWS_SESSION_TOKEN: str = ""

    # Vector Store settings
    VECTOR_STORE_TYPE: str = "pgvector"

    # Chroma DB settings
    CHROMA_DB_HOST: str = "chromadb"
    CHROMA_DB_PORT: int = 8000

    # Qdrant DB settings
    QDRANT_URL: str = "http://localhost:6333"
    QDRANT_PREFER_GRPC: bool = True

    # PGVector settings (optional; defaults to SQLAlchemy URL from POSTGRES_*)
    PGVECTOR_CONNECTION: str = ""

    @property
    def effective_pgvector_connection(self) -> str:
        """Legacy URL form; prefer pgvector_engine() for correct schema search_path."""
        base = self.PGVECTOR_CONNECTION.strip() or self.get_database_url
        schema = self.effective_postgres_schema
        if not schema or "search_path" in base or "options=" in base:
            return base
        from urllib.parse import quote

        option = quote(f"-csearch_path={schema},public", safe="")
        sep = "&" if "?" in base else "?"
        return f"{base}{sep}options={option}"

    # Deepseek settings
    DEEPSEEK_API_KEY: str = ""
    DEEPSEEK_API_BASE: str = "https://api.deepseek.com/v1"  # 默认 API 地址
    DEEPSEEK_MODEL: str = "deepseek-chat"  # 默认模型名称

    # Ollama settings
    OLLAMA_API_BASE: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "deepseek-r1:7b"
    OLLAMA_EMBEDDINGS_MODEL: str = "nomic-embed-text"

    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()


@lru_cache
def pgvector_engine():
    """Shared SQLAlchemy engine for PGVector (honours POSTGRES_SCHEMA via search_path)."""
    from sqlalchemy import create_engine

    return create_engine(
        settings.get_database_url,
        connect_args=settings.postgres_connect_args,
        pool_pre_ping=True,
    )


def resolve_pgvector_connection():
    """
    Connection for langchain PGVector.

    Matches optimizations-branch local setup (PGVECTOR_CONNECTION string) while
    keeping rag_private search_path when POSTGRES_SCHEMA is set.
    """
    if settings.PGVECTOR_CONNECTION.strip():
        return settings.effective_pgvector_connection
    return pgvector_engine()
