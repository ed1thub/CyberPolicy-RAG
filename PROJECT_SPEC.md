# PROJECT_SPEC.md — CyberPolicy-RAG Product Specification

## One-Line Summary

CyberPolicy-RAG is a secure AI-powered policy assistant that answers cybersecurity policy questions using Retrieval-Augmented Generation while enforcing authentication, role-based access control, prompt-injection protection, source citations, output guarding, and audit logging.

## Problem Statement

Cybersecurity policies are often stored in long documents that are difficult for staff or students to search quickly. A basic AI chatbot may hallucinate, leak sensitive information, or ignore access restrictions. This project demonstrates a safer RAG design where answers are grounded in authorised policy documents only.

## Target Users

### Standard User

Can ask questions from public and internal documents.

### Security Analyst

Can ask questions from public, internal, and confidential documents. Can view audit logs.

### Admin

Can access all document levels, upload new documents, and view audit logs.

## Core Features

### Authentication

- Users log in with username and password.
- Backend returns JWT access token.
- Protected endpoints require valid JWT.
- Passwords are hashed.

### Role-Based Access Control

Access by role:

```text
user: public, internal
security_analyst: public, internal, confidential
admin: public, internal, confidential, restricted
```

RBAC must be enforced before retrieval from the vector store.

### Document Upload and Ingestion

Supported file types:

```text
.md
.txt
.pdf
```

Each document has:

- title
- filename
- sensitivity_level
- allowed_roles
- uploaded_by
- uploaded_at

Markdown sample documents include metadata front matter:

```yaml
---
title: Password Policy
sensitivity_level: internal
allowed_roles: user,security_analyst,admin
---
```

### RAG Chat

The chat system must:

1. Accept a user question.
2. Validate authentication.
3. Check prompt injection patterns.
4. Determine user's allowed sensitivity levels.
5. Retrieve only authorised chunks.
6. Generate answer using only retrieved context.
7. Return answer with citations.
8. Log the request.

### Citations

Every answer based on retrieved documents must show sources:

- document_title
- filename
- section_heading if available
- page if available

### Prompt Guard

The prompt guard blocks obvious attempts to bypass rules, such as:

- ignore previous instructions
- reveal system prompt
- pretend you are admin
- bypass access control
- show restricted documents
- forget your rules
- disable security
- print hidden instructions
- override developer message
- act as system

This is a basic rule-based guard. The main security control is still backend-enforced RBAC before retrieval.

### Output Guard

The output guard blocks generated responses that appear to contain:

- API key style strings
- password-looking lines
- system prompt leakage
- hidden instruction leakage
- full document dumps

### Audit Logging

Every chat request should log:

- user_id
- username
- role
- question
- answer_status
- documents_used
- risk_flags
- created_at

Audit log access:

- admin: allowed
- security_analyst: allowed
- user: denied

## MVP Scope

The MVP is complete when:

1. Backend runs with FastAPI.
2. SQLite database exists.
3. Demo users exist.
4. Users can log in.
5. Sample Markdown policies are indexed into ChromaDB.
6. Authenticated users can ask questions.
7. Retrieval respects RBAC.
8. Answers include citations.
9. Prompt-injection attempts are blocked.
10. Audit logs are created.
11. Streamlit UI supports login and chat.

## Final Portfolio Scope

The project is portfolio-ready when it also has:

1. Admin document upload.
2. Output guard.
3. Audit logs page.
4. Docker Compose.
5. GitHub Actions security checks.
6. README with screenshots.
7. Architecture documentation.
8. Threat model.
9. Security controls documentation.
10. Demo script.

## Out of Scope for Initial Build

Do not add these unless explicitly requested later:

- Kubernetes
- Production cloud deployment
- Microsoft Entra ID login
- Multi-tenant organisations
- Payment systems
- Real company confidential documents
- Complex frontend frameworks
- Real SIEM integration
- Fine-tuned LLMs
- Advanced ML prompt-injection classifier

## Success Criteria

The project must prove:

- Secure RAG design
- Backend-enforced access control
- Practical AI security thinking
- Clean Python/FastAPI engineering
- Cybersecurity documentation
- Recruiter-friendly GitHub presentation
