# CyberPolicy-RAG — UI Design Reference

## Overview

Single-file HTML/CSS/JS SPA at `frontend/policy_chat_ui.html`.
Served at `GET /` by FastAPI. No build process. No CORS (same-origin API calls).
JWT stored in `localStorage` (`cp_token` key). All API calls use `Authorization: Bearer <jwt>`.

---

## Visual Design System

**Style direction:** Dark luxury — near-black surfaces with precise neutral palette and
single accent colour (blue). Intentional hierarchy through scale contrast and spacing rhythm.

### CSS Tokens (`:root`)

| Token | Value | Purpose |
|---|---|---|
| `--sidebar-w` | 260px (280px ≥1440, 300px ≥1920) | Sidebar width |
| `--bg` | `#0c0c0c` | App background |
| `--sidebar-bg` | `#0a0a0a` | Sidebar background |
| `--main-bg` | `#141414` | Main area background |
| `--surface` | `#1d1d1d` | Cards, bubbles |
| `--surface-hi` | `#252525` | Hover surfaces |
| `--surface-xl` | `#2d2d2d` | Elevated surfaces |
| `--border` | `#2c2c2c` | Primary borders |
| `--border-sub` | `#1a1a1a` | Subtle separators |
| `--text` | `#efefef` | Primary text |
| `--text-sec` | `#848484` | Secondary text |
| `--text-muted` | `#484848` | Muted/disabled text |
| `--blue` | `#1a6bff` | Accent colour |
| `--blue-badge` | `#0d58d9` | Brand icon, role badge |
| `--blue-text` | `#5a9dff` | Links, active items |
| `--amber` | `#d98a00` | Warning states |
| `--red` | `#f44747` | Error/blocked states |
| `--green` | `#3aaa66` | Success states |
| `--purple` | `#9d6bff` | Admin badge accent |
| `--font` | Inter, system-ui | Body font |
| `--mono` | JetBrains Mono | Code, badges, timestamps |

### Sensitivity Level Colours

| Level | Background | Text | Border |
|---|---|---|---|
| public | `--green-muted` | `--green` | `--green-border` |
| internal | `--blue-muted` | `--blue-text` | `--blue-border` |
| confidential | `--amber-muted` | `--amber` | `--amber-border` |
| restricted | `--red-muted` | `--red` | `--red-border` |

Applied via `.sens-badge .sens-{level}` classes. Uppercase monospace label (PUBLIC / INTERNAL / CONFIDENTIAL / RESTRICTED).

---

## Pages and Access Control

| Page | View ID | Visible to |
|---|---|---|
| Login | `#login-overlay` | All (pre-auth) |
| Chat | `#view-chat` | user, security_analyst, admin |
| Audit Logs | `#view-audit` | security_analyst, admin |
| Upload Policy | `#view-upload` | admin only |

Nav items injected by `renderSidebarNav()` based on role. Role-gated nav separator + items only appear for analyst/admin.

---

## Demo Users (seeded at startup)

| Username | Password | Role |
|---|---|---|
| `student1` | `password123` | `user` |
| `analyst1` | `password123` | `security_analyst` |
| `admin1` | `password123` | `admin` |

Shown in login hint block below the sign-in form.

---

## Login Page (`#login-overlay`)

Full-screen overlay with blur backdrop. Centered modal (340px wide).

**Elements:**
- Brand icon + "CyberPolicy-RAG" name
- "Sign in" title + subtitle
- Inline error card (`#login-err`, hidden by default, `.login-err` red style)
- Username field (`#login-user`, autocomplete="username")
- Password field (`#login-pass`, autocomplete="current-password")
- Submit button (`#login-btn`) → disables during request, text → "Signing in…"
- Demo accounts hint block (monospace code tags)

**Flow:** `POST /auth/login` (form-urlencoded) → JWT → `GET /auth/me` → `showApp()`

---

## App Shell (`#app`)

Two-column flex layout (100vh):
- `<aside class="sidebar">` — fixed-width left column
- `<main class="main">` — flex-1 right column containing all views

---

## Sidebar

### Header
Brand icon (26×26, blue) + "CyberPolicy RAG" name.

### Body (`#sb-body`)
- **New Chat button** (`.new-chat`) — white fill, `+` icon, full sidebar width
- **Chat history list** — grouped by day bucket (Pinned / Today / Yesterday / date)

#### Chat Row (`.conv-wrap`)
Each session row has:
- **Blue pin dot** (`.pin-dot`) — visible only when pinned
- **Title button** (`.conv`) — click to select; ellipsis overflow
- **Action buttons** (`.conv-actions`) — fade in on hover:
  - Pin/Unpin (`.conv-pin`) — filled pin SVG when pinned, outline when not; blue colour when pinned
  - Rename (`.conv-ren`) — pencil icon; activates inline rename input
  - Delete (`.conv-del`) — ×  icon; red hover background

