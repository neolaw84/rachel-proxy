# Brainstorming Session: RACHEL as an Android App

## 1. Overview & Objectives

This document evaluates the architectural feasibility, technical strategies, challenges, and implementation roadmap for packaging **RACHEL (`rachel-proxy`)** into an Android application.

### Key Context & Constraints
* **Frontend**: Implemented in lightweight **Vanilla JavaScript**, CSS, and HTML (SPA served by FastAPI).
* **Backend**: Implemented in **Python >= 3.12** using **FastAPI**, **Uvicorn**, **LangGraph**, and **LangChain**.
* **Sandbox Execution**: Currently relies on `py-mini-racer` (embedded Google V8 C++ isolates) and Python `multiprocessing.Process` to execute RPG dice rolls, contests, and state mutations safely.

---

## 2. Target User Scenarios & Mobile Topologies

When bringing RACHEL to mobile, there are three primary deployment paradigms:

```
+---------------------------------------------------------------------------------------------------------+
|                                        PARADIGMS FOR ANDROID                                            |
+---------------------------------------------------------------------------------------------------------+
|  [Paradigm 1: Standalone On-Device APK]    [Paradigm 2: Client-Server Companion]   [Paradigm 3: Port]  |
|  - Embedded Python Backend (Chaquopy/p4a)  - Remote Rachel Server (Cloud/PC)       - LangGraph.js /    |
|  - Android WebView / QuickJS Sandbox       - Mobile Web / Native UI on Android       Kotlin Native     |
|  - Runs 100% on phone, serves localhost    - Thin client connecting to proxy API   - Zero Python       |
+---------------------------------------------------------------------------------------------------------+
```

1. **Paradigm 1: Standalone On-Device App (Zero-Cloud / Local Loopback)**
   * **Goal**: Install an `.apk` directly on Android. The phone runs the embedded Python proxy on `http://127.0.0.1:8000`.
   * **Use Case**: Mobile browser (JanitorAI / SillyTavern) or on-device apps connect to `http://127.0.0.1:8000/v1/chat/completions` directly on the device with zero cloud server hosting costs.
2. **Paradigm 2: Mobile Companion / Web Client (Thin Client)**
   * **Goal**: RACHEL runs remotely (e.g., Cloud Run, VPS, local PC). Android app is a lightweight PWA or WebView wrapper for dashboard control and chat session management.
3. **Paradigm 3: Native Full Port (LangGraph.js / Kotlin)**
   * **Goal**: Rewrite the proxy/agent logic in TypeScript/Kotlin. High maintenance overhead and destroys codebase parity.

> **Focus**: This brainstorming session targets **Paradigm 1 (Standalone On-Device App)** to preserve maximum code reuse from the existing Python backend and Vanilla JS frontend.

---

## 3. First-Principles Layer-by-Layer Feasibility

```
+---------------------------------------------------------------------------------------+
|  FRONTEND LAYER        | Vanilla JS + CSS + HTML                                      |
|                        | -> Render directly in Android WebView / Capacitor            |
+------------------------+--------------------------------------------------------------+
|  BACKEND LAYER         | FastAPI + Uvicorn + LangGraph + LangChain                    |
|                        | -> Run via Chaquopy / Python-for-Android CPython runtime     |
+------------------------+--------------------------------------------------------------+
|  SANDBOX LAYER (HOT)   | py-mini-racer (V8) + multiprocessing.Process                 |
|                        | -> Replace with QuickJS / Android JS Engine via SandboxEngine|
+------------------------+--------------------------------------------------------------+
|  SYSTEM LIFECYCLE      | Android Foreground Service + Local Loopback (127.0.0.1:8000) |
+---------------------------------------------------------------------------------------+
```

