# DATA_MODEL.md — CyberPolicy-RAG Data Model

## SQLite Tables

## User

Purpose:

Stores application users and roles.

Fields:

```text
id: integer primary key
username: unique string
password_hash: string
role: string
created_at: datetime
```

Valid roles:

```text
user
security_analyst
admin
```

Seed users:

```text
student1 / password123 / user
analyst1 / password123 / security_analyst
admin1 / password123 / admin
```

Passwords must be hashed.

## Document

Purpose:

Tracks uploaded or sample documents.

Fields:

```text
id: integer primary key
filename: string
title: string
sensitivity_level: string
uploaded_by: integer or nullable
uploaded_at: datetime
```

Valid sensitivity levels:

```text
public
internal
confidential
restricted
```

## AuditLog

Purpose:

Tracks chatbot usage.

Fields:

```text
id: integer primary key
user_id: integer
username: string
role: string
question: text
answer_status: string
documents_used: text or JSON string
risk_flags: text or JSON string
created_at: datetime
```

Answer status examples:

```text
answered
blocked
no_source
error
```

## ChromaDB Collection

Collection name:

```text
policy_chunks
```

Each item contains:

```text
id: unique chunk id
document: chunk text
embedding: vector
metadata: dictionary
```

Required metadata:

```json
{
  "document_title": "Password Policy",
  "filename": "password_policy.md",
  "sensitivity_level": "internal",
  "allowed_roles": "user,security_analyst,admin",
  "section_heading": "Multi-Factor Authentication",
  "page": null,
  "chunk_id": "password_policy_001"
}
```

Note:

Chroma metadata values should be simple scalar values where possible. Store allowed_roles as a comma-separated string if list metadata causes compatibility issues.

## Sample Policy Access Plan

| File | Title | Sensitivity |
|---|---|---|
| acceptable_use_policy.md | Acceptable Use Policy | public |
| password_policy.md | Password Policy | internal |
| email_security_policy.md | Email Security Policy | internal |
| backup_policy.md | Backup Policy | confidential |
| incident_response_policy.md | Incident Response Policy | confidential |
| remote_access_policy.md | Remote Access Policy | confidential |
| data_classification_policy.md | Data Classification Policy | restricted |

## Markdown Metadata Format

Each sample Markdown policy should start with:

```yaml
---
title: Password Policy
sensitivity_level: internal
allowed_roles: user,security_analyst,admin
---
```

## Chat API Models

### ChatRequest

```json
{
  "question": "What does the password policy say about MFA?"
}
```

Validation:

- Required
- Not empty
- Max 1000 characters

### SourceCitation

```json
{
  "document_title": "Password Policy",
  "filename": "password_policy.md",
  "section_heading": "Multi-Factor Authentication",
  "page": null
}
```

### ChatResponse

```json
{
  "answer": "The password policy requires MFA for remote access and administrator accounts.",
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

Confidence values:

```text
high
medium
low
none
blocked
```