#### Rename Inline Mode
Replaces `.conv` button with `.conv-rename-input` (blue border). Enter commits, Escape cancels, blur commits.

#### Section Labels (`.sec`)
Uppercase 11px muted text: "Pinned", "Today", "Yesterday", date string.

### Nav (role-gated, `#sb-nav`)
Injected after chat list separator. Only for analyst/admin:
- **Audit Logs** nav item — visible to security_analyst + admin
- **Upload Policy** nav item — visible to admin only

Active view highlighted via `.nav-item.active`.

### Footer (`.sb-foot`)
- Avatar square (`.sb-av`) — 2-letter initials, deterministic colour from username hash
- Username + role display name
- Logout icon button (`.sb-logout`) — red hover

---

## Chat View (`#view-chat`)

### Header (`.view-hd`, 52px)
- Status dot (`.view-hd-dot`)
- Chat title (`#thread-title`) — current session name
- Role badge (`#role-badge`) — blue pill: USER / SECURITY-ANALYST / ADMIN
- Settings gear icon → toggles `#settings-panel` popover

### Settings Panel (`#settings-panel`)
Dropdown (272px) from gear button. Sections:
- **Session** — username, role display name
- **Document Access** — sensitivity badge chips (accessible ones coloured, inaccessible dim)
- **System** — LLM: MOCK, Embeddings: all-MiniLM-L6-v2

### Thread Scroll (`.thread-scroll`)
Scrollable, max-width 720px centred. Custom 4px scrollbar.

#### Empty State
When no messages, shows access card:
- Shield icon (coloured by role: green=user, blue=analyst, amber=admin)
- Role name + "Document Access"
- 4 sensitivity rows — accessible ones show "✓ Accessible" (green), others "✗ No access" (muted)
- 3 role-specific sample questions (clickable → fills composer textarea)

#### User Message (`.msg-user`)
Right-aligned bubble (max 72% width). Light fill (`#f0f0f0`), dark text (`#111`). Rounded: xl xl 5px xl.

#### Assistant Message (`.msg-agent`)
Left-aligned with avatar. Layout:
```
[avatar] CyberPolicy-RAG · HH:MM:SS
  [agent-bubble]
    [copy-btn top-right, fade in on hover]
    [risk flags row — if any]
    [answer body — varies by confidence]
    [footnotes — if sources present]
```

**Confidence states:**
- `answered` — plain answer text (`.answer-text`)
- `blocked` — red inline card with blocked icon + "Request blocked" / "Prompt injection blocked"; blocked-status line with red dot
- `error` — amber inline card with warning icon + "Request failed"
- `none` — amber inline card with triangle icon + "No authorised sources found"

**Thinking state:** 3-dot bounce animation while awaiting response. Avatar + "searching…" label.

**Copy button:** Position absolute top-right of bubble. Opacity 0 → 1 on bubble hover. Click copies answer text, icon → check, reverts after 1.8s.

**Footnotes (`.footnotes`):**
```
[1] [SENSITIVITY BADGE] Document Title — §Section Heading
```
Numbered list, sensitivity badge coloured, section heading prefixed with `§`.

**Risk flags:** Monospace red badges above answer text.

### Composer (`#comp-ta` + send)
Fixed bottom bar. Max-width 768px centred.
- Surface container with focus border transition
- Attach icon button (non-functional, visual only)
- Auto-resize textarea (min 24px, max 160px) — placeholder: "Ask about your cybersecurity policies…"
- Keyboard shortcut hint: `⌘↵`
- Send button — white fill → send on click or Cmd/Ctrl+Enter

---

## Audit Logs View (`#view-audit`)

### Header
- Title "Audit Logs"
- Role badge
- Refresh button (`.audit-refresh`) — with rotate icon

### Table
Max-width 1100px (1200px ≥1440, 1400px ≥1920). Horizontally scrollable. Min-width 720px.

**Columns:** Time | User | Role | Question | Status | Documents | Risk Flags

- **Time** — `HH:MM:SS` monospace, muted
- **User** — plain text
- **Role** — monospace blue badge (`.audit-role`)
- **Question** — truncated 260px, full text on title hover
- **Status** — coloured badge: `answered` (green), `blocked` (red), `no_source` (amber)
- **Documents** — monospace list of document titles used
- **Risk Flags** — red monospace badges or `—`

Sorted newest-first in JS before render. Count shown in toolbar.

---

## Upload Policy View (`#view-upload`)

Max-width 560px (600px ≥1440). Admin-only.

### Upload Form

**File drop zone (`.drop-zone`):**
- 2px dashed border → blue on hover/dragover → green when file selected
- Hidden `<input type="file" accept=".md,.txt,.pdf">`
- Upload icon + "Drop a file or click to browse" + "Supports .md, .txt, .pdf — max 10 MB"
- Selected filename shown in green monospace below

**Fields:**
- Document title — plain text input
- Sensitivity level — custom-styled `<select>` (arrow chevron via SVG background-image)
  - Options: public / internal / confidential / restricted
  - On change: sensitivity preview row shows coloured badge + "Accessible by: role, role"

