---
title: RACHEL (rachel-proxy)
emoji: 🎲
colorFrom: red
colorTo: blue
sdk: docker
app_port: 7860
pinned: false
---

# RACHEL (rachel-proxy)

**RACHEL** (**R**pg **A**gent **CH**at **E**valuation **L**oop) is a FastAPI proxy that sits between JanitorAI (or any OpenAI-compatible client) and LLM completion providers (OpenRouter, OpenAI, Google Gemini, DeepSeek), running request payloads through a stateful LangGraph agent with a secure V8 code sandbox containing dice and contest RNG helper functions.

* [Why Use RACHEL?](docs/why-rachel.md) — Core features, benefits, assumptions, and design philosophies.
* [All About Sessions](docs/all-about-sessions.md) — How session IDs are resolved and managed via API endpoints.
* [Road to Multi-Tenant](docs/road-to-multi-tenant.md) — Multi-tenant cloud roadmap and architecture.

---

## 🚀 Quickstarts

RACHEL is deployed as a single-tenant desktop application.

### 🖥️ One-Click Desktop Launchers
Download the release zip for your operating system from [Releases](../../releases) and launch with one click:
- **Windows**: Unzip and double-click `launch.bat`.
- **macOS**: Unzip and double-click `launch.command`. (If blocked by Gatekeeper, run `xattr -cr launch.command` in Terminal).
- **Linux**: Unzip and double-click `launch.sh`.

---

## 💻 Developer Setup

If you are cloning this repository for local development:

1. **Install Python dependencies**:
   ```bash
   pip install -e ".[dev]"
   ```
2. **Build Frontend Assets (Required)**:
   The compiled static frontend directory (`src/rachel/static/`) is git-ignored. You MUST build the frontend before launching the backend server:
   ```bash
   python scripts/build_frontend.py --target local
   ```
3. **Run the Server**:
   ```bash
   uvicorn rachel.proxy:app --reload --host 0.0.0.0 --port 8000
   ```
4. **Run Tests with Coverage**:
   Ensure your code changes pass all tests and maintain at least 75% coverage:
   ```bash
   pytest --cov=src --cov-fail-under=75
   ```

---
---

## Initial Setup & LLM Provider Credentials

Once the proxy starts, open the Admin Console in your browser at `http://localhost:8000`:

1. **Proxy API Key**: Enter the local admin key (printed to console logs or saved in `data/proxy.key`).
2. **Provider Credentials**: Configure your preferred provider (**OpenRouter BYOK / PKCE**, **OpenAI**, **Google Gemini**, or **DeepSeek**) directly in the **Provider Credentials** card.
3. Select your **Active Provider** and save settings.



