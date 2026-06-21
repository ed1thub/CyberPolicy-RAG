# CyberPolicy-RAG

Secure AI assistant for cybersecurity policy Q&A using Retrieval-Augmented Generation (RAG).

Answers questions from cybersecurity policy documents while enforcing authentication, role-based access control, metadata-filtered retrieval, prompt-injection protection, source citations, output guarding, and audit logging.

## Features

- JWT authentication with password hashing
- Role-based access control (user / security_analyst / admin)
- Metadata-filtered vector retrieval — restricted chunks never reach the LLM
- Prompt injection guard
- Output guard
- Source citations for every answer
- Audit logging for every chat request
- Mock LLM by default — no paid API required

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | FastAPI, SQLAlchemy, SQLite |
| Vector store | ChromaDB |
| Embeddings | sentence-transformers (all-MiniLM-L6-v2) |
| Frontend | Streamlit |
| Auth | JWT, passlib bcrypt |

## Setup

### Prerequisites

- Python 3.11+
- Ubuntu / WSL / macOS

### 1. Clone the repository

```bash
git clone <repo-url>
cd cyberpolicy-rag
```

### 2. Create virtual environment

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
```

### 3. Install backend dependencies

```bash
pip install -r backend/requirements.txt
```

> Note: `sentence-transformers` and `chromadb` may take a few minutes to install.

### 4. Install frontend dependencies

```bash
pip install -r frontend/requirements.txt
```

### 5. Configure environment

```bash
cp .env.example .env
```

Edit `.env` and set a strong `SECRET_KEY`.

### 6. Run the backend

```bash
uvicorn backend.app.main:app --reload
```

Backend available at: http://localhost:8000

API docs at: http://localhost:8000/docs

### 7. Run the frontend

```bash
streamlit run frontend/streamlit_app.py
```

Frontend available at: http://localhost:8501

## Demo Users

| Username | Password | Role |
|---|---|---|
| student1 | password123 | user |
| analyst1 | password123 | security_analyst |
| admin1 | password123 | admin |

## Document Access by Role

| Role | Public | Internal | Confidential | Restricted |
|---|---|---|---|---|
| user | Yes | Yes | No | No |
| security_analyst | Yes | Yes | Yes | No |
| admin | Yes | Yes | Yes | Yes |

## Running Tests

```bash
pytest backend/tests
```

## Code Quality

```bash
ruff check backend
bandit -r backend/app
```

## Project Structure

```
backend/
  app/
    main.py          # FastAPI entry point
    config.py        # Environment settings
    database.py      # SQLAlchemy setup (T02)
    models.py        # DB models (T02)
    schemas.py       # Pydantic schemas (T09)
    auth/            # JWT auth (T03)
    documents/       # Document loader and chunker (T05, T13)
    rag/             # Embeddings, vector store, RAG service (T06, T08)
    security/        # Access control, prompt guard, output guard (T07, T10, T14)
    audit/           # Audit logging (T11)
  tests/
data/
  sample_policies/   # Sample Markdown policy documents
  chroma/            # ChromaDB vector store (git-ignored)
  uploaded_policies/ # Admin uploaded files (git-ignored)
frontend/
  streamlit_app.py   # Streamlit UI (T12)
  api_client.py      # HTTP client for backend (T12)
```

## Security Design

Access control is enforced by deterministic backend code before vector retrieval. The LLM never receives chunks the user is not authorised to read.

```
User question
→ Authenticate user
→ Identify role
→ Run prompt guard
→ Determine allowed sensitivity levels
→ Retrieve only authorised chunks from ChromaDB
→ Send only authorised context to LLM
→ Run output guard
→ Return answer with citations
→ Write audit log
```
