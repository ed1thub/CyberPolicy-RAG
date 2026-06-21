# TASKS.md — Token-Efficient Build Tasks for CyberPolicy-RAG

## How to Use This File

Use one task at a time.

Do not paste the full project plan into every coding-agent session. Instead, paste this short instruction:

```text
Read AGENTS.md, PROJECT_SPEC.md, ARCHITECTURE.md, SECURITY_MODEL.md, DATA_MODEL.md, and TASKS.md. Then complete task TXX only. Follow the acceptance criteria exactly. Do not work ahead.
```

Replace `TXX` with the current task ID.

## Agent Workflow

For every task:

1. Inspect existing files first.
2. Implement only the requested task.
3. Add or update tests.
4. Run relevant tests if possible.
5. Return summary, files changed, commands, test results, and notes.
6. Do not start the next task.

## T01 — Project Skeleton

Owner suggestion: Claude Code

Goal:

Create the initial FastAPI/Streamlit project structure.

Files/directories:

```text
backend/app/main.py
backend/app/config.py
backend/requirements.txt
frontend/requirements.txt
README.md
.env.example
.gitignore
```

Acceptance criteria:

- `uvicorn backend.app.main:app --reload` starts.
- `GET /` returns project info.
- `GET /health` returns status ok.
- Requirements files exist.
- README has basic setup instructions.

Commit message:

```text
Initial project skeleton
```

## T02 — Database Models and Seed Users

Owner suggestion: Codex

Goal:

Add SQLite database and seed users.

Files:

```text
backend/app/database.py
backend/app/models.py
backend/tests/test_database.py
```

Acceptance criteria:

- User, Document, and AuditLog models exist.
- Database initialisation works.
- Demo users are created:
  - student1 / password123 / user
  - analyst1 / password123 / security_analyst
  - admin1 / password123 / admin
- Passwords are hashed.
- Tests confirm seed users exist and passwords are not plain text.

Commit message:

```text
Add database models and seed users
```

## T03 — JWT Authentication

Owner suggestion: Codex

Goal:

Add login and current-user authentication.

Files:

```text
backend/app/auth/auth_service.py
backend/app/auth/dependencies.py
backend/app/auth/routes.py
backend/tests/test_auth.py
```

Endpoints:

```text
POST /auth/login
GET /auth/me
```

Acceptance criteria:

- Valid login returns JWT.
- Invalid login is rejected.
- `/auth/me` returns username and role.
- Missing token is rejected.
- Password hash is not returned.

Commit message:

```text
Add JWT authentication
```

## T04 — Sample Cybersecurity Policies

Owner suggestion: Claude Code

Goal:

Create fake sample cybersecurity policy documents.

Files:

```text
data/sample_policies/password_policy.md
data/sample_policies/incident_response_policy.md
data/sample_policies/acceptable_use_policy.md
data/sample_policies/data_classification_policy.md
data/sample_policies/remote_access_policy.md
data/sample_policies/email_security_policy.md
data/sample_policies/backup_policy.md
```

Acceptance criteria:

- Each document is fake and original.
- Each document has Markdown metadata front matter.
- Each document is around 400-800 words.
- Documents have useful headings for retrieval.
- Sensitivity levels match DATA_MODEL.md.

Commit message:

```text
Add sample cybersecurity policies
```

## T05 — Document Loader and Chunker

Owner suggestion: Claude Code

Goal:

Load Markdown/TXT/PDF documents and split into chunks.

Files:

```text
backend/app/documents/loader.py
backend/app/documents/chunker.py
backend/tests/test_document_loader.py
```

Acceptance criteria:

- Markdown front matter is parsed.
- TXT loading works.
- PDF loading uses PyMuPDF.
- Chunks are 500-800 words with 80-120 word overlap.
- Chunk metadata is preserved.
- Tests cover metadata parsing and chunking.

Commit message:

```text
Add document loader and chunker
```

## T06 — Embeddings and ChromaDB

Owner suggestion: Codex

Goal:

Store and search policy chunks in ChromaDB.

Files:

```text
backend/app/rag/embeddings.py
backend/app/rag/vector_store.py
backend/tests/test_vector_store.py
```

Acceptance criteria:

- Uses sentence-transformers `all-MiniLM-L6-v2`.
- Uses persistent Chroma path from config.
- Implements:
  - `add_chunks(chunks)`
  - `search(query, allowed_sensitivity_levels, top_k=5)`
  - `reset_collection()`
- Search filters by sensitivity level.
- Tests prove restricted chunks are not returned when not allowed.

Commit message:

```text
Add vector store and embeddings
```

## T07 — Access Control

Owner suggestion: Codex

Goal:

Implement role-to-sensitivity mapping.

Files:

```text
backend/app/security/access_control.py
backend/tests/test_access_control.py
```

Acceptance criteria:

- `user` gets public/internal.
- `security_analyst` gets public/internal/confidential.
- `admin` gets all levels.
- Unknown role gets no access.
- Unknown sensitivity is denied.
- Tests cover all roles.

Commit message:

```text
Add role based access control
```

## T08 — Basic RAG Service

Owner suggestion: Claude Code

Goal:

Create the basic RAG service with mock LLM and citations.

Files:

```text
backend/app/rag/llm_adapter.py
backend/app/rag/retriever.py
backend/app/rag/rag_service.py
backend/tests/test_rag.py
```

Acceptance criteria:

