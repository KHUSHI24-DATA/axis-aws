"""Text splitting utilities with optional semantic-aware chunking."""

import logging
import re
from typing import List

from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_core.documents import Document as LangchainDocument

from app.core.config import settings

logger = logging.getLogger(__name__)

_SENTENCE_PATTERN = re.compile(r"(?<=[.!?])\s+")


class SemanticParagraphSplitter:
    """Split text at paragraph and sentence boundaries while respecting size limits."""

    def __init__(self, chunk_size: int, chunk_overlap: int) -> None:
        self.chunk_size = max(chunk_size, 200)
        self.chunk_overlap = min(chunk_overlap, chunk_size // 2)

    def split_documents(
        self, documents: List[LangchainDocument]
    ) -> List[LangchainDocument]:
        chunks: List[LangchainDocument] = []
        for doc in documents:
            for text in self._split_text(doc.page_content):
                chunks.append(
                    LangchainDocument(page_content=text, metadata=dict(doc.metadata))
                )
        return chunks

    def _split_text(self, text: str) -> List[str]:
        paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
        if not paragraphs:
            return []

        raw_chunks: List[str] = []
        current = ""

        for paragraph in paragraphs:
            if len(paragraph) > self.chunk_size:
                if current:
                    raw_chunks.append(current.strip())
                    current = ""
                raw_chunks.extend(self._split_paragraph(paragraph))
                continue

            candidate = f"{current}\n\n{paragraph}".strip() if current else paragraph
            if len(candidate) <= self.chunk_size:
                current = candidate
            else:
                if current:
                    raw_chunks.append(current.strip())
                current = paragraph

        if current:
            raw_chunks.append(current.strip())

        return self._apply_overlap(raw_chunks)

    def _split_paragraph(self, paragraph: str) -> List[str]:
        sentences = _SENTENCE_PATTERN.split(paragraph)
        chunks: List[str] = []
        current = ""

        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue
            candidate = f"{current} {sentence}".strip() if current else sentence
            if len(candidate) <= self.chunk_size:
                current = candidate
            else:
                if current:
                    chunks.append(current)
                if len(sentence) > self.chunk_size:
                    fallback = RecursiveCharacterTextSplitter(
                        chunk_size=self.chunk_size,
                        chunk_overlap=0,
                    )
                    chunks.extend(fallback.split_text(sentence))
                    current = ""
                else:
                    current = sentence

        if current:
            chunks.append(current)
        return chunks

    def _apply_overlap(self, chunks: List[str]) -> List[str]:
        if self.chunk_overlap <= 0 or len(chunks) <= 1:
            return chunks

        overlapped: List[str] = [chunks[0]]
        for chunk in chunks[1:]:
            prev = overlapped[-1]
            overlap_text = prev[-self.chunk_overlap :]
            overlapped.append(f"{overlap_text}\n{chunk}".strip())
        return overlapped


def _create_embedding_semantic_splitter(chunk_size: int, chunk_overlap: int):
    """Embedding-based semantic chunking via LangChain SemanticChunker."""
    from langchain_experimental.text_splitter import SemanticChunker

    from app.services.embedding.embedding_factory import EmbeddingsFactory

    embeddings = EmbeddingsFactory.create()
    chunker = SemanticChunker(
        embeddings,
        breakpoint_threshold_type="percentile",
        breakpoint_threshold_amount=95,
    )
    paragraph_fallback = SemanticParagraphSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
    )

    class _EmbeddingSemanticSplitter:
        def split_documents(
            self, documents: List[LangchainDocument]
        ) -> List[LangchainDocument]:
            chunks: List[LangchainDocument] = []
            for doc in documents:
                try:
                    doc_chunks = chunker.split_documents([doc])
                    if doc_chunks:
                        chunks.extend(doc_chunks)
                        continue
                except Exception as exc:
                    logger.warning(
                        "Embedding semantic split failed for document, using paragraph fallback: %s",
                        exc,
                    )
                chunks.extend(paragraph_fallback.split_documents([doc]))
            return chunks

    return _EmbeddingSemanticSplitter()


def get_text_splitter(
    chunk_size: int | None = None,
    chunk_overlap: int | None = None,
    use_semantic: bool | None = None,
):
    """Return the configured text splitter, with fallback to recursive splitting."""
    chunk_size = chunk_size or settings.CHUNK_SIZE
    chunk_overlap = chunk_overlap or settings.CHUNK_OVERLAP
    use_semantic = (
        use_semantic if use_semantic is not None else settings.USE_SEMANTIC_CHUNKING
    )

    if use_semantic:
        try:
            return _create_embedding_semantic_splitter(chunk_size, chunk_overlap)
        except Exception as exc:
            logger.warning(
                "Embedding semantic splitter unavailable, using paragraph splitter: %s",
                exc,
            )
            try:
                return SemanticParagraphSplitter(
                    chunk_size=chunk_size,
                    chunk_overlap=chunk_overlap,
                )
            except Exception as inner_exc:
                logger.warning(
                    "Semantic splitter unavailable, falling back to recursive: %s",
                    inner_exc,
                )

    return RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
    )
