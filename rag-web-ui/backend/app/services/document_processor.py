import logging
import os
import hashlib
import tempfile
import traceback
from datetime import datetime
from pathlib import Path
from app.db.session import SessionLocal
from io import BytesIO
from typing import Optional, List, Dict, Set
from fastapi import UploadFile
from langchain_community.document_loaders import (
    PyPDFLoader,
    Docx2txtLoader,
    UnstructuredMarkdownLoader,
    TextLoader,
)
from langchain_core.documents import Document as LangchainDocument
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.core.config import settings
from app.models.knowledge import ProcessingTask, Document, DocumentChunk, DocumentContent, DocumentFAQ
from app.services.chunk_record import ChunkRecord
from app.services.faq_generator import get_faq_generator
from app.services.text_splitter import get_text_splitter
from app.services.vector_store import VectorStoreFactory
from app.services.embedding.embedding_factory import EmbeddingsFactory
from app.services.upload_storage import upload_storage


class UploadResult(BaseModel):
    file_path: str
    file_name: str
    file_size: int
    content_type: str
    file_hash: str


class TextChunk(BaseModel):
    content: str
    metadata: Optional[Dict] = None


class PreviewResult(BaseModel):
    chunks: List[TextChunk]
    total_chunks: int


async def process_document(
    file_path: str,
    file_name: str,
    kb_id: int,
    document_id: int,
    chunk_size: int = None,
    chunk_overlap: int = None,
) -> None:
    chunk_size = chunk_size or settings.CHUNK_SIZE
    chunk_overlap = chunk_overlap or settings.CHUNK_OVERLAP
    """Process document and store in vector database with incremental updates"""
    logger = logging.getLogger(__name__)

    try:
        preview_result = await preview_document(file_path, chunk_size, chunk_overlap)

        # Initialize embeddings
        logger.info("Initializing OpenAI embeddings...")
        embeddings = EmbeddingsFactory.create()

        logger.info(f"Initializing vector store with collection: kb_{kb_id}")
        vector_store = VectorStoreFactory.create(
            store_type=settings.VECTOR_STORE_TYPE,
            collection_name=f"kb_{kb_id}",
            embedding_function=embeddings,
        )

        # Initialize chunk record manager
        chunk_manager = ChunkRecord(kb_id)

        # Get existing chunk hashes for this file
        existing_hashes = chunk_manager.list_chunks(file_name)

        # Prepare new chunks
        new_chunks = []
        current_hashes = set()
        documents_to_update = []

        for chunk in preview_result.chunks:
            # Calculate chunk hash
            chunk_hash = hashlib.sha256(
                (chunk.content + str(chunk.metadata)).encode()
            ).hexdigest()
            current_hashes.add(chunk_hash)

            # Skip if chunk hasn't changed
            if chunk_hash in existing_hashes:
                continue

            # Create unique ID for the chunk
            chunk_id = hashlib.sha256(
                f"{kb_id}:{file_name}:{chunk_hash}".encode()
            ).hexdigest()

            # Prepare chunk record
            # Prepare metadata
            metadata = {
                **chunk.metadata,
                "chunk_id": chunk_id,
                "file_name": file_name,
                "kb_id": kb_id,
                "document_id": document_id,
            }

            new_chunks.append(
                {
                    "id": chunk_id,
                    "kb_id": kb_id,
                    "document_id": document_id,
                    "file_name": file_name,
                    "metadata": metadata,
                    "hash": chunk_hash,
                }
            )

            # Prepare document for vector store
            doc = LangchainDocument(page_content=chunk.content, metadata=metadata)
            documents_to_update.append(doc)

        # Add new chunks to database and vector store
        if new_chunks:
            logger.info(f"Adding {len(new_chunks)} new/updated chunks")
            chunk_manager.add_chunks(new_chunks)
            vector_store.add_documents(documents_to_update)

        # Delete removed chunks
        chunks_to_delete = chunk_manager.get_deleted_chunks(current_hashes, file_name)
        if chunks_to_delete:
            logger.info(f"Removing {len(chunks_to_delete)} deleted chunks")
            chunk_manager.delete_chunks(chunks_to_delete)
            vector_store.delete(chunks_to_delete)

        logger.info("Document processing completed successfully")

    except Exception as e:
        logger.error(f"Error processing document: {str(e)}")
        raise


