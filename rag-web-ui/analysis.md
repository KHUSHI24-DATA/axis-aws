# Tech Stack and Database Analysis

## Overview

This app is a **RAG (Retrieval-Augmented Generation) knowledge-base web application** with a separated frontend and backend architecture.

## Main Tech Stack

### Frontend

- **Next.js 14** (React-based framework)
  - Used to build the web UI with routing, SSR/modern app structure, and production build optimization.
- **React 18**
  - Used for component-driven interactive UI.
- **TypeScript**
  - Used for better type safety and maintainability in frontend code.
- **Tailwind CSS + shadcn/ui + Radix UI**
  - Used for fast, consistent, accessible UI styling and reusable components.
- **Vercel AI SDK (`ai` package)**
  - Used to support AI/chat-oriented frontend interactions and streaming-friendly UX.

### Backend

- **Python 3 + FastAPI + Uvicorn**
  - Used for high-performance async REST APIs and API docs.
- **SQLAlchemy + Alembic**
  - Used for relational data modeling/ORM and schema migrations.
- **LangChain ecosystem**
  - Used to orchestrate retrieval + generation workflows in the RAG pipeline.
- **JWT/OAuth-related libraries (`python-jose`, etc.)**
  - Used for authentication and authorization flows.

### Deployment and Infra

- **Docker + Docker Compose**
  - Used to run and coordinate all services consistently across environments.
- **Nginx**
  - Used as a reverse proxy in front of frontend/backend/minio services.
- **MinIO**
  - Used as object storage for uploaded knowledge-base files/documents.

## Database(s) Used

### 1) Primary relational database: **PostgreSQL (same pgvector instance)**

- Service image: `pgvector/pgvector:pg16` in `docker-compose.yml`
- Backend default connection uses PostgreSQL (`postgresql+psycopg://...`) via SQLAlchemy.
- Purpose:
  - Store structured business/application data (users, metadata, settings, task states, etc.).
  - Support transactional consistency and relational queries.

### 2) Primary vector database (default): **PGVector**

- Service image: `pgvector/pgvector:pg16` in `docker-compose.yml`
- Backend default vector store type is `pgvector`.
- Purpose:
  - Store document embeddings (vectors) for similarity search in PostgreSQL.
  - Enable semantic retrieval in the RAG flow before LLM generation.

### 3) Optional vector databases: **ChromaDB** and **Qdrant** (supported, not default)

- ChromaDB service is included and can be selected by setting `VECTOR_STORE_TYPE=chroma`.
- Qdrant service is present (commented) and can be selected with `VECTOR_STORE_TYPE=qdrant`.
- Backend includes both ChromaDB and Qdrant config/dependency support.
- Purpose:
  - Alternative vector store backend for teams preferring Qdrant features/performance profile.

## Why this combination makes sense

- **Single PostgreSQL + pgvector** simplifies operations:
  - PostgreSQL handles structured transactional app data.
  - Chroma/Qdrant handles vector similarity retrieval.
- **FastAPI + LangChain** gives a practical backend for async APIs and LLM/retrieval orchestration.
- **Next.js + TypeScript** provides a modern, maintainable UI layer for chat and knowledge-base management.
- **MinIO + Dockerized services** simplifies document storage and local deployment reproducibility.