### 3.1. Frontend Layer (Vanilla JS)
* **Status**: **100% Ready / Zero Blockers**.
* The frontend uses pure modern JavaScript (ES Modules, standard DOM APIs, CSS variables) without a complex Webpack/Node.js build dependency at runtime.
* **Packaging Approaches**:
  1. **Android Native `WebView`**: Android's `android.webkit.WebView` loads the local dashboard directly from `http://127.0.0.1:8000` once the local server boots.
  2. **Bundled Asset**: Packaged as static files inside `file:///android_asset/` and communicating via REST to `http://127.0.0.1:8000`.

### 3.2. Backend Layer (Python + FastAPI + LangGraph)
* **Status**: **Feasible with Embedded CPython**.
* Pure-Python libraries (`fastapi`, `uvicorn`, `langgraph`, `langchain-openai`, `pydantic`, `httpx`, `pyyaml`) run without modification on Android CPython runtimes.
* Binary dependencies (`cryptography`, `psycopg2-binary`, `sqlite3`):
  * Chaquopy and BeeWare maintain pre-built binary wheels for Android ABIs (`arm64-v8a`, `armeabi-v7a`, `x86_64`).

### 3.3. Sandbox Layer (`py-mini-racer` / V8) — The Core Engineering Challenge
* **The Problem**:
  1. `py-mini-racer` bundles pre-compiled desktop V8 binaries (Linux, macOS, Windows). **No pre-compiled wheels exist for Android on PyPI**. Cross-compiling Google V8 for Android via NDK produces massive binary bloat (~50MB+ per ABI).
  2. `multiprocessing.Process(spawn)`: Android's Zygote process model and SELinux sandbox restrict standard POSIX `fork`/`spawn` and IPC queues, causing `multiprocessing` to fail or crash inside APK environments.
* **The Solution**:
  * RACHEL already defines a pluggable `SandboxEngine` interface (`src/rachel/sandbox/base.py`).
  * We can implement an Android-compatible engine:
    1. **`QuickJsSandboxEngine` (Recommended)**: QuickJS is an ultra-lightweight, complete ES2020 C-based JS engine (<1MB compiled). Compiles easily for all Android NDK ABIs. Executes state mutations, dice math, and contests in <1ms.
    2. **`AndroidJSSandboxEngine` (JNI Host Bridge)**: Android OS already contains V8 inside `android.webkit.WebView`. Python can evaluate scripts through Android's `JavascriptInterface` or `evaluateJavascript` via JNI.
    3. **Thread-Based Execution**: Replace `multiprocessing.Process` with `concurrent.futures.ThreadPoolExecutor` / timer interrupts for Android platforms.

### 3.4. Android OS & Networking Lifecycle
* **Local Loopback**: Binding to `127.0.0.1:8000` is fully supported on Android. Third-party apps (or mobile Chrome running JanitorAI) can access `http://127.0.0.1:8000/v1/chat/completions`.
* **Background Keep-Alive**: Android aggressively kills background background processes to save battery.
  * **Requirement**: The Python backend must run inside an Android **`ForegroundService`** displaying an ongoing persistent notification (e.g. *"RACHEL Proxy is running on localhost:8000"*).
  * **WakeLocks & Battery Optimization**: Request exemption from battery optimization to ensure LangGraph agent iterations and SSE streams are not severed when the screen turns off.

---

## 4. Technical Strategy Comparison

| Feature / Metric | Strategy 1: Chaquopy + Android WebView | Strategy 2: Capacitor / Tauri + Python daemon | Strategy 3: PWA / Web Client | Strategy 4: Full LangGraph.js Rewrite |
| :--- | :--- | :--- | :--- | :--- |
| **Effort** | **Medium (3–5 days)** | High (1–2 weeks) | Low (< 1 day) | Very High (3–4 weeks) |
| **Code Parity** | **95% identical Python & JS** | 90% identical | 100% identical | 0% (Complete rewrite) |
| **V8 / Sandbox Solution** | **QuickJS via NDK / Python CFFI** | QuickJS / Local bridge | Existing V8 | Native JS VM |
| **Distribution Format** | **Single `.apk` (Play Store ready)** | Single `.apk` | Web URL / Add to Home | Native Mobile App |
| **Offline On-Device Proxy** | **Yes (`127.0.0.1:8000`)** | Yes | No (requires remote server) | Yes |
| **Maintenance Burden** | **Low (single shared codebase)** | Medium | Low | High (2 split codebases) |