async def upload_document(file: UploadFile, kb_id: int) -> UploadResult:
    """Step 1: Upload document to local temporary storage."""
    content = await file.read()
    file_size = len(content)

    file_hash = hashlib.sha256(content).hexdigest()

    # Clean and normalize filename
    file_name = "".join(
        c for c in file.filename if c.isalnum() or c in ("-", "_", ".")
    ).strip()
    object_path = f"kb_{kb_id}/{file_name}"

    content_types = {
        ".pdf": "application/pdf",
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".md": "text/markdown",
        ".txt": "text/plain",
        ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        ".ppt": "application/vnd.ms-powerpoint",
        ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ".xls": "application/vnd.ms-excel",
    }

    _, ext = os.path.splitext(file_name)
    content_type = content_types.get(ext.lower(), "application/octet-stream")

    try:
        storage_path = upload_storage.save_temp_bytes(kb_id, file_name, content)
    except (OSError, ValueError) as e:
        logging.error(f"Failed to write uploaded file: {str(e)}")
        raise

    return UploadResult(
        file_path=storage_path,
        file_name=file_name,
        file_size=file_size,
        content_type=content_type,
        file_hash=file_hash,
    )


async def preview_document(
    file_path: str, chunk_size: int = None, chunk_overlap: int = None
) -> PreviewResult:
    chunk_size = chunk_size or settings.CHUNK_SIZE
    chunk_overlap = chunk_overlap or settings.CHUNK_OVERLAP
    """Step 2: Generate preview chunks from stored upload (local path or S3)."""
    _, ext = os.path.splitext(file_path)
    ext = ext.lower()

    with upload_storage.local_path_for_reading(file_path) as temp_path:
        return await _preview_from_local_path(
            temp_path, ext, chunk_size, chunk_overlap
        )


async def _preview_from_local_path(
    temp_path: str,
    ext: str,
    chunk_size: int,
    chunk_overlap: int,
) -> PreviewResult:
    try:
        if ext == ".pdf":
            loader = PyPDFLoader(temp_path)
        elif ext == ".docx":
            loader = Docx2txtLoader(temp_path)
        elif ext == ".md":
            loader = UnstructuredMarkdownLoader(temp_path)
        elif ext in [".pptx", ".ppt"]:
            from langchain_community.document_loaders import (
                UnstructuredPowerPointLoader,
            )

            loader = UnstructuredPowerPointLoader(temp_path)
        elif ext in [".xlsx", ".xls"]:
            import pandas as pd

            text_path = temp_path + ".txt"
            dfs = pd.read_excel(temp_path, sheet_name=None)
            with open(text_path, "w", encoding="utf-8") as f:
                for sheet_name, df in dfs.items():
                    f.write(f"--- Sheet: {sheet_name} ---\n")
                    df = df.fillna("")
                    headers = df.columns.tolist()
                    for index, row in df.iterrows():
                        row_str = " | ".join(
                            [
                                f"{col}: {row[col]}"
                                for col in headers
                                if str(row[col]).strip() != ""
                            ]
                        )
                        if row_str:
                            f.write(f"Row {index + 1}: {row_str}\n")
                    f.write("\n")
            loader = TextLoader(text_path)
        else:  # Default to text loader
            loader = TextLoader(temp_path)

        # Load and split the document
        documents = loader.load()
        text_splitter = get_text_splitter(
            chunk_size=chunk_size, chunk_overlap=chunk_overlap
        )
        chunks = text_splitter.split_documents(documents)

        # Convert to preview format
        preview_chunks = [
            TextChunk(content=chunk.page_content, metadata=chunk.metadata)
            for chunk in chunks
        ]

        return PreviewResult(chunks=preview_chunks, total_chunks=len(chunks))
    finally:
        derived = temp_path + ".txt"
        if derived != temp_path and os.path.exists(derived):
            os.remove(derived)