**Submit button** — disabled until file + title + sensitivity all present. Text → "Uploading…" during request.

**Result block** — shown after submit:
- Success (green): "Upload successful" + message + chunk count + sensitivity
- Error (red): error message text

### Indexed Policies Table

Below upload form, separated by border. Columns: Title | Sensitivity | Filename | Uploaded | (delete)

- **Sensitivity** — coloured badge
- **Filename** — monospace muted
- **Uploaded** — short locale date + time, monospace muted
- **Delete** — red outlined button with trash icon; confirm dialog before delete; calls `DELETE /documents/{id}` then reloads list

---

## API Endpoints (consumed by UI)

| Method | Path | Auth | Purpose |
|---|---|---|---|
| POST | `/auth/login` | None | Get JWT (form-urlencoded) |
| GET | `/auth/me` | JWT | Verify token, get user info |
| POST | `/chat/query` | JWT | Ask question |
| GET | `/chats/` | JWT | List user's chats |
| POST | `/chats/` | JWT | Create new chat |
| GET | `/chats/{id}` | JWT | Load chat with messages |
| PATCH | `/chats/{id}` | JWT | Rename or pin/unpin chat |
| DELETE | `/chats/{id}` | JWT | Delete chat |
| GET | `/audit/logs` | JWT (analyst+admin) | Audit log table |
| POST | `/documents/upload` | JWT (admin) | Upload policy (multipart) |
| GET | `/documents/` | JWT (admin) | List indexed documents |
| DELETE | `/documents/{id}` | JWT (admin) | Remove document + chunks |

---

## Chat API Response Shape

```json
{
  "answer": "string",
  "sources": [
    {
      "document_title": "string",
      "filename": "string",
      "section_heading": "string | null",
      "page": "int | null",
      "sensitivity_level": "string | null"
    }
  ],
  "risk_flags": ["string"],
  "confidence": "high | medium | low | none | blocked | error",
  "chat_id": 123,
  "chat_title": "string"
}
```

`chat_id` and `chat_title` used to sync sidebar after first message creates a new chat on the backend.

---

## Chat History Persistence

Backend-owned. JWT-scoped (each user sees only their own chats).

- `GET /chats/` — returns `[{id, title, created_at, pinned}]` summaries
- `GET /chats/{id}` — returns full detail with `messages[]`
- Sidebar groups unpinned chats by day bucket (Today / Yesterday / date string)
- Pinned chats appear in "Pinned" section at top, sorted after unpinned in creation-desc order
- `PATCH /chats/{id}` with `{pinned: bool}` or `{title: "string"}`
- JWT persisted in `localStorage` as `cp_token`; restored on page load via `apiMe` validation

---

## State Object (`St`)

```js
const St = {
  token:          null,   // JWT string
  user:           null,   // { username, role }
  chats:          [],     // [{id, title, created_at, pinned}] — from backend
  activeId:       null,   // numeric chat id
  activeMessages: [],     // normalised messages for active chat
  busy:           false,  // prevents double-send
  view:           'chat', // 'chat' | 'audit' | 'upload'
};
```

---

## Role → Access Mapping (client-side display only)

```js
const ROLE_ACCESS = {
  user:             ['public', 'internal'],
  security_analyst: ['public', 'internal', 'confidential'],
  admin:            ['public', 'internal', 'confidential', 'restricted'],
};
```

Server enforces actual access. This map drives empty-state access card and settings panel chips only.

---

## Sample Questions by Role

```js
user:             ['What are the password complexity requirements?', ...]
security_analyst: ['What is the incident response procedure for a data breach?', ...]
admin:            ['What are the restricted data handling procedures?', ...]
```

---

## Responsive Breakpoints

| Min-width | Sidebar | Thread/Composer max-width | Audit max-width |
|---|---|---|---|
| default | 260px | 720px | 1100px |
| 1440px | 280px | 820px | 1200px |
| 1920px | 300px | 940px | 1400px |

---

## Accessibility Notes

- `aria-label` on copy button, conv-action buttons, textarea
- `role="button"` implied via `<button>` elements throughout
- `:focus-visible` outlines on interactive elements (blue `#1a6bff`)
- `prefers-reduced-motion` collapses all animations to 0.001ms
- Keyboard: Enter/Ctrl+Enter sends message; Escape cancels rename; Tab navigation through buttons

---

## Security-Relevant UI Behaviour

- Sensitivity level of retrieved chunks is **not shown** to end-users in chat thread
- Sources show document title + section heading only (no sensitivity badge in footnotes)
- Upload form shows sensitivity badge only in admin-owned upload view
- Prompt-guard blocked responses show red "blocked" card, logged to audit
- Output-guard does not surface a visible indicator (answer is silently filtered server-side)
- 401 response from any API call triggers auto-logout (`doLogout()`)
