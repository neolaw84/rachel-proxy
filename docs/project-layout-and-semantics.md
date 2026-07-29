# Project Layout & Component Semantics Reference

This document serves as the complete reference for directory layout, module boundaries, component semantics, and responsibilities across **RPG Agent Behind Chat Completion (RACHEL)**.

---

## 1. Complete Directory Layout

```
rpg-agent-behind-chat-completion/
├── src/rachel/                     # Python Proxy Server Application Package
│   ├── proxy.py                    # FastAPI entrypoint & middleware assembly
│   ├── auth.py                     # Authorization middleware & auth dependencies
│   ├── config.py                   # Environment & configs.yaml settings resolver
│   │
│   ├── agent/                      # LangGraph Agent Core Loop
│   │   ├── graph.py                # LangGraph state graph assembly & execution loop
│   │   ├── prompts.py              # Dynamic system prompt builder
│   │   ├── openrouter.py           # Upstream OpenRouter LLM HTTP client wrapper
│   │   ├── reasoning_formats.py    # Model reasoning tag parsers (<think>, etc.)
│   │   └── tools.py                # LangChain tool bindings (sandbox, dice, RNG)
│   │
│   ├── core/                       # Domain Logic, Storage & Key Vault
│   │   ├── db.py                   # SQLAlchemy ORM models & database engines
│   │   ├── api_key_storage.py      # Client proxy key storage engine drivers
│   │   ├── settings_storage.py     # Provider credentials & settings storage
│   │   ├── crypto.py               # AES-256-GCM envelope encryption & HKDF SHA-256
│   │   ├── session.py              # Session ID hierarchy & SHA-256 turn key generator
│   │   └── state.py                # Turn state store & LRU session tracking
│   │
│   ├── routes/                     # FastAPI Router Controllers
│   │   ├── completions.py          # POST /v1/chat/completions endpoint
│   │   ├── sessions.py             # Session inspection & turn CRUD endpoints
│   │   └── system.py               # Dashboard SPA, health, status & proxy keys API
│   │
│   ├── sandbox/                    # V8 Code Execution Isolate Sandbox
│   │   ├── v8_engine.py            # Py-Mini-Racer V8 engine wrapper
│   │   ├── sandbox.py              # Abstract SandboxEngine interface & fallbacks
│   │   ├── validation.py           # Pre-execution JavaScript code safety validator
│   │   └── schemas.py              # OpenRouter tool definition JSON schemas
│   │
│   └── static/                     # Compiled frontend SPA distribution assets
│       ├── index.html              # Static index HTML
│       └── assets/                 # Compiled CSS/JS web bundles
│
├── frontend/                       # Vite Single-Page Application Source
│   ├── index.html                  # SPA HTML container template
│   ├── vite.config.mjs             # Dual-target build config (desktop vs cloud)
│   ├── src/
│   │   ├── main.js                 # Frontend application lifecycle & tab router
│   │   ├── auth/
│   │   │   ├── LocalAuthModal.js   # Single-tenant local key password overlay
│   │   │   └── CloudAuthModal.js   # Multi-tenant SaaS OIDC JWT SSO overlay
│   │   ├── components/
│   │   │   ├── Header.js           # Navigation bar & tab selector
│   │   │   ├── CredentialsHelper.js# Step 1 client connection card & key builder
│   │   │   ├── ProxyKeysPanel.js   # Proxy API keys management & creation modal
│   │   │   ├── ProviderSettings.js # LLM provider settings & key vault form
│   │   │   ├── ProxyStatus.js      # System runtime monitor & status dashboard
│   │   │   ├── SessionInspector.js # Interactive session turn state inspector
│   │   │   └── SessionSidebar.js   # Session search sidebar
│   │   ├── services/
│   │   │   ├── api.js              # HTTP client fetch wrapper with Bearer token
│   │   │   ├── modal.js            # Confirmation modal dialog service
│   │   │   └── toast.js            # Toast alert notification service
│   │   └── styles/
│   │       └── main.css            # Centralized CSS design system & tokens
│
├── scripts/                        # Development & Build Automation Helpers
│   └── build_frontend.py           # Compiles Vite targets and syncs to static/
│
├── docs/                           # Architectural Documentation
│   ├── ai-index.md                 # Main AI guidance index & taboos
│   ├── architecture-and-guidelines.md # First-principles development guidelines
│   ├── project-layout-and-semantics.md# (This file) Layout & component semantics map
│   ├── all-about-auth.md           # Authentication & authorization boundaries
│   ├── all-about-sessions.md       # Session resolution hierarchy & turn keys
│   ├── configurations.md           # Setting parameters reference
│   └── road-to-multi-tenant.md     # Multi-tenant Cloud Run & Neon Postgres roadmap
│
├── tests/                          # Automated Pytest Suite
│   ├── test_agent_flow.py          # End-to-end agent loop tests
│   ├── test_crypto_envelope.py     # Envelope encryption tests
│   ├── test_file_storage_schema_parity.py # File vs relational storage parity
│   ├── test_multi_provider.py      # Provider switcher tests
│   ├── test_postgres_storage.py    # Postgres DB integration tests
│   ├── test_proxy.py               # API route completion tests
│   ├── test_proxy_keys_and_auth.py # Proxy key CRUD & auth dependency tests
│   └── test_state_and_sandbox.py   # State tracking & V8 sandbox execution tests
│
├── configs.yaml                    # System runtime configurations
└── pyproject.toml                  # Python package specifications & build config
```

