import logging
import math
from typing import Any, Dict, List, Optional, TypedDict

from langchain_core.documents import Document as LangchainDocument
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.knowledge import Document, DocumentFAQ
from app.services.embedding.embedding_factory import EmbeddingsFactory
from app.services.vector_store import VectorStoreFactory
from app.utils.text_sanitizer import sanitize_documents

logger = logging.getLogger(__name__)

FAQ_MATCH_THRESHOLD = 0.78


class FaqMatchResult(TypedDict):
    answer: str
    context: List[Dict[str, Any]]


def get_effective_faq_answer(faq: DocumentFAQ) -> Optional[str]:
    if faq.feedback_status not in {"correct", "incorrect"}:
        return None
    if faq.feedback_status == "incorrect":
        answer = (faq.corrected_answer or "").strip()
    else:
        answer = (faq.answer or "").strip()
    return answer or None


def _cosine_similarity(vec_a: List[float], vec_b: List[float]) -> float:
    if not vec_a or not vec_b or len(vec_a) != len(vec_b):
        return 0.0
    dot = sum(a * b for a, b in zip(vec_a, vec_b))
    norm_a = math.sqrt(sum(a * a for a in vec_a))
    norm_b = math.sqrt(sum(b * b for b in vec_b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def _normalize_text(value: str) -> str:
    import re

    return re.sub(r"\s+", " ", value or "").strip().lower()


def sync_verified_faq_to_vector_store(
    kb_id: int,
    document: Document,
    faq: DocumentFAQ,
) -> None:
    """Upsert a verified FAQ Q&A pair into the KB vector store."""
    effective_answer = get_effective_faq_answer(faq)
    if not effective_answer:
        return

    try:
        embeddings = EmbeddingsFactory.create()
        vector_store = VectorStoreFactory.create(
            store_type=settings.VECTOR_STORE_TYPE,
            collection_name=f"kb_{kb_id}",
            embedding_function=embeddings,
        )
        chunk_id = f"verified_faq_{faq.id}"
        page_content = f"Question: {faq.question}\nAnswer: {effective_answer}"
        doc = LangchainDocument(
            page_content=page_content,
            metadata={
                "source": document.file_name,
                "kb_id": kb_id,
                "document_id": document.id,
                "faq_id": faq.id,
                "source_type": "verified_faq",
                "chunk_id": chunk_id,
            },
        )

        try:
            vector_store.delete([chunk_id])
        except Exception:
            pass

        safe_docs = sanitize_documents([doc])
        if not safe_docs:
            return

        store = getattr(vector_store, "_store", None)
        if store is not None:
            store.add_documents(safe_docs, ids=[chunk_id])
        else:
            vector_store.add_documents(safe_docs)
    except Exception as exc:
        logger.warning("Failed to sync verified FAQ %s to vector store: %s", faq.id, exc)


def _faq_context_entry(
    faq: DocumentFAQ, document: Document, answer: str
) -> Dict[str, Any]:
    return {
        "page_content": f"Question: {faq.question}\nAnswer: {answer}",
        "metadata": {
            "source": document.file_name,
            "file_name": document.file_name,
            "kb_id": document.knowledge_base_id,
            "document_id": document.id,
            "faq_id": faq.id,
            "source_type": "verified_faq",
        },
    }


def _faq_match_result(
    faq: DocumentFAQ, document: Document, answer: str
) -> FaqMatchResult:
    return {
        "answer": answer,
        "context": [_faq_context_entry(faq, document, answer)],
    }


def find_faq_corrected_answer(
    db: Session,
    query: str,
    knowledge_base_ids: List[int],
) -> Optional[FaqMatchResult]:
    """Return user-corrected FAQ answer (incorrect + corrected_answer only)."""
    normalized_query = _normalize_text(query)
    if not normalized_query:
        return None

    faqs = (
        db.query(DocumentFAQ)
        .join(Document, DocumentFAQ.document_id == Document.id)
        .filter(
            Document.knowledge_base_id.in_(knowledge_base_ids),
            DocumentFAQ.feedback_status == "incorrect",
            DocumentFAQ.corrected_answer.isnot(None),
        )
        .all()
    )
    if not faqs:
        return None

    for faq in faqs:
        corrected = (faq.corrected_answer or "").strip()
        if not corrected:
            continue
        if _normalize_text(faq.question) == normalized_query:
            return _faq_match_result(faq, faq.document, corrected)

    try:
        embeddings = EmbeddingsFactory.create()
        query_embedding = embeddings.embed_query(query)
    except Exception as exc:
        logger.warning("FAQ corrected lookup failed: %s", exc)
        return None

    best_score = 0.0
    best_match: Optional[FaqMatchResult] = None

    for faq in faqs:
        corrected = (faq.corrected_answer or "").strip()
        if not corrected:
            continue
        try:
            faq_embedding = embeddings.embed_query(faq.question)
            score = _cosine_similarity(query_embedding, faq_embedding)
        except Exception:
            continue
        if score > best_score:
            best_score = score
            best_match = _faq_match_result(faq, faq.document, corrected)

    if best_score >= FAQ_MATCH_THRESHOLD and best_match:
        return best_match

    return None


def find_verified_faq_answer(
    db: Session,
    query: str,
    knowledge_base_ids: List[int],
) -> Optional[FaqMatchResult]:
    """Return the best matching verified FAQ answer and source context."""
    normalized_query = _normalize_text(query)
    if not normalized_query:
        return None

    faqs = (
        db.query(DocumentFAQ)
        .join(Document, DocumentFAQ.document_id == Document.id)
        .filter(
            Document.knowledge_base_id.in_(knowledge_base_ids),
            DocumentFAQ.feedback_status.in_(["correct", "incorrect"]),
        )
        .all()
    )
    if not faqs:
        return None

    for faq in faqs:
        if _normalize_text(faq.question) == normalized_query:
            answer = get_effective_faq_answer(faq)
            if answer:
                return _faq_match_result(faq, faq.document, answer)

    try:
        embeddings = EmbeddingsFactory.create()
        query_embedding = embeddings.embed_query(query)
    except Exception as exc:
        logger.warning("FAQ embedding lookup failed: %s", exc)
        return None

    best_score = 0.0
    best_match: Optional[FaqMatchResult] = None

    for faq in faqs:
        answer = get_effective_faq_answer(faq)
        if not answer:
            continue
        try:
            faq_embedding = embeddings.embed_query(faq.question)
            score = _cosine_similarity(query_embedding, faq_embedding)
        except Exception:
            continue
        if score > best_score:
            best_score = score
            best_match = _faq_match_result(faq, faq.document, answer)

    if best_score >= FAQ_MATCH_THRESHOLD and best_match:
        return best_match

    return None
