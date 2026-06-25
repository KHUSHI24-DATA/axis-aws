"""Text sanitization for PostgreSQL and vector store storage."""

import logging
import re
from typing import Any, Dict, List

from langchain_core.documents import Document as LangchainDocument

logger = logging.getLogger(__name__)

_NUL = "\x00"
_CONTROL_CHAR_PATTERN = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def sanitize_text(text: str | None) -> str:
    """
    Remove characters that break PostgreSQL text/json storage.

    PDF and Office extractors often emit NUL (0x00) bytes that PostgreSQL rejects.
    """
    if not text:
        return ""

    cleaned = text.replace(_NUL, "")
    cleaned = _CONTROL_CHAR_PATTERN.sub("", cleaned)
    return cleaned


def sanitize_metadata(metadata: Dict[str, Any] | None) -> Dict[str, Any]:
    """Recursively sanitize string values in document metadata."""
    if not metadata:
        return {}

    result: Dict[str, Any] = {}
    for key, value in metadata.items():
        safe_key = sanitize_text(str(key)) if isinstance(key, str) else key
        result[safe_key] = _sanitize_value(value)
    return result


def _sanitize_value(value: Any) -> Any:
    if isinstance(value, str):
        return sanitize_text(value)
    if isinstance(value, dict):
        return sanitize_metadata(value)
    if isinstance(value, list):
        return [_sanitize_value(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_sanitize_value(item) for item in value)
    return value


def sanitize_documents(
    documents: List[LangchainDocument],
    *,
    skip_empty: bool = True,
) -> List[LangchainDocument]:
    """Sanitize page content and metadata for LangChain documents."""
    sanitized: List[LangchainDocument] = []
    removed_nul_count = 0

    for doc in documents:
        original = doc.page_content or ""
        if _NUL in original:
            removed_nul_count += original.count(_NUL)

        content = sanitize_text(original)
        if skip_empty and not content.strip():
            logger.warning("Skipping empty document page after text sanitization")
            continue

        sanitized.append(
            LangchainDocument(
                page_content=content,
                metadata=sanitize_metadata(dict(doc.metadata or {})),
            )
        )

    if removed_nul_count:
        logger.info(
            "Sanitized document text: removed %s NUL byte(s)", removed_nul_count
        )

    return sanitized
