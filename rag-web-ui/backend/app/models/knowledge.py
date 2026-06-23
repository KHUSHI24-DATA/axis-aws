from sqlalchemy import Column, Integer, String, ForeignKey, Text, DateTime, JSON, BigInteger, TIMESTAMP, LargeBinary, text
from sqlalchemy.orm import relationship
from app.models.base import Base, TimestampMixin
from datetime import datetime
import sqlalchemy as sa

class KnowledgeBase(Base, TimestampMixin):
    __tablename__ = "knowledge_bases"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    description = Column(Text)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    documents = relationship("Document", back_populates="knowledge_base", cascade="all, delete-orphan")
    user = relationship("User", back_populates="knowledge_bases")
    processing_tasks = relationship("ProcessingTask", back_populates="knowledge_base")
    chunks = relationship("DocumentChunk", back_populates="knowledge_base", cascade="all, delete-orphan")
    document_uploads = relationship("DocumentUpload", back_populates="knowledge_base", cascade="all, delete-orphan")

class Document(Base, TimestampMixin):
    __tablename__ = "documents"

    id = Column(Integer, primary_key=True, index=True)
    file_path = Column(String(255), nullable=False)  # Path in MinIO
    file_name = Column(String(255), nullable=False)  # Actual file name
    file_size = Column(BigInteger, nullable=False)  # File size in bytes
    content_type = Column(String(100), nullable=False)  # MIME type
    file_hash = Column(String(64), index=True)  # SHA-256 hash of file content
    knowledge_base_id = Column(Integer, ForeignKey("knowledge_bases.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    knowledge_base = relationship("KnowledgeBase", back_populates="documents") 
    processing_tasks = relationship("ProcessingTask", back_populates="document")
    chunks = relationship("DocumentChunk", back_populates="document", cascade="all, delete-orphan")

    __table_args__ = (
        # Ensure file_name is unique within each knowledge base
        sa.UniqueConstraint('knowledge_base_id', 'file_name', name='uq_kb_file_name'),
    )

class DocumentUpload(Base):
    __tablename__ = "document_uploads"
    
    id = Column(Integer, primary_key=True, index=True)
    knowledge_base_id = Column(Integer, ForeignKey("knowledge_bases.id", ondelete="CASCADE"), nullable=False)
    file_name = Column(String, nullable=False)
    file_hash = Column(String, nullable=False)
    file_size = Column(BigInteger, nullable=False)
    content_type = Column(String, nullable=False)
    temp_path = Column(String, nullable=False)
    file_data = Column(LargeBinary, nullable=True)
    created_at = Column(TIMESTAMP, nullable=False, server_default=text("now()"))
    status = Column(String, nullable=False, server_default="pending")
    error_message = Column(Text)
    
    # Relationships
    knowledge_base = relationship("KnowledgeBase", back_populates="document_uploads")

class ProcessingTask(Base):
    __tablename__ = "processing_tasks"

    id = Column(Integer, primary_key=True, index=True)
    knowledge_base_id = Column(Integer, ForeignKey("knowledge_bases.id"))
    document_id = Column(Integer, ForeignKey("documents.id"), nullable=True)
    document_upload_id = Column(Integer, ForeignKey("document_uploads.id"), nullable=True)
    status = Column(String(50), default="pending")  # pending, processing, completed, failed
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    knowledge_base = relationship("KnowledgeBase", back_populates="processing_tasks")
    document = relationship("Document", back_populates="processing_tasks")
    document_upload = relationship("DocumentUpload", backref="processing_tasks")

class DocumentChunk(Base, TimestampMixin):
    __tablename__ = "document_chunks"

    id = Column(String(64), primary_key=True)  # SHA-256 hash as ID
    kb_id = Column(Integer, ForeignKey("knowledge_bases.id"), nullable=False)
    document_id = Column(Integer, ForeignKey("documents.id"), nullable=False)
    file_name = Column(String(255), nullable=False)
    chunk_metadata = Column(JSON, nullable=True)
    hash = Column(String(64), nullable=False, index=True)  # Content hash for change detection
    
    # Relationships
    knowledge_base = relationship("KnowledgeBase", back_populates="chunks")
    document = relationship("Document", back_populates="chunks")

    __table_args__ = (
        sa.Index('idx_kb_file_name', 'kb_id', 'file_name'),
    )


class DocumentContent(Base, TimestampMixin):
    """Stores extracted content from documents"""
    __tablename__ = "document_contents"

    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)
    raw_text = Column(Text, nullable=False)  # Full extracted text
    content_length = Column(Integer)  # Character count
    extracted_at = Column(DateTime, default=datetime.utcnow)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    document = relationship("Document", backref="content")


class DocumentFAQ(Base, TimestampMixin):
    """Stores FAQ entries generated from documents"""
    __tablename__ = "document_faqs"

    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)
    question = Column(Text, nullable=False)
    answer = Column(Text, nullable=False)
    is_verified = Column(sa.Boolean, default=False)  # Whether FAQ has been reviewed
    feedback_status = Column(String(20), default="pending")  # pending, correct, incorrect
    corrected_answer = Column(Text, nullable=True)  # If marked incorrect
    is_auto_generated = Column(sa.Boolean, default=True)  # Distinguish auto-generated from manually added
    confidence_score = Column(sa.Float, nullable=True)  # Confidence of LLM in the FAQ
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    
    # Relationships
    document = relationship("Document", backref="faqs")
    creator = relationship("User", backref="created_faqs")
    feedbacks = relationship("FAQFeedback", back_populates="faq", cascade="all, delete-orphan")


class FAQFeedback(Base, TimestampMixin):
    """Tracks feedback history for FAQs"""
    __tablename__ = "faq_feedbacks"

    id = Column(Integer, primary_key=True, index=True)
    faq_id = Column(Integer, ForeignKey("document_faqs.id", ondelete="CASCADE"), nullable=False)
    feedback_type = Column(String(20), nullable=False)  # correct, incorrect
    corrected_answer = Column(Text, nullable=True)
    reviewer_notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    
    # Relationships
    faq = relationship("DocumentFAQ", back_populates="feedbacks")
    reviewer = relationship("User", backref="faq_feedbacks")