# Code & Security Review — RACHEL Proxy
**Date**: 2026-07-25  
**Reviewer**: Senior Software Engineer & Security Expert  
**Scope**: Full codebase review — architecture, SOLID adherence, security posture, and actionable recommendations.  
**Branch / Commit**: `HEAD` at time of review

---

## Executive Summary

RACHEL is a well-structured, single-responsibility-driven FastAPI proxy that routes JanitorAI chat completions through a stateful LangGraph RPG agent. The codebase demonstrates strong intent around SOLID principles, clean layering, and a pragmatic two-mode deployment model (desktop/local vs. cloud/multi-tenant). The team has done excellent work on:

- Dual-engine storage abstraction (File ↔ SQL) with verified parity tests
- AES-256-GCM envelope encryption for at-rest credentials
- SHA-256 hashing of proxy API keys (never stored in cleartext)
- PKCE OAuth flow for OpenRouter authorization

Several **security-critical issues** and a handful of **engineering quality concerns** were found and are detailed below. All findings are prioritized and include concrete remediation guidance.

---

## 1. Critical Security Findings

### SEC-01 · Broken PostgreSQL URL Construction (Data Loss / Misconfiguration Risk)

**File**: `src/rachel/config.py` L140–L151  
**Severity**: 🔴 Critical

```python
def get_default_db_url() -> str:
    if DATABASE_URL:
        return DATABASE_URL
    if any((PGHOST, PGUSER, PGDATABASE)):
        user = PGUSER or ""
        pwd = f":{PGPASSWORD}" if PGPASSWORD else ""
        host = PGHOST or "localhost"
        port = f":{PGPORT}" if PGPORT else ""
        dbname = f"/{PGDATABASE}" if PGDATABASE else ""
        auth = f"{user}{pwd}@" if user or pwd else ""
    return f"sqlite:///{DEFAULT_SQLITE_PATH}"   # BUG: always returns SQLite
```

The constructed `postgresql+psycopg2://...` URL is built into local variables but **never returned**. The function unconditionally falls through to the SQLite fallback. In a cloud deployment where `DATABASE_URL` is not set but `PGHOST`/`PGUSER` are, the proxy silently connects to local SQLite — causing data to be persisted in the wrong store, potentially with concurrent writes from multiple Cloud Run instances.

**Fix**:

```python
def get_default_db_url() -> str:
    if DATABASE_URL:
        return DATABASE_URL
    if any((PGHOST, PGUSER, PGDATABASE)):
        user = PGUSER or ""
        pwd = f":{PGPASSWORD}" if PGPASSWORD else ""
        host = PGHOST or "localhost"
        port = f":{PGPORT}" if PGPORT else ""
        dbname = f"/{PGDATABASE}" if PGDATABASE else ""
        auth = f"{user}{pwd}@" if user or pwd else ""
        return f"postgresql+psycopg2://{auth}{host}{port}{dbname}"  # return it
    return f"sqlite:///{DEFAULT_SQLITE_PATH}"
```

---

### SEC-02 · Insecure PKCE Fallback — State Mismatch Ignored

**File**: `src/rachel/routes/system.py` L283–L288  
**Severity**: 🔴 Critical

```python
code_verifier = _PKCE_VERIFIERS.pop(state, None) if state else None
if not code_verifier:
    # Fallback if state was not returned
    if _PKCE_VERIFIERS:
        code_verifier = next(iter(_PKCE_VERIFIERS.values()))
        _PKCE_VERIFIERS.clear()
```

The PKCE `state` parameter exists **specifically** to prevent CSRF attacks on OAuth callbacks. When `state` does not match any stored verifier, the code silently grabs whichever verifier happens to be in the dict and proceeds with the token exchange. This allows an attacker who can initiate their own PKCE flow (e.g., from another browser tab or by intercepting the callback URL) to potentially bind their authorization code to the victim's verifier.

Additionally, `_PKCE_VERIFIERS` is a module-level in-memory dict. In a multi-worker/multi-process deployment (multiple uvicorn workers, Cloud Run auto-scaling), each process has its own dict, making the callback arbitrarily fail or succeed based on which process receives the request.

