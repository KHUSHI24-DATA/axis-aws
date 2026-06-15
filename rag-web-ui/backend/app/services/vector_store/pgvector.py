import asyncio
from typing import Any, Dict, List

from langchain_core.callbacks import (
    AsyncCallbackManagerForRetrieverRun,
    CallbackManagerForRetrieverRun,
)
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from langchain_core.retrievers import BaseRetriever
from langchain_postgres import PGVector
from pydantic import Field

from app.core.config import pgvector_engine, settings

from .base import BaseVectorStore


class SyncBackedRetriever(BaseRetriever):
    """Retriever that uses sync vector search and supports async via thread offload."""

    vector_store: "PGVectorStore"
    search_kwargs: Dict[str, Any] = Field(default_factory=dict)

    def _get_relevant_documents(
        self,
        query: str,
        *,
        run_manager: CallbackManagerForRetrieverRun,
    ) -> List[Document]:
        k = int(self.search_kwargs.get("k", 4))
        extra_kwargs = {k1: v1 for k1, v1 in self.search_kwargs.items() if k1 != "k"}
        return self.vector_store.similarity_search(query=query, k=k, **extra_kwargs)

    async def _aget_relevant_documents(
        self,
        query: str,
        *,
        run_manager: AsyncCallbackManagerForRetrieverRun,
    ) -> List[Document]:
        k = int(self.search_kwargs.get("k", 4))
        extra_kwargs = {k1: v1 for k1, v1 in self.search_kwargs.items() if k1 != "k"}
        return await asyncio.to_thread(
            self.vector_store.similarity_search,
            query,
            k,
            **extra_kwargs,
        )


class PGVectorStore(BaseVectorStore):
    """PGVector vector store implementation."""

    def __init__(self, collection_name: str, embedding_function: Embeddings, **kwargs: Any):
        """Initialize PGVector vector store."""
        self._collection_name = collection_name
        self._store = PGVector(
            embeddings=embedding_function,
            collection_name=collection_name,
            connection=pgvector_engine(),
            use_jsonb=True,
        )

    def add_documents(self, documents: List[Document]) -> None:
        """Add documents to PGVector."""
        self._store.add_documents(documents)

    def delete(self, ids: List[str]) -> None:
        """Delete documents from PGVector."""
        self._store.delete(ids=ids)

    def as_retriever(self, **kwargs: Any):
        """Return a retriever interface compatible with async chains."""
        search_kwargs = kwargs.get("search_kwargs", {})
        return SyncBackedRetriever(vector_store=self, search_kwargs=search_kwargs)

    def similarity_search(self, query: str, k: int = 4, **kwargs: Any) -> List[Document]:
        """Search for similar documents in PGVector."""
        return self._store.similarity_search(query, k=k, **kwargs)

    def similarity_search_with_score(self, query: str, k: int = 4, **kwargs: Any) -> List[Document]:
        """Search for similar documents in PGVector with score."""
        return self._store.similarity_search_with_score(query, k=k, **kwargs)

    def count_documents(self) -> int:
        """Count documents in PGVector collection when possible."""
        try:
            if hasattr(self._store, "_collection") and self._store._collection is not None:
                return self._store._collection.count()
        except Exception:
            return 0
        return 0

    def delete_collection(self) -> None:
        """Delete the entire PGVector collection."""
        if hasattr(self._store, "delete_collection"):
            self._store.delete_collection()

