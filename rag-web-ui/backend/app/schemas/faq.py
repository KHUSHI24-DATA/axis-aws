from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class DocumentContentResponse(BaseModel):
    id: int
    document_id: int
    raw_text: str
    content_length: Optional[int] = None
    extracted_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class FAQResponse(BaseModel):
    id: int
    document_id: int
    question: str
    answer: str
    is_verified: bool = False
    feedback_status: str = "pending"
    corrected_answer: Optional[str] = None
    is_auto_generated: bool = True
    confidence_score: Optional[float] = None
    created_at: datetime
    updated_at: datetime
    created_by: Optional[int] = None

    class Config:
        from_attributes = True


class FAQCreate(BaseModel):
    question: str = Field(..., min_length=5)
    answer: str = Field(..., min_length=10)


class FAQUpdate(BaseModel):
    question: Optional[str] = None
    answer: Optional[str] = None
    feedback_status: Optional[str] = None


class FAQFeedbackRequest(BaseModel):
    feedback_type: str = Field(..., pattern="^(correct|incorrect)$")
    corrected_answer: Optional[str] = None
    notes: Optional[str] = None


class FAQStatsResponse(BaseModel):
    total_faqs: int
    correct_faqs: int
    incorrect_faqs: int
    pending_faqs: int
    average_confidence: float = 0.0