---

## 2. Component Semantics Map

### Backend (`src/rachel/`)

| File / Module | Responsibilities & Semantic Purpose | Key Interfaces & Dependencies |
| :--- | :--- | :--- |
| **`proxy.py`** | FastAPI application factory, middleware assembly, static directory mounting, and router registration. | `FastAPI`, `CORSMiddleware`, `StaticFiles` |
| **`auth.py`** | Inbound proxy key validation, local admin key checking, and multi-tenant OIDC JWT stateless verification. | `require_proxy_key`, `require_local_admin_key`, `require_oidc_jwt_user`, `get_admin_user` |
| **`config.py`** | Resolves settings from environment variables, `configs.yaml`, and path constants (`KEY_FILE`, `STATE_STORAGE_DIR`). | `CONFIG_PUBLIC_URL`, `STORAGE_ENGINE`, `SANDBOX_TIMEOUT` |
| **`agent/graph.py`** | LangGraph agent state graph assembly, turn execution loop, tool node execution, and fallback strategies. | `StateGraph`, `END`, `compile()` |
| **`agent/prompts.py`** | Dynamic RPG system prompt generator, persona formatting, and world state injection. | `build_system_prompt()` |
| **`agent/openrouter.py`** | Upstream OpenRouter LLM API client wrapper supporting streaming and non-streaming completions. | `httpx.AsyncClient` |
| **`agent/reasoning_formats.py`** | Model-specific reasoning tag parsers (`<think>`, `[reasoning]`) and payload formatters. | `extract_reasoning_payload()` |
| **`agent/tools.py`** | LangChain tool bindings for the V8 JS code sandbox, dice roller, and RNG utilities. | `sandbox_tool`, `dice_tool` |
| **`core/db.py`** | SQLAlchemy ORM models (`Tenant`, `TenantApiKey`, `TenantCredential`, `TenantSetting`, `Session`) and engine factories. | `get_engine()`, `get_sessionmaker()`, `init_db()` |
| **`core/api_key_storage.py`** | Client Proxy Key storage interface and drivers (`FileApiKeyStorage`, `RelationalApiKeyStorage`). | `BaseApiKeyStorage`, `get_api_key_storage()` |
| **`core/settings_storage.py`** | Provider credentials and active provider selection storage engine per tenant. | `BaseSettingsStorage`, `get_settings_storage()` |
| **`core/crypto.py`** | AES-256-GCM envelope encryption/decryption routines and HKDF-SHA256 key derivation. | `encrypt_credential()`, `decrypt_credential()`, `hash_key()` |
| **`core/session.py`** | Session ID hierarchy resolution, turn key generation (`SHA-256[:24]`), and turn state hashing. | `resolve_session_id()`, `generate_turn_key()` |
| **`core/state.py`** | Turn state store, LRU turn history management, and session state persistence. | `StateStorage`, `list_all_sessions()` |
| **`routes/completions.py`** | Endpoint controller for `POST /v1/chat/completions` and `POST /v1/{session_id}/chat/completions`. | `FastAPI.APIRouter` |
| **`routes/sessions.py`** | Endpoint controllers for session inspecting, turn state viewing, and session CRUD operations. | `/v1/sessions`, `/v1/sessions/{id}` |
| **`routes/system.py`** | Endpoint controllers for SPA static dashboard (`/`), status (`/v1/status`), providers (`/v1/providers`), and client proxy keys (`/v1/proxy-keys`). | `/v1/status`, `/v1/providers`, `/v1/proxy-keys` |
| **`sandbox/v8_engine.py`** | Py-Mini-Racer V8 JavaScript isolate sandbox engine wrapper for safe code execution. | `MiniRacerV8Engine` |
| **`sandbox/sandbox.py`** | Abstract sandbox engine interface definition and fallback implementations. | `BaseSandboxEngine` |
| **`sandbox/validation.py`** | Code safety validator scanning for unsafe patterns before V8 execution. | `validate_js_code()` |
| **`sandbox/schemas.py`** | JSON Schemas for OpenRouter tool definitions. | `SANDBOX_TOOL_SCHEMA` |

