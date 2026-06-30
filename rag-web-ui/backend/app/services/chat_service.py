import json
import base64
import re
from typing import Any, Dict, List, AsyncGenerator, Optional
from sqlalchemy.orm import Session
from sqlalchemy import desc
from langchain.chains import create_history_aware_retriever, create_retrieval_chain
from langchain.chains.combine_documents import create_stuff_documents_chain
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder, PromptTemplate
from langchain_core.messages import HumanMessage, AIMessage
from langchain.globals import set_verbose, set_debug
from app.core.config import settings
from app.models.chat import Message, Chat, chat_knowledge_bases
from app.models.knowledge import KnowledgeBase, Document
from app.services.vector_store import VectorStoreFactory
from app.services.vector_store.pgvector import (
    CitationIndexingRetriever,
    MergedVectorStoreRetriever,
)
from app.services.embedding.embedding_factory import EmbeddingsFactory
from app.services.faq_vector_sync import find_faq_corrected_answer
from app.services.llm.llm_factory import LLMFactory

set_verbose(True)
set_debug(True)


def _escape_stream_text(value: str) -> str:
    return (
        value.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", "\\n")
    )


def _serialize_metadata(metadata: dict) -> dict:
    serializable = {}
    for key, value in (metadata or {}).items():
        if isinstance(value, (str, int, float, bool)) or value is None:
            serializable[key] = value
        else:
            serializable[key] = str(value)
    return serializable


def _finish_stream() -> str:
    return 'd:{"finishReason":"stop","usage":{"promptTokens":0,"completionTokens":0}}\n'


def _build_context_prefix(context: List[Dict[str, Any]]) -> str:
    if not context:
        return ""
    escaped_context = json.dumps({"context": context})
    base64_context = base64.b64encode(escaped_context.encode()).decode()
    return base64_context + "__LLM_RESPONSE__"


def _format_answer_with_context(answer: str, context: List[Dict[str, Any]]) -> str:
    prefix = _build_context_prefix(context)
    return prefix + answer if prefix else answer


def _extract_context_from_stored(content: str) -> List[Dict[str, Any]]:
    if "__LLM_RESPONSE__" not in content:
        return []
    base64_part = content.split("__LLM_RESPONSE__", 1)[0].strip()
    if not base64_part:
        return []
    try:
        payload = json.loads(base64.b64decode(base64_part).decode())
        return payload.get("context") or []
    except Exception:
        return []


def _has_citation_markers(text: str) -> bool:
    return bool(re.search(r"\[citation:\s*\d+\]", text or "", re.IGNORECASE))


def _ensure_citation_markers(answer: str, num_contexts: int) -> str:
    """Add inline [citation:N] markers when the model omits them."""
    if not answer or num_contexts <= 0 or _has_citation_markers(answer):
        return answer
    if _is_not_found_answer(answer):
        return _strip_citation_markers(answer)

    paragraphs = [p.strip() for p in re.split(r"\n\n+", answer.strip()) if p.strip()]
    if not paragraphs:
        return f"{answer.rstrip()} [citation:1]"

    cited = []
    for i, paragraph in enumerate(paragraphs):
        cite_num = min(i + 1, num_contexts)
        if _has_citation_markers(paragraph):
            cited.append(paragraph)
        else:
            cited.append(f"{paragraph.rstrip()} [citation:{cite_num}]")
    return "\n\n".join(cited)


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip().lower()


_NOT_FOUND_PHRASES = (
    "i could not find this information in the uploaded documents",
    "i could not find relevant information in the uploaded documents",
)


def _is_not_found_answer(text: str) -> bool:
    normalized = _normalize_text(text)
    return any(phrase in normalized for phrase in _NOT_FOUND_PHRASES)


def _strip_citation_markers(text: str) -> str:
    return re.sub(r"\[citation:\s*\d+\]", "", text or "", flags=re.IGNORECASE).strip()


def _extract_assistant_text(content: str) -> str:
    if not content:
        return ""
    if "__LLM_RESPONSE__" in content:
        return content.split("__LLM_RESPONSE__", 1)[1].strip()
    return content.strip()