**Fix**:

```python
# Remove the fallback entirely
if not code_verifier:
    raise HTTPException(
        status_code=400,
        detail="OAuth state mismatch or session expired. Please restart the authorization flow."
    )
```

**Multi-process context**: Yes — this is precisely the problem. Cloud Run (and any multi-worker deployment) can spin up N container instances. The user's `/authorize` request may hit instance 1 (which stores the verifier in its local dict), while the OAuth redirect callback hits instance 2 (where the dict is empty). The state-mismatch fallback then silently grabs the wrong verifier — or fails arbitrarily.

**Zero-infrastructure alternative (no Redis required)**: Encode the `code_verifier` into the `state` parameter itself as an **HMAC-signed, time-limited token**. The verifier travels in the redirect URL, so any process can verify and extract it on callback without any shared memory:

```python
# On /authorize: encode verifier into signed state token (signed with PROXY_API_KEY)
import jwt as pyjwt, time
state_payload = {"cv": code_verifier, "exp": int(time.time()) + 600, "aud": "pkce"}
state_token = pyjwt.encode(state_payload, PROXY_API_KEY, algorithm="HS256")

# On /callback: decode and verify locally — no shared dict, no Redis
try:
    decoded = pyjwt.decode(state_token, PROXY_API_KEY, algorithms=["HS256"], audience="pkce")
    code_verifier = decoded["cv"]
except Exception:
    raise HTTPException(status_code=400, detail="Invalid or expired OAuth state.")
```

This costs nothing, works across any number of Cloud Run instances, and naturally enforces a 10-minute expiry on the PKCE handshake. The `_PKCE_VERIFIERS` dict can be removed entirely.

---

### SEC-03 · Insecure Default Encryption Key

**File**: `src/rachel/config.py` L155–L158  
**Severity**: 🔴 Critical

```python
ENCRYPTION_MASTER_KEY: str = os.environ.get(
    "ENCRYPTION_MASTER_KEY",
    _cfg.get("encryption_master_key", "rachel-master-encryption-secret-default")
)
```

The hard-coded fallback `"rachel-master-encryption-secret-default"` is a known-plaintext master key committed to public version control. Any operator who forgets to set `ENCRYPTION_MASTER_KEY` in production will have all their LLM API credentials encrypted with a publicly-known key. A database dump combined with this known key is sufficient for a full credential compromise.

**Fix**: Remove the plaintext fallback entirely. If the variable is unset, raise a `RuntimeError` at startup in cloud/SQL mode. For local mode, the master key is derived from `PROXY_API_KEY` in the existing `derive_kek` path, so no extra env var is needed.

```python
ENCRYPTION_MASTER_KEY: str = os.environ.get("ENCRYPTION_MASTER_KEY") or ""
```

In `crypto.py → derive_kek`, add a guard:

```python
else:
    if not config.ENCRYPTION_MASTER_KEY:
        raise RuntimeError(
            "ENCRYPTION_MASTER_KEY must be set for multi-tenant/relational storage mode."
        )
    secret_bytes = config.ENCRYPTION_MASTER_KEY.encode("utf-8")
```

---

### SEC-04 · HKDF Constant Salt in Local Mode

**File**: `src/rachel/core/crypto.py` L21–L40  
**Severity**: 🟠 High

```python
if tenant_id == "local":
    secret_bytes = PROXY_API_KEY.encode("utf-8")
    salt = b"local"          # constant, predictable salt
    info = b"local_admin"
```

HKDF salt should be random or at minimum unique per derivation context. Using the constant `b"local"` as a salt reduces HKDF domain-separation strength in principle.

**Trade-off assessment**: This is a **known and widely-accepted trade-off** for this class of codebase and is acceptable as-is. HKDF's security requirement is that the primary entropy comes from the Input Keying Material (IKM); the salt provides domain separation, not entropy. In local mode the IKM (`PROXY_API_KEY`) is a 32-byte URL-safe random secret — amply entropic. A constant salt does not weaken the derived key when the IKM is strong. GCP Tink and similar production cryptography libraries follow the same pattern for symmetric-key derivation when no external random salt is available.

