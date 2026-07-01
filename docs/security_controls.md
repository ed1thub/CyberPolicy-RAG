# Security Controls

This document explains each security control implemented in CyberPolicy-RAG, where it lives in the code, and what it does and does not protect against. See [threat_model.md](threat_model.md) for the threats each control addresses, and [architecture.md](architecture.md) for how they fit into the request flow.

## JWT Authentication

**Where:** `backend/app/auth/auth_service.py`, `backend/app/auth/dependencies.py`, `backend/app/auth/routes.py`

`POST /auth/login` verifies a username/password pair against the stored bcrypt hash and, on success, issues a JWT signed with `SECRET_KEY` (HS256, `python-jose`) containing the username and role, expiring after `ACCESS_TOKEN_EXPIRE_MINUTES` (default 60). Every protected route depends on `get_current_user`, which decodes and verifies the token and loads the corresponding `User` row; missing, malformed, or expired tokens are rejected with `401`.

There is no refresh-token flow, no token revocation list, and no rate limiting on the login endpoint. Sessions cannot be invalidated server-side before natural expiry.

## Password Hashing

**Where:** `backend/app/auth/auth_service.py`

Passwords are hashed with bcrypt via passlib before storage; the plain-text password is never persisted or logged. Demo user seeding (`student1`, `analyst1`, `admin1`) also hashes the seed passwords rather than inserting them as plain text — verified by `test_database.py`.

## Role-Based Access Control (RBAC)

**Where:** `backend/app/security/access_control.py`

A fixed, deny-by-default mapping from role to the sensitivity levels that role may access:

| Role | public | internal | confidential | restricted |
|---|---|---|---|---|
| `user` | yes | yes | no | no |
| `security_analyst` | yes | yes | yes | no |
| `admin` | yes | yes | yes | yes |
| unknown role | no | no | no | no |

`get_allowed_sensitivity_levels(role)` returns this set; `can_access_document(role, sensitivity_level)` additionally rejects any `sensitivity_level` value outside the four valid levels, so a document with a malformed or unexpected sensitivity value is denied to everyone rather than defaulting open.

This mapping is also enforced route-by-route for actions that aren't retrieval: `/audit/logs` requires `admin` or `security_analyst`; `/documents/upload`, `/documents/`, and `/documents/{id}` require `admin`.

## Metadata-Filtered Retrieval

**Where:** `backend/app/rag/vector_store.py`, `backend/app/rag/retriever.py`

This is the primary control preventing disclosure, not the prompt or output guard. `VectorStore.search()` and `VectorStore.get_section()` pass `allowed_sensitivity_levels` as a ChromaDB `where` clause on the `sensitivity_level` field, so the vector database itself excludes unauthorised chunks from the result set — they are never fetched, never placed in the LLM's context, and therefore cannot appear in a generated answer. `_authorised_results()` performs a second, defensive re-check on whatever ChromaDB returns, dropping anything outside the allowed set even if it somehow passed the query filter.

**This ordering must not change.** Retrieving all chunks and then filtering, or telling the LLM which chunks it's "allowed" to use, would make disclosure prevention dependent on LLM compliance rather than backend code — this is explicitly the incorrect pattern per `AGENTS.md`.

## Prompt Guard

**Where:** `backend/app/security/prompt_guard.py`

Runs on the raw question, before retrieval is called at all. `check_prompt()` performs a case-insensitive substring match against a static list of known bypass phrases (e.g. "ignore previous instructions", "reveal the system prompt", "bypass access control", "pretend you are admin"). A match short-circuits the request: retrieval never runs, a fixed refusal is returned, and the attempt is still logged to the audit trail with `answer_status="blocked"` and `risk_flags=["prompt_injection_attempt"]`.

**This is a basic, deterministic, first-layer safety net — not a general prompt-injection defence.** It will not catch paraphrased, obfuscated, translated, or novel injection attempts that avoid the listed phrases. It exists to catch the obvious cases cheaply; the metadata-filtered retrieval boundary above is what actually prevents disclosure even if this guard is bypassed entirely.