def _build_correction_context(
    query: str,
    corrected_answer: str,
    preserved_context: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Attach corrected answer to document source metadata for citations."""
    base_metadata: Dict[str, Any] = {"source_type": "user_corrected"}
    if preserved_context:
        first = preserved_context[0]
        base_metadata = dict(first.get("metadata") or {})
        base_metadata["source_type"] = "user_corrected"

    corrected_chunk = {
        "page_content": f"Question: {query}\nVerified answer: {corrected_answer}",
        "metadata": base_metadata,
    }
    return [corrected_chunk]


def _get_chat_corrected_answer(
    db: Session, query: str, knowledge_base_ids: List[int], user_id: int
) -> Optional[str]:
    """Return chat thumbs-down corrected answer for the same question."""
    normalized_query = _normalize_text(query)
    if not normalized_query:
        return None

    candidates = (
        db.query(Message)
        .join(Chat, Message.chat_id == Chat.id)
        .join(chat_knowledge_bases, chat_knowledge_bases.c.chat_id == Chat.id)
        .filter(
            Chat.user_id == user_id,
            Message.role == "assistant",
            Message.feedback_type == "down",
            Message.corrected_answer.isnot(None),
            chat_knowledge_bases.c.knowledge_base_id.in_(knowledge_base_ids),
        )
        .order_by(desc(Message.updated_at))
        .all()
    )

    for candidate in candidates:
        if _normalize_text(candidate.feedback_query or "") != normalized_query:
            continue
        corrected = (candidate.corrected_answer or "").strip()
        if not corrected:
            continue
        preserved_context = _build_correction_context(
            query=query,
            corrected_answer=corrected,
            preserved_context=_extract_context_from_stored(candidate.content),
        )
        return _format_answer_with_context(corrected, preserved_context)

    return None


def _resolve_corrected_answer(
    db: Session,
    query: str,
    knowledge_base_ids: List[int],
    user_id: int,
) -> Optional[str]:
    """Step 1: user corrections from chat feedback, then FAQ incorrect+corrected."""
    chat_corrected = _get_chat_corrected_answer(
        db=db,
        query=query,
        knowledge_base_ids=knowledge_base_ids,
        user_id=user_id,
    )
    if chat_corrected:
        return chat_corrected

    faq_corrected = find_faq_corrected_answer(
        db=db,
        query=query,
        knowledge_base_ids=knowledge_base_ids,
    )
    if faq_corrected:
        answer = _ensure_citation_markers(
            faq_corrected["answer"], len(faq_corrected["context"])
        )
        return _format_answer_with_context(answer, faq_corrected["context"])

    return None


async def generate_response(
    query: str,
    messages: dict,
    knowledge_base_ids: List[int],
    chat_id: int,
    db: Session,
    user_id: int,
) -> AsyncGenerator[str, None]:
    try:
        user_message = Message(
            content=query,
            role="user",
            chat_id=chat_id,
        )
        db.add(user_message)
        db.commit()

        bot_message = Message(
            content="",
            role="assistant",
            chat_id=chat_id,
        )
        db.add(bot_message)
        db.commit()

        corrected_answer = _resolve_corrected_answer(
            db=db,
            query=query,
            knowledge_base_ids=knowledge_base_ids,
            user_id=user_id,
        )
        if corrected_answer:
            if "__LLM_RESPONSE__" in corrected_answer:
                prefix, answer_text = corrected_answer.split("__LLM_RESPONSE__", 1)
                context_items = _extract_context_from_stored(corrected_answer)
                answer_text = _ensure_citation_markers(
                    answer_text, len(context_items)
                )
                corrected_answer = prefix + "__LLM_RESPONSE__" + answer_text
                yield f'0:"{_escape_stream_text(prefix + "__LLM_RESPONSE__")}"\n'
                yield f'0:"{_escape_stream_text(answer_text)}"\n'
            else:
                yield f'0:"{_escape_stream_text(corrected_answer)}"\n'
            yield _finish_stream()
            bot_message.content = corrected_answer
            db.commit()
            return

        knowledge_bases = (
            db.query(KnowledgeBase)
            .filter(KnowledgeBase.id.in_(knowledge_base_ids))
            .all()
        )

        embeddings = EmbeddingsFactory.create()

        vector_stores = []
        for kb in knowledge_bases:
            documents = db.query(Document).filter(Document.knowledge_base_id == kb.id).all()
            if documents:
                vector_store = VectorStoreFactory.create(
                    store_type=settings.VECTOR_STORE_TYPE,
                    collection_name=f"kb_{kb.id}",
                    embedding_function=embeddings,
                )
                print(f"Collection {f'kb_{kb.id}'} count:", vector_store.count_documents())
                vector_stores.append(vector_store)

        if not vector_stores:
            error_msg = "I don't have any knowledge base to help answer your question."
            yield f'0:"{_escape_stream_text(error_msg)}"\n'
            yield _finish_stream()
            bot_message.content = error_msg
            db.commit()
            return

        top_k = settings.RETRIEVAL_TOP_K
        if len(vector_stores) == 1:
            base_retriever = vector_stores[0].as_retriever(
                search_kwargs={"k": top_k}
            )
        else:
            base_retriever = MergedVectorStoreRetriever(
                stores=vector_stores, k=top_k
            )
        retriever = CitationIndexingRetriever(base_retriever=base_retriever)

        preview_docs = retriever.invoke(query)
        if not preview_docs or not any(
            (doc.page_content or "").strip() for doc in preview_docs
        ):
            error_msg = (
                "I could not find relevant information in the uploaded documents "
                "for your question. Please try rephrasing or upload the document "
                "that contains this topic."
            )
            yield f'0:"{_escape_stream_text(error_msg)}"\n'
            yield _finish_stream()
            bot_message.content = error_msg
            db.commit()
            return

        llm = LLMFactory.create()

        contextualize_q_system_prompt = (
            "Given a chat history and the latest user question "
            "which might reference context in the chat history, "
            "formulate a standalone question which can be understood "
            "without the chat history. Do NOT answer the question, just "
            "reformulate it if needed and otherwise return it as is. "
            "Always write the reformulated question in English."
        )
        contextualize_q_prompt = ChatPromptTemplate.from_messages([
            ("system", contextualize_q_system_prompt),
            MessagesPlaceholder("chat_history"),
            ("human", "{input}"),
        ])

        history_aware_retriever = create_history_aware_retriever(
            llm,
            retriever,
            contextualize_q_prompt,
        )

        qa_system_prompt = (
            "You are a document Q&A assistant. Answer the user's question using ONLY "
            "the information provided in the Context below. The Context comes from "
            "uploaded knowledge-base documents — treat it as your only source of truth.\n\n"
            "Rules:\n"
            "1. Use ONLY facts explicitly stated in the Context. Do NOT use outside "
            "knowledge, training data, guesses, or assumptions.\n"
            "2. Each context chunk is labeled [citation:1], [citation:2], etc. "
            "You MUST cite the matching label immediately after every sentence that "
            "uses that chunk, e.g. ...policy details[citation:2]. Never skip citations.\n"
            "3. If the Context does not contain enough information, respond exactly: "
            "'I could not find this information in the uploaded documents.' "
            "Do NOT add any citation markers for not-found responses.\n"
            "4. Do not repeat the Context verbatim. Write a clear, concise answer (max 1024 tokens).\n"
            "5. If multiple contexts support a sentence, cite all of them, e.g. [citation:1][citation:2].\n"
            "6. Always respond in English.\n\n"
            "Context:\n{context}\n\n"
            "Remember: Answer ONLY from the Context above. Every factual sentence needs "
            "inline [citation:N] markers."
        )
        qa_prompt = ChatPromptTemplate.from_messages([
            ("system", qa_system_prompt),
            MessagesPlaceholder("chat_history"),
            ("human", "{input}"),
        ])

        document_prompt = PromptTemplate.from_template(
            "[citation:{citation_index}]\n{page_content}\n"
        )

        question_answer_chain = create_stuff_documents_chain(
            llm,
            qa_prompt,
            document_variable_name="context",
            document_prompt=document_prompt,
        )

        rag_chain = create_retrieval_chain(
            history_aware_retriever,
            question_answer_chain,
        )

        chat_history = []
        for message in messages.get("messages", []):
            if message["role"] == "user" and message["content"] == query:
                continue
            if message["role"] == "user":
                chat_history.append(HumanMessage(content=message["content"]))
            elif message["role"] == "assistant":
                content = message["content"]
                if "__LLM_RESPONSE__" in content:
                    content = content.split("__LLM_RESPONSE__")[-1]
                chat_history.append(AIMessage(content=content))

        full_response = ""
        serializable_context: List[Dict[str, Any]] = []
        async for chunk in rag_chain.astream({
            "input": query,
            "chat_history": chat_history,
        }):
            if "context" in chunk:
                serializable_context = []
                for context in chunk["context"]:
                    serializable_doc = {
                        "page_content": context.page_content,
                        "metadata": _serialize_metadata(context.metadata),
                    }
                    serializable_context.append(serializable_doc)

                escaped_context = json.dumps({"context": serializable_context})
                base64_context = base64.b64encode(escaped_context.encode()).decode()
                separator = "__LLM_RESPONSE__"
                stream_payload = _escape_stream_text(base64_context + separator)

                yield f'0:"{stream_payload}"\n'
                full_response += base64_context + separator

            if "answer" in chunk:
                answer_chunk = chunk["answer"]
                full_response += answer_chunk
                yield f'0:"{_escape_stream_text(answer_chunk)}"\n'

        if serializable_context and "__LLM_RESPONSE__" in full_response:
            prefix, answer_text = full_response.split("__LLM_RESPONSE__", 1)
            answer_text = _strip_citation_markers(answer_text)
            if _is_not_found_answer(answer_text):
                # No answer in documents — do not attach source chunks or citations.
                full_response = answer_text
            else:
                answer_text = _ensure_citation_markers(
                    answer_text, len(serializable_context)
                )
                full_response = prefix + "__LLM_RESPONSE__" + answer_text

        yield _finish_stream()
        bot_message.content = full_response
        db.commit()

    except Exception as e:
        error_message = f"Error generating response: {str(e)}"
        print(error_message)
        yield f'3:"{_escape_stream_text(error_message)}"\n'
        yield _finish_stream()

        if "bot_message" in locals():
            bot_message.content = error_message
            db.commit()
