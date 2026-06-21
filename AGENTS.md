# AGENTS.md — CyberPolicy-RAG Coding Agent Instructions

## Project Identity

Project name: **CyberPolicy-RAG**

Full title: **CyberPolicy-RAG: Secure AI Assistant for Cybersecurity Policy Q&A**

This is a cybersecurity portfolio project for a Bachelor of Networking / Cybersecurity student. The goal is to build a secure Retrieval-Augmented Generation chatbot that answers questions from cybersecurity policy documents while enforcing authentication, role-based access control, metadata-filtered retrieval, prompt-injection protection, source citations, output guarding, and audit logging.

## Non-Negotiable Rules

1. Build in small, reviewable steps.
2. Do not rewrite unrelated files.
3. Do not remove existing working features unless the current task explicitly requires it.
4. Do not hardcode secrets, API keys, tokens, or passwords.
5. Use environment variables for configuration.
6. Use clean Python with clear function names and type hints where practical.
7. Add or update tests for every security-critical feature.
8. Keep the system runnable in local development without a paid LLM API.
9. Use a mock LLM provider by default.
10. Enforce role-based access control before retrieval.
11. Never send unauthorised document chunks to the LLM.
12. Every chatbot answer must include citations when sources are used.
13. Every chat request must create an audit log.
14. Prompt injection protection is a guardrail, not the only defence.
15. If unsure, choose the simpler maintainable implementation.

## Development Environment

The user is developing on:

- Windows
- Ubuntu WSL
- VS Code
- Python virtual environment
- Git
- Docker optional later

Assume commands are run from the project root inside Ubuntu WSL.

## Preferred Commands

Create virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
```

Run backend:

```bash
uvicorn backend.app.main:app --reload
```

Run frontend:

```bash
streamlit run frontend/streamlit_app.py
```

Run tests:

```bash
pytest backend/tests
```

Run lint:

```bash
ruff check backend
```

Run security scan:

```bash
bandit -r backend/app
```

## Tech Stack

Backend:

- FastAPI
- SQLAlchemy
- SQLite
- Pydantic
- python-jose for JWT
- passlib bcrypt for password hashing

RAG:

- ChromaDB
- sentence-transformers
- all-MiniLM-L6-v2
- PyMuPDF for PDF text extraction
- Markdown/TXT loader
- Mock LLM as default provider
- Optional Ollama/OpenAI-compatible provider later

Frontend:

- Streamlit
- requests
- session_state for JWT

Security:

- JWT authentication
- Role-based access control
- Metadata-filtered retrieval
- Prompt guard
- Output guard
- Audit logging

DevSecOps:

- pytest
- ruff
- bandit
- pip-audit optional
- GitHub Actions
- Docker Compose

## Code Style

- Prefer small modules with single responsibility.
- Prefer simple explicit code over clever abstractions.
- Avoid unnecessary frameworks unless already used.
- Use readable names:
  - `get_allowed_sensitivity_levels`
  - `can_access_document`
  - `create_audit_log`
  - `search_authorised_chunks`
- Keep API responses structured and predictable.
- Avoid global mutable state unless clearly safe.
- Do not add external services that make the project hard to run.

## Security Architecture Rule

Correct RAG security flow:

```text
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

Incorrect flow:

```text
Retrieve all chunks
→ Send all chunks to LLM
→ Tell LLM not to reveal restricted data
```

Never implement the incorrect flow.

## User Roles

```text
user:
- public
- internal

security_analyst:
- public
- internal
- confidential

admin:
- public
- internal
- confidential
- restricted
```

Unknown roles receive no access.

## Sensitivity Levels

Allowed sensitivity levels:

```text
public
internal
confidential
restricted
```

Unknown sensitivity levels must be rejected.

## Demo Users

Seed these users during development:

```text
student1 / password123 / user
analyst1 / password123 / security_analyst
admin1 / password123 / admin
```

Passwords must be hashed. Never store plain-text passwords in the database.

## Standard API Shape

Chat endpoint:

```text
POST /chat/query
```

Request:

```json
{
  "question": "What does the password policy say about MFA?"
}
```

Response:

```json
{
  "answer": "Answer text here.",
  "sources": [
    {
      "document_title": "Password Policy",
      "filename": "password_policy.md",
      "section_heading": "Multi-Factor Authentication",
      "page": null
    }
  ],
  "risk_flags": [],
  "confidence": "high"
}
```

Blocked prompt response:

```json
{
  "answer": "This request cannot be processed because it attempts to bypass system or access-control rules.",
  "sources": [],
  "risk_flags": ["prompt_injection_attempt"],
  "confidence": "blocked"
}
```

No authorised source response:

```json
{
  "answer": "I could not find this information in the authorised policy documents.",
  "sources": [],
  "risk_flags": [],
  "confidence": "none"
}
```

## Required Agent Response Format

After each coding task, respond with:

```text
Summary:
- What changed

Files changed:
- path/to/file.py
- path/to/test.py

How to run:
- command 1
- command 2

Tests:
- What tests were added
- What tests passed or were not run

Notes:
- Any limitations or follow-up items
```

## Do Not Do

- Do not create a giant all-in-one file.
- Do not use real company policies.
- Do not use real secrets.
- Do not add a paid API requirement.
- Do not skip tests for auth, RBAC, prompt guard, output guard, and audit logs.
- Do not make normal users able to access confidential or restricted documents.
- Do not depend on Windows-specific commands.
- Do not add Kubernetes, cloud deployment, OAuth providers, or complex infrastructure unless specifically requested.