## Output Guard

**Where:** `backend/app/security/output_guard.py`

Runs on the generated answer, after the LLM adapter produces it and before it's returned to the user. `check_output()` uses regex patterns to detect: common API-key/token shapes (AWS `AKIA...`, Google `AIza...`, GitHub `ghp_...`, OpenAI-style `sk-...`, Slack `xox...`), password-looking key=value assignment lines, system/developer-prompt leakage phrases, and full-document-dump phrasing. A match replaces the answer with a fixed block message, sets `confidence="blocked"`, and adds `unsafe_output_blocked` to the response's risk flags (merged with any existing flags).

**This is also a basic, deterministic, pattern-matching layer**, not a general data-loss-prevention system. It catches known shapes; it will not catch sensitive content that doesn't match one of the compiled patterns.

## Audit Logging

**Where:** `backend/app/audit/audit_service.py`, `backend/app/audit/routes.py`

Every call to `/chat/query` writes an `AuditLog` row — for answered, blocked, and no-source outcomes alike — recording `user_id`, `username`, `role`, `question`, `answer_status`, `documents_used` (filenames of cited sources, empty for blocked/no-source), `risk_flags`, and `created_at`. `GET /audit/logs` returns all logs to `admin` and `security_analyst`; a `user`-role request returns `403`.

Audit logs are stored in the same SQLite database as application data and are not currently write-once/tamper-evident, exportable, or externally shipped to a SIEM — they are a local, queryable trail suitable for demo and review purposes.

## Admin-Only Document Upload

**Where:** `backend/app/documents/routes.py`, `backend/app/documents/service.py`

`POST /documents/upload` requires `current_user.role == "admin"`, checked explicitly before any file processing happens. `validate_upload()` rejects unsupported file extensions (only `.md`, `.txt`, `.pdf` are accepted), files over the configured size limit, and unrecognised `sensitivity_level` values — all before the file is written to disk or handed to the loader/chunker. Successful uploads are chunked, embedded, and indexed into ChromaDB with the supplied `sensitivity_level` and `allowed_roles` metadata, and recorded as a `Document` row. `GET /documents/` and `DELETE /documents/{id}` are also admin-only.

## Docker Local Deployment Considerations

`docker-compose.yml` runs two containers: `backend` (FastAPI, serving the API and the HTML SPA on port 8000) and `frontend` (the Streamlit launcher shim, port 8501). Configuration is passed via environment variables with development-safe defaults (e.g. `SECRET_KEY` defaults to a placeholder — this must be overridden for anything beyond local demo use). `./data` is mounted as a volume so the SQLite database, ChromaDB store, and uploaded files persist across container restarts. There is no TLS termination, reverse proxy, or production hardening configured in the compose file — it is intended for local development and demonstration, not as a production deployment topology.

## GitHub Actions Checks

**Where:** `.github/workflows/security-checks.yml`

Runs on every push and pull request against the repository: installs backend dependencies, then runs `pytest backend/tests`, `ruff check backend`, and `bandit -r backend/app` as blocking steps. `pip-audit -r backend/requirements.txt` is also run but with `continue-on-error: true`, so a dependency vulnerability advisory surfaces in the CI log without failing the build outright.

## Honest Summary

The prompt guard and output guard are intentionally simple, deterministic, rule-based safety layers — not machine-learning classifiers and not a complete prompt-injection defence. The project does **not** claim to fully prevent all prompt-injection attacks. The property that actually holds under adversarial input is narrower and stronger: **the LLM is never given text outside the requesting user's authorised sensitivity levels**, because that filter is applied in the vector-store query itself, not requested of the LLM. This project is a local/demo-oriented portfolio build; it is not represented as production-ready, and the [Future Improvements](../README.md#future-improvements) section lists what would be needed to move toward that (rate limiting, token revocation, a production database, TLS/reverse-proxy configuration, and a more robust prompt-injection evaluation approach, among others).
