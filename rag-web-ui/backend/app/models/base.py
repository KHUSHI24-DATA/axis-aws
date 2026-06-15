from datetime import datetime

from sqlalchemy import Column, DateTime, MetaData
from sqlalchemy.orm import declarative_base

from app.core.config import settings

metadata = MetaData(schema=settings.effective_postgres_schema)
Base = declarative_base(metadata=metadata)

class TimestampMixin:
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False) 