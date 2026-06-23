"""add document content and faq tables

Revision ID: h1b2c3d4e5f6
Revises: g0a1b2c3d4e6
Create Date: 2026-06-23 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "h1b2c3d4e5f6"
down_revision: Union[str, None] = "g0a1b2c3d4e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create document_contents table
    op.create_table(
        "document_contents",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("document_id", sa.Integer(), nullable=False),
        sa.Column("raw_text", sa.Text(), nullable=False),
        sa.Column("content_length", sa.Integer(), nullable=True),
        sa.Column("extracted_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_document_contents_document_id", "document_contents", ["document_id"])

    # Create document_faqs table
    op.create_table(
        "document_faqs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("document_id", sa.Integer(), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("answer", sa.Text(), nullable=False),
        sa.Column("is_verified", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("feedback_status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("corrected_answer", sa.Text(), nullable=True),
        sa.Column("is_auto_generated", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("confidence_score", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_document_faqs_document_id", "document_faqs", ["document_id"])
    op.create_index("ix_document_faqs_feedback_status", "document_faqs", ["feedback_status"])

    # Create faq_feedbacks table
    op.create_table(
        "faq_feedbacks",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("faq_id", sa.Integer(), nullable=False),
        sa.Column("feedback_type", sa.String(length=20), nullable=False),
        sa.Column("corrected_answer", sa.Text(), nullable=True),
        sa.Column("reviewer_notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("created_by", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["faq_id"], ["document_faqs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_faq_feedbacks_faq_id", "faq_feedbacks", ["faq_id"])


def downgrade() -> None:
    op.drop_index("ix_faq_feedbacks_faq_id", table_name="faq_feedbacks")
    op.drop_table("faq_feedbacks")

    op.drop_index("ix_document_faqs_feedback_status", table_name="document_faqs")
    op.drop_index("ix_document_faqs_document_id", table_name="document_faqs")
    op.drop_table("document_faqs")

    op.drop_index("ix_document_contents_document_id", table_name="document_contents")
    op.drop_table("document_contents")
