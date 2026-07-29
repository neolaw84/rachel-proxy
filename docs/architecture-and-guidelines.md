# Architecture, System Guidelines & First-Principles Workflow

This document serves as the authoritative architectural blueprint and first-principles development guide for **RPG Agent Behind Chat Completion (RACHEL)**.

---

## 1. First-Principles Development Workflow

To prevent contract drift, schema mismatches, and UI/UX omissions, all AI coding agents and human developers MUST adhere to the following workflow principles when adding or modifying features:

### Rule 1: First-Principles Intent Verification
- **Never blindly execute feature requests.** Coding Agents MUST NOT blindly add feature $X$ when the user requests $X$.
- **Reverse-engineer and consult**: Always consider *why* the user is requesting $X$, reverse-engineer the underlying requirement, analyze what system-wide impacts the change will make across the entire codebase (backend routers, database schemas, frontend components, and static build targets), and consult with the user to verify intent if ambiguous.
- **Holistic plan presentation**: Present the user with all related changes required across all components so that the system continues to work coherently as a unified whole.

#### Sub-Rule 1.1: Contract & Schema Primacy
- **Never guess endpoints or payload schemas.** Before modifying any frontend component or backend route, inspect the exact route handler in `src/rachel/routes/` to verify:
  - Exact URL path (e.g. `/v1/proxy-keys`, not `/v1/keys`).
  - Required request payload key names (e.g. `{ "name": "..." }`, not `{ "label": "..." }`).
  - Response JSON structure (e.g. `data.proxy_key`, not `data.raw_key`, and `k.prefix`, not `k.key_prefix`).

#### Sub-Rule 1.2: Complete UI/UX End-to-End Delivery
- **No superficial or raw browser placeholders.** User actions in the frontend must NEVER stop at console logs, browser `alert()`, or unstyled fallbacks, unless explicitly requested or approved by the user.
- Every user action that generates sensitive data or triggers state changes MUST provide a complete UI affordance:
  - A dedicated, styled modal or card container.
  - Clear monospace text display for raw secret keys.
  - A functional **"📋 Copy to Clipboard"** button with visual feedback ("✓ Copied!").
  - Dismiss/close mechanisms and error toast notifications (`showToast`).

#### Sub-Rule 1.3: Dual-Target Build & Asset Verification
- The frontend supports two statically compiled build targets:
  - **`desktop` (Local Mode)**: Local proxy key password modal, single-tenant UI.
  - **`cloud` (Multi-Tenant Mode)**: SSO authentication overlay, multi-tenant UI.
- Whenever modifying code in `frontend/`, verify compilation and static asset synchronization using the python build helper:
  ```bash
  venv/bin/python scripts/build_frontend.py --target local
  venv/bin/python scripts/build_frontend.py --target cloud
  venv/bin/python scripts/build_frontend.py --target local
  ```

---

## 2. High-Level Architecture & Layout References

### High-Level Architecture

```
+-------------------------------------------------------------------+
|                        Frontend SPA (Vite)                        |
|  [Header] [Setup / Creds] [Sessions] [Proxy Keys] [Status Monitor]|
+-------------------------------------------------------------------+
                                 | HTTP / JSON API
                                 v
+-------------------------------------------------------------------+
|                       FastAPI Proxy Server                        |
|  - Auth Middleware (Local Proxy Key / OIDC JWT SSO)              |
|  - Router Controllers: /v1/chat/completions, /v1/proxy-keys, etc. |
+-------------------------------------------------------------------+
        |                                          |
        v                                          v
+-----------------------+              +----------------------------+
|  LangGraph Agent Loop |              |  Storage & Key Vault Layer |
|  - Graph State Nodes  |              |  - SQLite / Neon Postgres  |
|  - System Prompts     |              |  - AES-256 Envelope Crypto |
|  - V8 JS Sandbox      |              |  - Tenant Settings & Keys  |
+-----------------------+              +----------------------------+
```

---

### Layout & Semantics Map

For the complete file-by-file directory tree, module boundaries, and component semantics map across backend (`src/rachel/`), frontend (`frontend/`), and build scripts (`scripts/`), please refer to:

👉 **[docs/project-layout-and-semantics.md](project-layout-and-semantics.md)**