The cloud path correctly uses `salt = tenant_id.encode()` (unique per tenant), which is the right design. The local-mode constant salt is not a copy-paste risk because the branching is explicit (`if tenant_id == "local":`) and well-contained in a single file.

**Recommended fix (documentation only)**: Add a short comment in `crypto.py` confirming this trade-off is intentional, so future contributors do not "fix" it incorrectly. No code change required.

---

### SEC-05 · Error Detail Leaks JWT Validation Failure Reason

**File**: `src/rachel/auth.py` L151–L157  
**Severity**: 🟠 High

```python
except Exception as exc:
    logger.warning("SSO JWT validation failed: %s", exc)
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=f"Invalid SSO authentication token: {exc}",  # leaks internal error
    )
```

Returning the raw exception string to clients can leak internal state, library versions, cryptographic error types, or algorithm names that assist attackers in crafting valid-looking tokens.

**Fix**:

```python
raise HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Invalid SSO authentication token.",
    headers={"WWW-Authenticate": "Bearer"},
)
```

---

### SEC-06 · Auth Fallback Silently Bypasses Storage Layer on Failure

**File**: `src/rachel/auth.py` L89–L97  
**Severity**: 🟠 High

```python
except HTTPException:
    raise
except Exception as exc:
    logger.warning("Error during proxy key lookup: %s", exc)

# 2. Fallback check against local PROXY_API_KEY
if secrets.compare_digest(raw_token, PROXY_API_KEY):
    request.state.tenant_id = "local"
    return "local"
```

If the storage layer raises any exception (e.g., database connectivity loss, corrupt JSON file), the code silently falls through to plain-text comparison against `PROXY_API_KEY`. A user whose key has been revoked could still authenticate if the storage layer was down at the time of their request.

**Fix**: Distinguish between "key not found" (fall through is acceptable) and "storage failure" (which should surface an alert). Consider raising a `503 Service Unavailable` on storage errors rather than silently degrading to bootstrap-key-only auth.

---

### SEC-07 · OIDC Algorithm Negotiation Too Broad — Algorithm Confusion Risk

**File**: `src/rachel/auth.py` L133–L138  
**Severity**: 🟠 High

```python
payload = jwt.decode(
    token,
    signing_key.key,
    algorithms=["RS256", "ES256", "HS256"],  # HS256 is symmetric!
    options={"verify_aud": False},
)
```

Accepting `HS256` alongside asymmetric algorithms opens the "algorithm confusion" attack vector. An attacker could craft a JWT signed with `HS256` using the JWKS public key bytes as the HMAC secret, potentially bypassing signature verification.

**Fix**: Restrict to asymmetric algorithms only:

```python
payload = jwt.decode(
    token,
    signing_key.key,
    algorithms=["RS256", "ES256"],  # HS256 is never valid for OIDC
    options={"verify_aud": False},
)
```

---

### SEC-08 · Audience Verification Disabled

**File**: `src/rachel/auth.py` L137  
**Severity**: 🟡 Medium

```python
options={"verify_aud": False},
```

Disabling audience verification means any valid JWT issued by the OIDC provider — for any application — will pass RACHEL's authentication. A token originally issued for a completely different service can authenticate against RACHEL.

**Fix**: Configure `OIDC_AUDIENCE` in config and pass it to `jwt.decode`:

```python
payload = jwt.decode(
    token,
    signing_key.key,
    algorithms=["RS256", "ES256"],
    audience=OIDC_AUDIENCE,
)
```

---

### SEC-09 · Sandbox Engine Instantiated Per-Request

**File**: `src/rachel/sandbox/sandbox.py` L18–L24  
**Severity**: 🟡 Medium (performance / DoS risk)

```python
def get_sandbox_engine() -> SandboxEngine:
    engine_name = os.environ.get("RACHEL_SANDBOX_ENGINE", "v8").strip().lower()
    if engine_name == "python":
        return PythonSandboxEngine()
    else:
        return V8SandboxEngine()
```

