import json
import base64
import re
from typing import List, AsyncGenerator, Optional
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
from app.services.embedding.embedding_factory import EmbeddingsFactory
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


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip().lower()


def _extract_assistant_text(content: str) -> str:
    if not content:
        return ""
    if "__LLM_RESPONSE__" in content:
        return content.split("__LLM_RESPONSE__", 1)[1].strip()
    return content.strip()


def _get_feedback_answer(
    db: Session, query: str, knowledge_base_ids: List[int], user_id: int
) -> Optional[str]:
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
            Message.feedback_type.in_(["up", "down"]),
            chat_knowledge_bases.c.knowledge_base_id.in_(knowledge_base_ids),
        )
        .order_by(desc(Message.updated_at))
        .all()
    )

    for candidate in candidates:
        if _normalize_text(candidate.feedback_query or "") != normalized_query:
            continue

        if candidate.feedback_type == "up":
            preferred_answer = _extract_assistant_text(candidate.content)
        else:
            preferred_answer = (candidate.corrected_answer or "").strip()
        if preferred_answer:
            return preferred_answer

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

        preferred_answer = _get_feedback_answer(
            db=db,
            query=query,
            knowledge_base_ids=knowledge_base_ids,
            user_id=user_id,
        )
        if preferred_answer:
            escaped_answer = _escape_stream_text(preferred_answer)
            yield f'0:"{escaped_answer}"\n'
            yield _finish_stream()
            bot_message.content = preferred_answer
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

        retriever = vector_stores[0].as_retriever()

        llm = LLMFactory.create()

        contextualize_q_system_prompt = (
            "Given a chat history and the latest user question "
            "which might reference context in the chat history, "
            "formulate a standalone question which can be understood "
            "without the chat history. Do NOT answer the question, just "
            "reformulate it if needed and otherwise return it as is."
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
            "You are given a user question, and please write clean, concise and accurate answer to the question. "
            "You will be given a set of related contexts to the question, which are numbered sequentially starting from 1. "
            "Each context has an implicit reference number based on its position in the array (first context is 1, second is 2, etc.). "
            "Please use these contexts and cite them using the format [citation:x] at the end of each sentence where applicable. "
            "Your answer must be correct, accurate and written by an expert using an unbiased and professional tone. "
            "Please limit to 1024 tokens. Do not give any information that is not related to the question, and do not repeat. "
            "Say 'information is missing on' followed by the related topic, if the given context do not provide sufficient information. "
            "If a sentence draws from multiple contexts, please list all applicable citations, like [citation:1][citation:2]. "
            "Other than code and specific names and citations, your answer must be written in the same language as the question. "
            "Be concise.\n\nContext: {context}\n\n"
            "Remember: Cite contexts by their position number (1 for first context, 2 for second, etc.) and don't blindly "
            "repeat the contexts verbatim."
        )
        qa_prompt = ChatPromptTemplate.from_messages([
            ("system", qa_system_prompt),
            MessagesPlaceholder("chat_history"),
            ("human", "{input}"),
        ])

        document_prompt = PromptTemplate.from_template("\n\n- {page_content}\n\n")

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