---

### Frontend (`frontend/`)

| File / Component | Responsibilities & Semantic Purpose | Key Mappings & Services |
| :--- | :--- | :--- |
| **`index.html`** | SPA main HTML scaffold, font imports, and container root element definitions. | `#auth-container`, `#main-container` |
| **`src/main.js`** | Application lifecycle entrypoint, tab switching controller, and target-aware component initialization. | `renderHeader`, `renderCredentialsHelper`, `renderProxyKeysPanel` |
| **`src/auth/LocalAuthModal.js`** | Single-tenant local password overlay for proxy key authentication. | Uses `setApiKey()` to save key to `localStorage` |
| **`src/auth/CloudAuthModal.js`** | Multi-tenant SaaS SSO overlay for stateless OIDC JWT authentication. | Manages SSO redirect & bearer token |
| **`src/components/CredentialsHelper.js`** | "Step 1" client setup card displaying API URL, Master Key (local mode), or client key generator (cloud mode). | `renderCredentialsHelper(container, { isCloud })` |
| **`src/components/ProxyKeysPanel.js`** | "Client Proxy API Keys" tab management panel. Lists active keys (`/v1/proxy-keys`), handles key creation modal, and revokes keys. | `renderProxyKeysPanel(container, { isCloud })` |
| **`src/components/ProviderSettings.js`** | "LLM Provider Settings" panel for selecting active provider (OpenRouter, OpenAI, Gemini, DeepSeek) and configuring API keys. | Hitting `/v1/providers` and `/v1/providers/active` |
| **`src/components/ProxyStatus.js`** | "System Status" monitor displaying runtime statistics, active sessions count, sandbox engine, and public API endpoint. | Hitting `/v1/status` |
| **`src/components/SessionInspector.js`** | Interactive turn state inspector and turn history viewer for active roleplay sessions. | Hitting `/v1/sessions/{id}` |
| **`src/components/SessionSidebar.js`** | Sidebar listing active roleplay sessions with search filtering and session selection callbacks. | Hitting `/v1/sessions` |
| **`src/components/Header.js`** | Navigation header with tab selectors (Setup, Sessions, Proxy Keys, System Status), refresh, and logout actions. | Controls tab views (`#view-setup`, `#view-keys`, etc.) |
| **`src/services/api.js`** | HTTP fetch wrapper automatically injecting `Authorization: Bearer <key>` header and handling 401 unauthorized callbacks. | `apiFetch()`, `getApiKey()`, `setApiKey()` |
| **`src/services/modal.js`** | Reusable confirmation modal overlay dialog. | `showConfirm(title, msg, onOk)` |
| **`src/services/toast.js`** | Floating toast notification alerts for user feedback. | `showToast(msg, type)` |
| **`src/styles/main.css`** | Centralized modern CSS design system (dark mode palette, glassmorphism, buttons, cards, key display boxes). | Tokens (`--bg-base`, `--accent`, `--green`, `--radius`) |
| **`vite.config.mjs`** | Dual-target Vite build configuration outputting to `frontend/dist/local` or `frontend/dist/cloud`. | `VITE_MULTI_TENANT` compiler flag |

---

### Scripts & Build Automation (`scripts/`)

| Script | Responsibilities & Semantic Purpose | Usage |
| :--- | :--- | :--- |
| **`scripts/build_frontend.py`** | Compiles Vite frontend for specified target (`local` or `cloud`) and syncs assets directly into `src/rachel/static/`. | `python scripts/build_frontend.py --target local` |