A new `V8SandboxEngine` is created on every call. V8 context initialization (via `py-mini-racer`) carries meaningful overhead. `get_sandbox_engine()` is called in **four hot-path call sites** per request: `openrouter.py:82` (tool schema resolution), `nodes.py:124` (system instruction context), `nodes.py:350` (sandbox code execution), and `tools.py:30` (tool execution).

**Scope clarification**: The fix should be a **process-level singleton** — `lru_cache` is the correct mechanism. This is *not* request-level, and request-level would be incorrect here. The engine selection is determined entirely by `RACHEL_SANDBOX_ENGINE`, an environment variable that never changes during process lifetime. More importantly, `SandboxEngine.execute(code, state, timeout)` is a **stateless call** — all per-user, per-session, and per-campaign state is passed as arguments. Multiple concurrent requests (across different users, sessions, campaigns) share one engine instance safely, because py-mini-racer creates a fresh V8 execution context per `.eval()` call internally.

**Fix**:

```python
import functools

@functools.lru_cache(maxsize=1)
def get_sandbox_engine() -> SandboxEngine:
    engine_name = os.environ.get("RACHEL_SANDBOX_ENGINE", "v8").strip().lower()
    if engine_name == "python":
        return PythonSandboxEngine()
    return V8SandboxEngine()
```

---

## 2. Engineering Quality Findings

### ENG-01 · `get_default_model` Has Redundant `hasattr` Guard

**File**: `src/rachel/core/settings_storage.py` L176–L180  
**Severity**: 🟡 Medium

```python
def get_default_model(self) -> str | None:
    if not hasattr(self, "_data"):   # defensive guard implies init ordering issue
        return None
    bucket = self._get_tenant_bucket()
    return bucket.get("default_model")
```

The `hasattr` guard on `_data` implies the method can be called before `__init__` completes — a symptom of either circular initialization or overly broad `super().__init__` calls. The same pattern appears in `get_reasoning_format`.

**Fix**: Ensure `_data` is initialized as an empty sentinel in `BaseSettingsStorage.__init__` before any abstract method calls can occur.

---

### ENG-02 · `RelationalSessionStorage.delete` Delegates to `reset` — Document the Equivalence

**File**: `src/rachel/core/state.py` L305–L306  
**Severity**: 🟡 Medium

```python
def delete(self) -> None:
    self.reset()
```

`FileSessionStorage.delete` unlinks the file from disk. `RelationalSessionStorage.delete` calls `reset()` which deletes the database row — functionally equivalent for the current denormalized-blob schema, but semantically surprising and fragile if per-session metadata columns are ever added. Add a comment explaining this is intentional.

---

### ENG-03 · `hash_key` Defined in Two Modules — DRY Violation

**File**: `src/rachel/core/api_key_storage.py` L25–L28 and `src/rachel/core/db.py` L151–L153  
**Severity**: 🟡 Medium

Both files define an identical `hash_key(raw_key: str) -> str` function with the same SHA-256 logic. Any future change to hashing semantics must be applied in two places.

**Fix**: Consolidate into `core/crypto.py` and import from there in both `db.py` and `api_key_storage.py`.

---

### ENG-04 · `SessionStateStore` is a Redundant Wrapper

**File**: `src/rachel/core/state.py` L387–L424  
**Severity**: 🟢 Low

`SessionStateStore` is a "compatibility wrapper delegator" that proxies every method call to `get_session_storage(...)`. Since `get_session_storage` already returns a `BaseSessionStorage`, the wrapper adds no new behavior and doubles the call depth. The `list_sessions` classmethod implementation also silently ignores `tenant_id`.

**Fix**: Deprecate and remove in favor of direct calls to `get_session_storage`.

---

### ENG-05 · Trigger Logic Triplicated in `graph.py` — OCP / SRP Violation

**File**: `src/rachel/agent/graph.py` L147–L187  
**Severity**: 🟡 Medium  
**Status**: ⏳ Deferred — the author has confirmed this block will be refactored into a **composer pattern** in the next release. The current hard-coded style is an intentional staging step; ENG-05 should be re-evaluated and applied at that point.