async def process_document_background(
    temp_path: str,
    file_name: str,
    kb_id: int,
    task_id: int,
    db: Session = None,
    chunk_size: int = None,
    chunk_overlap: int = None,
    file_bytes: bytes | None = None,
) -> None:
    chunk_size = chunk_size or settings.CHUNK_SIZE
    chunk_overlap = chunk_overlap or settings.CHUNK_OVERLAP
    """Process document in background"""
    logger = logging.getLogger(__name__)
    logger.info(f"Starting background processing for task {task_id}, file: {file_name}")

    # if we don't pass in db, create a new database session
    if db is None:
        db = SessionLocal()
        should_close_db = True
    else:
        should_close_db = False

    task = db.query(ProcessingTask).get(task_id)
    if not task:
        logger.error(f"Task {task_id} not found")
        return

    try:
        logger.info(f"Task {task_id}: Setting status to processing")
        task.status = "processing"
        db.commit()

        if file_bytes is not None:
            path_ctx = upload_storage.local_path_from_bytes(
                file_bytes, os.path.splitext(file_name)[1] or ".bin"
            )
        else:
            if not upload_storage.exists(temp_path):
                error_msg = f"Upload file not found: {temp_path}"
                logger.error(f"Task {task_id}: {error_msg}")
                raise Exception(error_msg)
            path_ctx = upload_storage.local_path_for_reading(temp_path)

        with path_ctx as local_temp_path:
            _, ext = os.path.splitext(file_name)
            ext = ext.lower()

            logger.info(f"Task {task_id}: Loading document with extension {ext}")
            if ext == ".pdf":
                loader = PyPDFLoader(local_temp_path)
            elif ext == ".docx":
                loader = Docx2txtLoader(local_temp_path)
            elif ext == ".md":
                loader = UnstructuredMarkdownLoader(local_temp_path)
            elif ext in [".pptx", ".ppt"]:
                from langchain_community.document_loaders import (
                    UnstructuredPowerPointLoader,
                )

                loader = UnstructuredPowerPointLoader(local_temp_path)
            elif ext in [".xlsx", ".xls"]:
                import pandas as pd

                text_path = local_temp_path + ".txt"
                dfs = pd.read_excel(local_temp_path, sheet_name=None)
                with open(text_path, "w", encoding="utf-8") as f:
                    for sheet_name, df in dfs.items():
                        f.write(f"--- Sheet: {sheet_name} ---\n")
                        df = df.fillna("")
                        headers = df.columns.tolist()
                        for index, row in df.iterrows():
                            row_str = " | ".join(
                                [
                                    f"{col}: {row[col]}"
                                    for col in headers
                                    if str(row[col]).strip() != ""
                                ]
                            )
                            if row_str:
                                f.write(f"Row {index + 1}: {row_str}\n")
                        f.write("\n")
                loader = TextLoader(text_path)
            else:  # 默认使用文本加载器
                loader = TextLoader(local_temp_path)

            logger.info(f"Task {task_id}: Loading document content")
            documents = loader.load()
            logger.info(f"Task {task_id}: Document loaded successfully")

            logger.info(f"Task {task_id}: Splitting document into chunks")
            text_splitter = get_text_splitter(
                chunk_size=chunk_size, chunk_overlap=chunk_overlap
            )
            chunks = text_splitter.split_documents(documents)
            logger.info(f"Task {task_id}: Document split into {len(chunks)} chunks")

            # 3. 创建向量存储
            logger.info(f"Task {task_id}: Initializing vector store")
            embeddings = EmbeddingsFactory.create()

            vector_store = VectorStoreFactory.create(
                store_type=settings.VECTOR_STORE_TYPE,
                collection_name=f"kb_{kb_id}",
                embedding_function=embeddings,
            )

            # 4. 创建文档记录（不保留原文件，仅保留 checksum 引用）
            logger.info(f"Task {task_id}: Creating document record")
            document = Document(
                file_name=file_name,
                file_path=f"checksum://{task.document_upload.file_hash}",
                file_hash=task.document_upload.file_hash,
                file_size=task.document_upload.file_size,
                content_type=task.document_upload.content_type,
                knowledge_base_id=kb_id,
            )
            db.add(document)
            db.commit()
            db.refresh(document)
            logger.info(
                f"Task {task_id}: Document record created with ID {document.id}"
            )

            # 5. 存储文档块
            logger.info(f"Task {task_id}: Storing document chunks")
            for i, chunk in enumerate(chunks):
                # 为每个 chunk 生成唯一的 ID
                chunk_id = hashlib.sha256(
                    f"{kb_id}:{file_name}:{chunk.page_content}".encode()
                ).hexdigest()

                chunk.metadata["source"] = file_name
                chunk.metadata["kb_id"] = kb_id
                chunk.metadata["document_id"] = document.id
                chunk.metadata["chunk_id"] = chunk_id

                doc_chunk = DocumentChunk(
                    id=chunk_id,  # 添加 ID 字段
                    document_id=document.id,
                    kb_id=kb_id,
                    file_name=file_name,
                    chunk_metadata={
                        "page_content": chunk.page_content,
                        **chunk.metadata,
                    },
                    hash=hashlib.sha256(
                        (chunk.page_content + str(chunk.metadata)).encode()
                    ).hexdigest(),
                )
                db.add(doc_chunk)
                if i > 0 and i % 100 == 0:
                    logger.info(f"Task {task_id}: Stored {i} chunks")
                    db.commit()  # 每 100 条提交一次，避免事务太大

            # 6. 添加到向量存储
            logger.info(f"Task {task_id}: Adding chunks to vector store")
            vector_store.add_documents(chunks)
            # 移除 persist() 调用，因为新版本不需要
            logger.info(f"Task {task_id}: Chunks added to vector store")

            # 7. Extract content and generate FAQs
            logger.info(f"Task {task_id}: Extracting document content")
            try:
                # Combine all chunk content
                full_content = "\n\n".join([chunk.page_content for chunk in chunks])
                
                # Store extracted content
                doc_content = DocumentContent(
                    document_id=document.id,
                    raw_text=full_content,
                    content_length=len(full_content),
                )
                db.add(doc_content)
                db.commit()
                logger.info(f"Task {task_id}: Document content stored ({len(full_content)} chars)")
                
                # Generate FAQs using LLM
                if settings.FAQ_GENERATION_ENABLED:
                    logger.info(f"Task {task_id}: Starting FAQ generation")
                    faq_generator = get_faq_generator()
                    num_faqs = settings.FAQ_NUM_FAQS
                    
                    try:
                        faqs = await faq_generator.generate_faqs(
                            content=full_content,
                            num_faqs=num_faqs,
                            language="English"
                        )
                        
                        # Store FAQs in database
                        for faq_data in faqs:
                            faq = DocumentFAQ(
                                document_id=document.id,
                                question=faq_data.get("question", ""),
                                answer=faq_data.get("answer", ""),
                                confidence_score=faq_data.get("confidence_score", 0.85),
                                is_auto_generated=True,
                                feedback_status="pending",
                            )
                            db.add(faq)
                        
                        db.commit()
                        logger.info(f"Task {task_id}: Successfully generated and stored {len(faqs)} FAQs")
                    except Exception as faq_error:
                        logger.warning(f"Task {task_id}: FAQ generation failed (non-blocking): {str(faq_error)}")
                        # Don't fail the entire document processing if FAQ generation fails
                        
            except Exception as content_error:
                logger.warning(f"Task {task_id}: Content extraction/FAQ generation failed (non-blocking): {str(content_error)}")
                # Don't fail the entire document processing

            # 8. 更新任务状态
            logger.info(f"Task {task_id}: Updating task status to completed")
            task.status = "completed"
            task.document_id = document.id  # 更新为新创建的文档ID

            # 9. 更新上传记录状态
            upload = task.document_upload  # 直接通过关系获取
            if upload:
                logger.info(
                    f"Task {task_id}: Updating upload record status to completed"
                )
                upload.status = "completed"
                upload.file_data = None

            db.commit()
            logger.info(f"Task {task_id}: Processing completed successfully")

        upload_storage.delete(temp_path)

    except Exception as e:
        logger.error(f"Task {task_id}: Error processing document: {str(e)}")
        logger.error(f"Task {task_id}: Stack trace: {traceback.format_exc()}")
        task.status = "failed"
        task.error_message = str(e)
        db.commit()

        upload_storage.delete(temp_path)
    finally:
        # if we create the db session, we need to close it
        if should_close_db and db:
            db.close()