- RAG service receives question and role.
- Uses access control to get allowed sensitivity levels.
- Retrieves only authorised chunks.
- Mock LLM answers from retrieved context.
- No source returns standard refusal.
- Sources include document title, filename, section, page.
- Tests cover user/admin access differences.

Commit message:

```text
Add basic RAG service with citations
```

## T09 — Authenticated Chat Endpoint

Owner suggestion: Codex

Goal:

Expose RAG through FastAPI.

Files:

```text
backend/app/schemas.py
backend/app/chat/routes.py
backend/tests/test_chat.py
```

Endpoint:

```text
POST /chat/query
```

Acceptance criteria:

- Requires JWT.
- Validates question is not empty.
- Enforces max length 1000 characters.
- Passes question and role to RAG service.
- Returns structured answer, sources, risk flags, confidence.
- Tests cover auth and validation.

Commit message:

```text
Add authenticated chat endpoint
```

## T10 — Prompt Guard

Owner suggestion: Claude Code

Goal:

Block obvious prompt-injection attempts before retrieval.

Files:

```text
backend/app/security/prompt_guard.py
backend/tests/test_prompt_guard.py
```

Acceptance criteria:

- Detects suspicious phrases listed in SECURITY_MODEL.md.
- Returns allowed boolean and risk flags.
- Integrated into `/chat/query`.
- Blocked prompt does not call retrieval.
- Blocked response uses standard blocked response shape.
- Tests cover normal, injection, and privilege escalation prompts.

Commit message:

```text
Add prompt injection guard
```

## T11 — Audit Logging

Owner suggestion: Codex

Goal:

Log all chat requests and expose logs to analyst/admin.

Files:

```text
backend/app/audit/audit_service.py
backend/app/audit/routes.py
backend/tests/test_audit.py
```

Endpoint:

```text
GET /audit/logs
```

Acceptance criteria:

- Successful chat creates audit log.
- Blocked prompt creates audit log.
- Admin can view logs.
- Security analyst can view logs.
- Normal user cannot view logs.
- Logs include user, role, question, answer_status, documents_used, risk_flags.

Commit message:

```text
Add audit logging
```

## T12 — Streamlit Frontend

Owner suggestion: Claude Code

Goal:

Build basic frontend.

Files:

```text
frontend/api_client.py
frontend/streamlit_app.py
```

Pages:

- Login
- Chat
- Audit Logs
- Admin Upload placeholder

Acceptance criteria:

- User can log in.
- JWT stored in session state.
- User can ask questions.
- Answer, sources, risk flags, and confidence display clearly.
- Audit logs page visible only to analyst/admin.
- Admin upload placeholder visible only to admin.

Commit message:

```text
Add Streamlit frontend
```

## T13 — Admin Document Upload

Owner suggestion: Claude Code

Goal:

Allow admins to upload new documents.

Files:

```text
backend/app/documents/routes.py
backend/app/documents/service.py
frontend/streamlit_app.py
backend/tests/test_document_upload.py
```

Endpoint:

```text
POST /documents/upload
```

Acceptance criteria:

- Admin only.
- Supports `.md`, `.txt`, `.pdf`.
- Rejects files larger than 5MB.
- Rejects unsupported file types.
- Rejects unknown sensitivity levels.
- Saves uploaded file.
- Creates Document record.
- Chunks and indexes uploaded document.
- Uploaded document becomes searchable.

Commit message:

```text
Add admin document upload
```

## T14 — Output Guard

Owner suggestion: Codex

Goal:

Block unsafe generated output.

Files:

```text
backend/app/security/output_guard.py
backend/tests/test_output_guard.py
```

Acceptance criteria:

- Blocks API-key-like strings.
- Blocks password-looking lines.
- Blocks system prompt leakage.
- Integrated after LLM generation.
- Adds `unsafe_output_blocked` risk flag.
- Tests cover normal and unsafe outputs.

Commit message:

```text
Add output guard
```

## T15 — Docker Setup

Owner suggestion: Codex

Goal:

Run project through Docker Compose.

Files:

```text
backend/Dockerfile
frontend/Dockerfile
docker-compose.yml
```

Acceptance criteria:

- `docker compose up --build` starts backend and frontend.
- Backend available at localhost:8000.
- Frontend available at localhost:8501.
- Data directory mounted as volume.

Commit message:

```text
Add Docker setup
```

## T16 — GitHub Actions Security Checks

Owner suggestion: Codex

Goal:

Automate tests and security checks.

Files:

```text
.github/workflows/security-checks.yml
```

Acceptance criteria:

- Runs on push and pull_request.
- Installs backend requirements.
- Runs pytest.
- Runs ruff.
- Runs bandit.
- Runs pip-audit with continue-on-error if needed.

Commit message:

```text
Add GitHub Actions security checks
```

## T17 — Documentation and Portfolio Polish

Owner suggestion: Claude Code

Goal:

Make repo recruiter-ready.

Files:

```text
README.md
docs/architecture.md
docs/threat_model.md
docs/security_controls.md
docs/test_cases.md
docs/demo_script.md
```

Acceptance criteria:

- README includes overview, features, setup, demo users, screenshots section, and future improvements.
- Architecture doc includes Mermaid diagram.
- Threat model includes risks and mitigations.
- Security controls doc explains auth, RBAC, prompt guard, output guard, audit logs.
- Test cases doc includes a table.
- Demo script explains a 3-5 minute walkthrough.

Commit message:

```text
Add professional documentation
```