The plan/summary/cleanup trigger calculation blocks are near-identical three times, differing only in XOR seed mask, config variables, and output variable name. Adding a new trigger type (e.g., `lore-update`) currently requires copy-pasting another ~20-line block and updating routing logic in `nodes.py`.

**Proposed fix (for next release)**: Extract to a `_compute_trigger_fired(trigger_type, turn_number, ...)` helper and call it three times with different config arguments:

```python
def _compute_trigger_fired(
    trigger_type: str,
    turn_number: int,
    interval_turns: int,
    trigger_probability: float,
    offset: int,
    gap: int,
    seed_mask: int,
    msg_contents: list[str],
) -> bool:
    if trigger_type == "disabled":
        return False
    if trigger_type == "probabilistic":
        seed = int(hashlib.sha256("\x00".join(msg_contents).encode()).hexdigest(), 16)
        return random.Random(seed ^ seed_mask).random() < trigger_probability
    if offset > 0:
        return turn_number >= offset and (turn_number - offset) % interval_turns == 0
    return turn_number == 1 or turn_number % interval_turns == 0
```

---

### ENG-06 · `detect_public_url()` Re-evaluated on Every `/v1/status` Request

**File**: `src/rachel/routes/system.py` L47–L71  
**Severity**: 🟢 Low

The function reads environment variables and performs string operations on every request. These values are stable for the process lifetime.

**Fix**: Cache via `@functools.lru_cache(maxsize=1)` or compute once in the lifespan context.

---

### ENG-07 · `_STATIC_INDEX` Uses `os.path` Instead of `pathlib.Path`

**File**: `src/rachel/routes/system.py` L37  
**Severity**: 🟢 Low

```python
_STATIC_INDEX = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static", "index.html")
```

Per project convention (`docs/ai-index.md`), paths should use `pathlib.Path`:

```python
_STATIC_INDEX = Path(__file__).resolve().parent.parent / "static" / "index.html"
```

---

### ENG-08 · `FileApiKeyStorage` Reads Full JSON on Every Instantiation

**File**: `src/rachel/core/api_key_storage.py` L77  
**Severity**: 🟢 Low (scalability)

`get_api_key_storage()` is called on every authenticated request inside `require_proxy_key`, leading to repeated disk reads and full deserialization of `tenant_api_keys.json`.

**Fix**: Module-level singleton with invalidation on write, or a short-TTL in-memory cache. Low priority for single-tenant desktop use, but important to address before cloud deployment.

---

### ENG-09 · DB Session Leaked in `RelationalApiKeyStorage.__init__`

**File**: `src/rachel/core/api_key_storage.py` L193  
**Severity**: 🟡 Medium (resource leak)

```python
seed_bootstrap_key(self.SessionMaker(), tenant_id=self.tenant_id)
```

`self.SessionMaker()` creates an ORM session that is passed into `seed_bootstrap_key` but never explicitly closed by the caller. `seed_bootstrap_key` commits but does not close. The session will eventually be garbage-collected, but it leaks a connection slot in pool-based deployments (PostgreSQL).

**Fix**:

```python
with self.SessionMaker() as session:
    from rachel.core.db import seed_bootstrap_key
    seed_bootstrap_key(session, tenant_id=self.tenant_id)
```

---

### ENG-10 · Empty Alias Subclasses — Remove or Document

**File**: `src/rachel/core/settings_storage.py` L323–L325 and `src/rachel/core/state.py` L357–L359  
**Severity**: 🟢 Low

`PostgresSettingsStorage` and `PostgresSessionStorage` are empty `pass`-body subclasses with no overrides. They currently serve only as import aliases for their parent `RelationalSettingsStorage` / `RelationalSessionStorage` classes.

**PostgreSQL feature parity clarification**: These empty subclasses have **no impact on PostgreSQL functionality** — PostgreSQL, SQLite, and File storage are fully interchangeable via the existing test suite. `RelationalSettingsStorage` and `RelationalSessionStorage` handle both SQLite and PostgreSQL via SQLAlchemy's dialect abstraction. **PostgreSQL is fully working.**

**Recommended action**: Remove both empty subclasses and use the relational base classes directly in the factory functions. If there is future intent to add PostgreSQL-specific behaviour (e.g., `LISTEN/NOTIFY`, advisory locks), reintroduce them at that point with a clear docstring explaining their purpose.