---

## 5. Recommended Architecture: Chaquopy + Android WebView

```mermaid
graph TD
    subgraph Android App Package (.apk)
        subgraph UI Layer
            WV["Android WebView (Vanilla JS Frontend)"]
        end

        subgraph Android Native Host (Kotlin)
            MA["MainActivity.kt"]
            FS["Foreground Service (Keep-Alive)"]
        end

        subgraph Embedded CPython (Chaquopy)
            FA["FastAPI + Uvicorn (127.0.0.1:8000)"]
            LG["LangGraph RPG Agent"]
            QS["QuickJS Sandbox Engine (NDK C-Engine)"]
        end
    end

    subgraph External
        OR["OpenRouter API"]
        JAN["JanitorAI / SillyTavern (Mobile Browser)"]
    end

    WV -->|HTTP / REST| FA
    JAN -->|HTTP / 127.0.0.1:8000| FA
    MA --> FS
    FS -->|Initializes via JNI| FA
    FA --> LG
    LG --> QS
    LG -->|HTTPS| OR
```

---

## 6. Implementation Roadmap

### Phase 1: Sandbox Engine Modernization
1. **Implement `QuickJsSandboxEngine`** in `src/rachel/sandbox/quickjs_engine.py`:
   * Use lightweight C bindings (`quickjs` or `pyquickjs`) with support for the standard RACHEL JS preamble (`roll_xdy`, `contest`, `update_plan_status`, state object serialization).
   * Benchmark against `V8SandboxEngine` to verify 100% parity across test cases.
2. **Abstract Execution Worker**:
   * Support thread-based execution with strict timeout interruption for mobile platforms where `multiprocessing.Process(spawn)` is unavailable.

### Phase 2: Android Scaffolding & Chaquopy Integration
1. **Android Studio Project Setup**:
   * Create `android/` directory containing standard Kotlin Gradle project with `com.chaquo.python` plugin.
   * Configure `build.gradle.kts` to package `src/rachel` and pip dependencies.
2. **Backend Entrypoint**:
   * Create a lightweight Python bootstrap function (`rachel.android.start_server(port=8000)`) executed via Chaquopy on a background worker thread.

### Phase 3: Android UI & Service Management
1. **`ForegroundService` Implementation**:
   * Manage proxy lifecycle, wake lock, and persistent notification with "Start / Stop Proxy" actions.
2. **`MainActivity.kt` with WebView**:
   * Load `http://127.0.0.1:8000` inside standard `WebView` with Javascript enabled, file access, and local storage support.

### Phase 4: CI/CD & Packaging
1. **GitHub Actions Workflow**:
   * Add `.github/workflows/android-build.yml` to build `.apk` artifacts using Gradle and Android SDK.
   * Release unsigned debug `.apk` and signed release `.apk` alongside desktop launcher packages.

---

## 7. Risks & Mitigations

| Risk | Impact | Mitigation |
| :--- | :--- | :--- |
| **Android kills background proxy during long LLM calls** | High | Use `ForegroundService` with a sticky notification and acquire a `PartialWakeLock` during active streaming turns. |
| **QuickJS JS behavior differs slightly from V8** | Medium | QuickJS complies with ES2020 specification. Standardize JS helper code to avoid non-standard V8 syntax. Run test suite against both engines. |
| **APK file size bloat** | Low | Strip unused ABIs (target `arm64-v8a` and `x86_64` only); QuickJS adds <1MB compared to 50MB+ for V8. |
| **First-turn cold start latency on mobile** | Low | Pre-warm Python runtime and initialize LangGraph checkpointers in the background when the app launches. |
