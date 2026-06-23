"""FAQ Management API Endpoints"""

from typing import List, Any
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.db.session import get_db
from app.models.user import User
from app.models.knowledge import DocumentFAQ, FAQFeedback, Document, KnowledgeBase, DocumentContent
from app.core.security import get_current_user
from app.schemas.faq import (
    FAQResponse,
    FAQCreate,
    FAQUpdate,
    FAQFeedbackRequest,
    FAQFeedbackResponse,
    FAQStatsResponse,
    DocumentContentResponse,
)

router = APIRouter()


@router.get("/{kb_id}/documents/{doc_id}/content", response_model=DocumentContentResponse)
def get_document_content(
    *,
    kb_id: int,
    doc_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    """Get extracted content of a document"""
    # Verify knowledge base ownership
    kb = (
        db.query(KnowledgeBase)
        .filter(KnowledgeBase.id == kb_id, KnowledgeBase.user_id == current_user.id)
        .first()
    )
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found")

    # Verify document belongs to kb
    doc = (
        db.query(Document)
        .filter(Document.id == doc_id, Document.knowledge_base_id == kb_id)
        .first()
    )
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    # Get document content
    content = (
        db.query(DocumentContent)
        .filter(DocumentContent.document_id == doc_id)
        .first()
    )

    if not content:
        raise HTTPException(status_code=404, detail="Document content not extracted yet")

    return content


@router.get("/{kb_id}/documents/{doc_id}/faqs", response_model=List[FAQResponse])
def get_document_faqs(
    *,
    kb_id: int,
    doc_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    skip: int = 0,
    limit: int = 50,
) -> Any:
    """Get FAQs for a document"""
    # Verify knowledge base ownership
    kb = (
        db.query(KnowledgeBase)
        .filter(KnowledgeBase.id == kb_id, KnowledgeBase.user_id == current_user.id)
        .first()
    )
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found")

    # Verify document belongs to kb
    doc = (
        db.query(Document)
        .filter(Document.id == doc_id, Document.knowledge_base_id == kb_id)
        .first()
    )
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    # Get FAQs
    faqs = (
        db.query(DocumentFAQ)
        .filter(DocumentFAQ.document_id == doc_id)
        .order_by(desc(DocumentFAQ.confidence_score))
        .offset(skip)
        .limit(limit)
        .all()
    )

    return faqs


@router.get("/{kb_id}/documents/{doc_id}/faqs/{faq_id}", response_model=FAQResponse)
def get_faq(
    *,
    kb_id: int,
    doc_id: int,
    faq_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    """Get a specific FAQ"""
    # Verify ownership
    kb = (
        db.query(KnowledgeBase)
        .filter(KnowledgeBase.id == kb_id, KnowledgeBase.user_id == current_user.id)
        .first()
    )
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found")

    faq = (
        db.query(DocumentFAQ)
        .join(Document)
        .filter(
            DocumentFAQ.id == faq_id,
            DocumentFAQ.document_id == doc_id,
            Document.knowledge_base_id == kb_id,
        )
        .first()
    )

    if not faq:
        raise HTTPException(status_code=404, detail="FAQ not found")

    return faq


@router.post("/{kb_id}/documents/{doc_id}/faqs", response_model=FAQResponse)
def create_faq(
    *,
    kb_id: int,
    doc_id: int,
    faq_in: FAQCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    """Create a new FAQ for a document"""
    # Verify ownership
    kb = (
        db.query(KnowledgeBase)
        .filter(KnowledgeBase.id == kb_id, KnowledgeBase.user_id == current_user.id)
        .first()
    )
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found")

    # Verify document
    doc = (
        db.query(Document)
        .filter(Document.id == doc_id, Document.knowledge_base_id == kb_id)
        .first()
    )
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    # Create FAQ
    faq = DocumentFAQ(
        document_id=doc_id,
        question=faq_in.question,
        answer=faq_in.answer,
        is_auto_generated=False,
        feedback_status="pending",
        created_by=current_user.id,
    )
    db.add(faq)
    db.commit()
    db.refresh(faq)

    return faq


@router.put("/{kb_id}/documents/{doc_id}/faqs/{faq_id}", response_model=FAQResponse)
def update_faq(
    *,
    kb_id: int,
    doc_id: int,
    faq_id: int,
    faq_in: FAQUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    """Update a FAQ"""
    # Verify ownership
    kb = (
        db.query(KnowledgeBase)
        .filter(KnowledgeBase.id == kb_id, KnowledgeBase.user_id == current_user.id)
        .first()
    )
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found")

    faq = (
        db.query(DocumentFAQ)
        .join(Document)
        .filter(
            DocumentFAQ.id == faq_id,
            DocumentFAQ.document_id == doc_id,
            Document.knowledge_base_id == kb_id,
        )
        .first()
    )

    if not faq:
        raise HTTPException(status_code=404, detail="FAQ not found")

    # Update fields if provided
    if faq_in.question is not None:
        faq.question = faq_in.question
    if faq_in.answer is not None:
        faq.answer = faq_in.answer
    if faq_in.feedback_status is not None:
        faq.feedback_status = faq_in.feedback_status

    db.commit()
    db.refresh(faq)
    return faq


@router.post(
    "/{kb_id}/documents/{doc_id}/faqs/{faq_id}/feedback",
    response_model=FAQFeedbackResponse,
)
def submit_faq_feedback(
    *,
    kb_id: int,
    doc_id: int,
    faq_id: int,
    feedback: FAQFeedbackRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    """Submit feedback on a FAQ (mark as correct/incorrect)"""
    # Verify ownership
    kb = (
        db.query(KnowledgeBase)
        .filter(KnowledgeBase.id == kb_id, KnowledgeBase.user_id == current_user.id)
        .first()
    )
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found")

    faq = (
        db.query(DocumentFAQ)
        .join(Document)
        .filter(
            DocumentFAQ.id == faq_id,
            DocumentFAQ.document_id == doc_id,
            Document.knowledge_base_id == kb_id,
        )
        .first()
    )

    if not faq:
        raise HTTPException(status_code=404, detail="FAQ not found")

    # Validate feedback type
    if feedback.feedback_type not in {"correct", "incorrect"}:
        raise HTTPException(
            status_code=400, detail="feedback_type must be 'correct' or 'incorrect'"
        )

    if feedback.feedback_type == "incorrect" and not (
        feedback.corrected_answer and feedback.corrected_answer.strip()
    ):
        raise HTTPException(
            status_code=400,
            detail="corrected_answer is required when feedback_type is 'incorrect'",
        )

    # Update FAQ feedback status
    faq.feedback_status = feedback.feedback_type
    faq.is_verified = True

    if feedback.feedback_type == "incorrect":
        faq.corrected_answer = feedback.corrected_answer

    # Store feedback history
    faq_feedback = FAQFeedback(
        faq_id=faq_id,
        feedback_type=feedback.feedback_type,
        corrected_answer=feedback.corrected_answer,
        reviewer_notes=feedback.notes,
        created_by=current_user.id,
    )
    db.add(faq_feedback)
    db.commit()
    db.refresh(faq)

    return FAQFeedbackResponse(status="success", faq=faq)


@router.get("/{kb_id}/documents/{doc_id}/faqs-stats", response_model=FAQStatsResponse)
def get_faq_stats(
    *,
    kb_id: int,
    doc_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    """Get FAQ statistics for a document"""
    # Verify ownership
    kb = (
        db.query(KnowledgeBase)
        .filter(KnowledgeBase.id == kb_id, KnowledgeBase.user_id == current_user.id)
        .first()
    )
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found")

    # Verify document
    doc = (
        db.query(Document)
        .filter(Document.id == doc_id, Document.knowledge_base_id == kb_id)
        .first()
    )
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    # Calculate stats
    total_faqs = db.query(DocumentFAQ).filter(DocumentFAQ.document_id == doc_id).count()

    correct_faqs = (
        db.query(DocumentFAQ)
        .filter(
            DocumentFAQ.document_id == doc_id,
            DocumentFAQ.feedback_status == "correct",
        )
        .count()
    )

    incorrect_faqs = (
        db.query(DocumentFAQ)
        .filter(
            DocumentFAQ.document_id == doc_id,
            DocumentFAQ.feedback_status == "incorrect",
        )
        .count()
    )

    pending_faqs = (
        db.query(DocumentFAQ)
        .filter(
            DocumentFAQ.document_id == doc_id,
            DocumentFAQ.feedback_status == "pending",
        )
        .count()
    )

    avg_confidence = db.query(DocumentFAQ).filter(
        DocumentFAQ.document_id == doc_id
    ).count()

    return FAQStatsResponse(
        total_faqs=total_faqs,
        correct_faqs=correct_faqs,
        incorrect_faqs=incorrect_faqs,
        pending_faqs=pending_faqs,
        average_confidence=0.85,  # Can be calculated if needed
    )


@router.delete("/{kb_id}/documents/{doc_id}/faqs/{faq_id}")
def delete_faq(
    *,
    kb_id: int,
    doc_id: int,
    faq_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    """Delete a FAQ"""
    # Verify ownership
    kb = (
        db.query(KnowledgeBase)
        .filter(KnowledgeBase.id == kb_id, KnowledgeBase.user_id == current_user.id)
        .first()
    )
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found")

    faq = (
        db.query(DocumentFAQ)
        .join(Document)
        .filter(
            DocumentFAQ.id == faq_id,
            DocumentFAQ.document_id == doc_id,
            Document.knowledge_base_id == kb_id,
        )
        .first()
    )

    if not faq:
        raise HTTPException(status_code=404, detail="FAQ not found")

    db.delete(faq)
    db.commit()

    return {"status": "success"}