---

### ENG-11 · Full Message Payload Logged at DEBUG

**File**: `src/rachel/routes/completions.py` L86–L95  
**Severity**: 🟡 Medium (data privacy)

```python
logger.debug(
    "Incoming Request: ... | Payload: %s",
    _json.dumps(payload, ensure_ascii=False),
)
```

The full conversation payload — potentially containing sensitive user content — is logged at DEBUG. In production with DEBUG inadvertently enabled, all user conversations would be written to log aggregators. The `Authorization` header is already redacted; the message bodies are not.

**Fix**: Log only metadata (session_id, turn_key, message count) at DEBUG. Reserve full-payload logging for an explicit `TRACE` log level behind a feature flag.

---

### ENG-12 · `_get_active_provider_config` is Not Request-Scoped (Multi-Tenant Bug)

**File**: `src/rachel/routes/completions.py` L45–L57  
**Severity**: 🟡 Medium

```python
def _get_active_provider_config() -> tuple[str, str, str, str]:
    storage = get_settings_storage()   # no tenant_id — always "local"
```

This function always fetches settings for `tenant_id="local"`, ignoring the authenticated tenant resolved by `require_proxy_key`. In multi-tenant mode, all tenants would share the same "local" provider configuration — a correctness bug and a potential security boundary violation.

**Fix**: Remove `_get_active_provider_config` and resolve settings inline within the endpoint, using the tenant_id from `request.state`:

```python
async def proxy_chat_completions(request: Request, ...) -> Any:
    tenant_id = getattr(request.state, "tenant_id", "local")
    storage = get_settings_storage(tenant_id=tenant_id)
    active_provider, base_url, api_key, default_model = storage.get_active_provider_details()
    if not api_key:
        raise HTTPException(status_code=400, detail=f"No API key configured for '{active_provider}'.")
```

---

## 3. SOLID Assessment

| Principle | Status | Notes |
|---|---|---|
| **S** Single Responsibility | ✅ Strong | Each module is well-scoped. `session.py`, `state.py`, `auth.py`, `crypto.py` do not bleed concerns. Module SLoC averages are within the declared 100–350 line target. |
| **O** Open/Closed | ⚠️ Partial | Storage engines are extensible via ABC. Trigger logic in `graph.py` requires modification (not extension) to add new trigger types. See ENG-05. |
| **L** Liskov Substitution | ✅ Strong | `FileSessionStorage` and `RelationalSessionStorage` honour the same `BaseSessionStorage` contract and are verified interchangeable by the parity test suite. Minor semantic gap on `delete` (ENG-02). |
| **I** Interface Segregation | ✅ Strong | Base classes expose only what their consumers need. `BaseApiKeyStorage`, `BaseSettingsStorage`, and `BaseSessionStorage` are lean and purpose-built. |
| **D** Dependency Inversion | ✅ Strong | Routers depend on abstract factory functions, not concrete classes. FastAPI `dependency_overrides` correctly swaps auth implementations between desktop and cloud entrypoints. |

---

## 4. Architecture Observations

### A1 · Dashboard Served Without Auth (Intentional)

`GET /` returns the SPA HTML without authentication. This is a deliberate design choice for local desktop mode (the UI handles auth client-side). In cloud deployments, this surface should be gated at the infrastructure level (CDN auth rules, IAP, VPN) or the cloud entrypoint should apply an auth middleware for the root path.

### A2 · In-Memory PKCE Store is Not Multi-Process Safe

`_PKCE_VERIFIERS` is a module-level dict (see SEC-02). In any deployment with multiple workers (uvicorn `--workers N`, gunicorn, Cloud Run auto-scaling), the OAuth initiation and callback may land on different processes, causing silent failures in production.

### A3 · PKCE Callback Saves Credentials Without Tenant Context

**File**: `src/rachel/routes/system.py` L314–L316

```python
storage = get_settings_storage()   # no tenant_id
storage.set_credential("openrouter_pkce", api_key)
```

The OAuth callback is a public endpoint (unauthenticated redirect URI). Without tenant context encoded in the PKCE state token, credentials are always saved to the `local` tenant. In multi-tenant cloud mode, this would silently assign provider credentials to the wrong tenant.

### A4 · Positive Security — Design Decisions Worth Recognising

1. **Raw proxy keys never stored** — all keys are SHA-256 hashed; raw keys shown once at creation.
2. **`secrets.compare_digest` for timing-safe comparison** — correctly used in the fallback auth path.
3. **AES-256-GCM with random 12-byte nonce** — industry-standard authenticated encryption with correct nonce hygiene.
4. **HKDF for key derivation** — correct KDF choice; context-specific `info` prevents cross-purpose key reuse.
5. **PKCE intent is correct** — proper S256 code challenge; the implementation flaw (SEC-02) is tactical, not architectural.
6. **`Authorization` header redacted in debug logs** — correctly implemented in `_log_request`.
7. **Startup key auto-generation** — `_load_or_generate_proxy_key()` handles first-run gracefully.
8. **Storage parity test suite** — `test_file_storage_schema_parity.py` verifies File ↔ SQL interchangeability; excellent engineering discipline.

---

## 5. Test Coverage Gaps

The `test_file_storage_schema_parity.py` suite is well-structured and covers:

- Schema parity between file and SQL engines ✅
- CRUD lifecycle for all entities ✅
- End-to-end proxy key auth in both engine modes ✅

**Missing coverage**:

- `auth.py` — No tests for `require_oidc_jwt_user` with a real JWKS-signed token
- `routes/system.py` — PKCE authorize/callback flow entirely untested
- `crypto.py` — No tests for decryption failure, truncated payload, or wrong-key error paths
- `config.py` — The `get_default_db_url()` bug (SEC-01) would have been caught by a unit test asserting the returned URL when `PGHOST` is set

---

## 6. Prioritised Action List

| Priority | ID | Summary |
|---|---|---|
| 🔴 P0 | SEC-01 | Fix `get_default_db_url()` — always returns SQLite even when PG env vars are set |
| 🔴 P0 | SEC-02 | Remove PKCE state-mismatch fallback; reject on invalid state |
| 🔴 P0 | SEC-03 | Remove hard-coded `ENCRYPTION_MASTER_KEY` default; fail-fast in cloud/SQL mode |
| 🟠 P1 | SEC-05 | Suppress raw JWT exception detail from HTTP 401 response |
| 🟠 P1 | SEC-07 | Remove `HS256` from OIDC decode algorithm list |
| 🟠 P1 | SEC-06 | Distinguish storage failure from key-not-found in auth fallback |
| 🟠 P1 | ENG-09 | Use context manager for session in `RelationalApiKeyStorage.__init__` |
| 🟠 P1 | ENG-12 | Remove `_get_active_provider_config`; resolve settings with tenant_id per-request |
| 🟠 P1 | A3 | Encode tenant_id in PKCE state token for multi-tenant correctness |
| 🟡 P2 | SEC-08 | Enable OIDC audience verification once `OIDC_AUDIENCE` is configured |
| 🟡 P2 | ENG-03 | Consolidate `hash_key` into `core/crypto.py` |
| 🟡 P2 | ENG-05 | Extract triplicated trigger logic to `_compute_trigger_fired` helper *(⏳ deferred — apply during composer-pattern refactor)* |
| 🟡 P2 | ENG-11 | Redact message bodies from debug payload logs |
| 🟢 P3 | ENG-04 | Deprecate and remove `SessionStateStore` wrapper class |
| 🟢 P3 | ENG-07 | Use `Path` API consistently for `_STATIC_INDEX` |
| 🟢 P3 | ENG-10 | Remove empty alias subclasses (`PostgresSettingsStorage`, `PostgresSessionStorage`) — PostgreSQL parity confirmed fully working |
| 🟢 P3 | SEC-09 | Cache `SandboxEngine` as singleton instead of per-request instantiation |

---

*Review conducted on RACHEL source as of 2026-07-25. Next review recommended after SEC-01/02/03 remediations are merged and verified by the test suite.*
