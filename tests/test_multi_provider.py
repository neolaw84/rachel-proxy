"""Unit tests for Multi-Provider endpoints, CORS, and PKCE OAuth flow."""

import asyncio
import pytest
from fastapi.testclient import TestClient


from rachel.auth import PROXY_API_KEY
from rachel.proxy import app
from rachel.core.settings_storage import get_settings_storage

client = TestClient(app)
AUTH_HEADERS = {"Authorization": f"Bearer {PROXY_API_KEY}"}


def test_cors_headers():
    # JanitorAI origin
    res = client.options(
        "/v1/chat/completions",
        headers={"Origin": "https://janitorai.com", "Access-Control-Request-Method": "POST"}
    )
    assert res.headers.get("access-control-allow-origin") == "https://janitorai.com"

    # Wyvern origin
    res_wyvern = client.options(
        "/v1/chat/completions",
        headers={"Origin": "https://app.wyvern.chat", "Access-Control-Request-Method": "POST"}
    )
    assert res_wyvern.headers.get("access-control-allow-origin") == "https://app.wyvern.chat"

    # JessicaAI origin
    res_jessica = client.options(
        "/v1/chat/completions",
        headers={"Origin": "https://jessicaai.online", "Access-Control-Request-Method": "POST"}
    )
    assert res_jessica.headers.get("access-control-allow-origin") == "https://jessicaai.online"

    # Localhost origin
    res_local = client.options(
        "/v1/chat/completions",
        headers={"Origin": "http://localhost:3000", "Access-Control-Request-Method": "POST"}
    )
    assert res_local.headers.get("access-control-allow-origin") == "http://localhost:3000"

    # Disallowed origin
    res_other = client.options(
        "/v1/chat/completions",
        headers={"Origin": "https://untrusted-domain.com", "Access-Control-Request-Method": "POST"}
    )
    assert res_other.headers.get("access-control-allow-origin") is None


def test_provider_management_endpoints(tmp_path, monkeypatch):
    from rachel.core import settings_storage
    storage = settings_storage.FileSettingsStorage(tenant_id="local", storage_dir=str(tmp_path))
    monkeypatch.setattr("rachel.routes.system.get_settings_storage", lambda *a, **kw: storage)
    monkeypatch.setattr("rachel.routes.completions.get_settings_storage", lambda *a, **kw: storage)

    # List providers
    res = client.get("/v1/providers", headers=AUTH_HEADERS)
    assert res.status_code == 200
    data = res.json()
    assert data["active_provider"] == "openrouter_byok"
    assert "openrouter_byok" in data["providers"]

    # Set credentials
    res_cred = client.post(
        "/v1/providers/credentials",
        headers=AUTH_HEADERS,
        json={"provider": "deepseek_byok", "api_key": "sk-deepseek-test"}
    )
    assert res_cred.status_code == 200

    # Set active provider
    res_active = client.post(
        "/v1/providers/active",
        headers=AUTH_HEADERS,
        json={"provider": "deepseek_byok"}
    )
    assert res_active.status_code == 200
    assert res_active.json()["active_provider"] == "deepseek_byok"

    # Verify status
    status_res = client.get("/v1/status", headers=AUTH_HEADERS)
    assert status_res.status_code == 200
    status_data = status_res.json()
    assert status_data["active_provider"] == "deepseek_byok"
    assert status_data["provider_key_set"] is True

    # Test localhost_byok in providers
    assert "localhost_byok" in data["providers"]
    assert "localhost:11434" in data["providers"]["localhost_byok"]["base_url"]
    assert data["providers"]["localhost_byok"]["default_model"] == "llama3.2"
    assert data["localhost_key_not_needed"] is True

    # Toggle localhost-key-not-needed endpoint
    toggle_res = client.post(
        "/v1/providers/localhost-key-not-needed",
        headers=AUTH_HEADERS,
        json={"enabled": False},
    )
    assert toggle_res.status_code == 200
    assert toggle_res.json()["localhost_key_not_needed"] is False
    assert storage.get_localhost_key_not_needed() is False

    # Switch active provider to localhost_byok with key_not_needed=False and no key
    client.post("/v1/providers/active", headers=AUTH_HEADERS, json={"provider": "localhost_byok"})
    status_res2 = client.get("/v1/status", headers=AUTH_HEADERS)
    assert status_res2.json()["active_provider"] == "localhost_byok"
    assert status_res2.json()["provider_key_set"] is False

    # Toggle localhost-key-not-needed back to True
    toggle_res2 = client.post(
        "/v1/providers/localhost-key-not-needed",
        headers=AUTH_HEADERS,
        json={"enabled": True},
    )
    assert toggle_res2.status_code == 200
    assert toggle_res2.json()["localhost_key_not_needed"] is True
    status_res3 = client.get("/v1/status", headers=AUTH_HEADERS)
    assert status_res3.json()["provider_key_set"] is True


def test_localhost_byok_completion_dispatch_behavior(tmp_path, monkeypatch):
    """Test localhost_byok completion dispatch behavior under toggle ON, toggle OFF, and explicit key."""
    from unittest.mock import AsyncMock, patch
    from rachel.core import settings_storage

    storage = settings_storage.FileSettingsStorage(tenant_id="local", storage_dir=str(tmp_path))
    storage.set_active_provider("localhost_byok")
    monkeypatch.setattr("rachel.routes.system.get_settings_storage", lambda *a, **kw: storage)
    monkeypatch.setattr("rachel.routes.completions.get_settings_storage", lambda *a, **kw: storage)

    mock_agent_result = {
        "content": "Local response",
        "reasoning_content": "",
        "after_state": {},
    }

    # 1. Toggle ON + No key -> should succeed using dummy key 'not-needed'
    storage.set_localhost_key_not_needed(True)
    with patch("rachel.routes.completions.run_agent", new_callable=AsyncMock) as mock_agent:
        mock_agent.return_value = mock_agent_result
        res = client.post(
            "/v1/chat/completions",
            headers=AUTH_HEADERS,
            json={"messages": [{"role": "user", "content": "hello local"}]},
        )
        assert res.status_code == 200
        mock_agent.assert_called_once()
        call_kwargs = mock_agent.call_args.kwargs
        assert call_kwargs["api_key"] == "not-needed"
        assert "localhost:11434" in call_kwargs["base_url"]
        assert call_kwargs["model"] == "llama3.2"

    # 2. Toggle OFF + No key -> should return RACHEL HTTP 400 pre-flight error
    storage.set_localhost_key_not_needed(False)
    with patch("rachel.routes.completions.run_agent", new_callable=AsyncMock) as mock_agent:
        res = client.post(
            "/v1/chat/completions",
            headers=AUTH_HEADERS,
            json={"messages": [{"role": "user", "content": "hello local"}]},
        )
        assert res.status_code == 400
        assert "No API key configured for active provider 'localhost_byok'" in res.json()["detail"]
        mock_agent.assert_not_called()

    # 3. Toggle OFF + User explicitly entered a key -> should succeed using configured key
    storage.set_credential("localhost_byok", "sk-custom-vllm-key")
    with patch("rachel.routes.completions.run_agent", new_callable=AsyncMock) as mock_agent:
        mock_agent.return_value = mock_agent_result
        res = client.post(
            "/v1/chat/completions",
            headers=AUTH_HEADERS,
            json={"messages": [{"role": "user", "content": "hello local"}]},
        )
        assert res.status_code == 200
        mock_agent.assert_called_once()
        assert mock_agent.call_args.kwargs["api_key"] == "sk-custom-vllm-key"

    # 4. Toggle OFF + User explicitly entered string 'not-needed' -> should succeed using 'not-needed'
    storage.set_credential("localhost_byok", "not-needed")
    with patch("rachel.routes.completions.run_agent", new_callable=AsyncMock) as mock_agent:
        mock_agent.return_value = mock_agent_result
        res = client.post(
            "/v1/chat/completions",
            headers=AUTH_HEADERS,
            json={"messages": [{"role": "user", "content": "hello local"}]},
        )
        assert res.status_code == 200
        mock_agent.assert_called_once()
        assert mock_agent.call_args.kwargs["api_key"] == "not-needed"

    # 5. Custom Localhost Base URL endpoint and dispatch
    # Invalid URL format
    res_bad = client.post(
        "/v1/providers/localhost-base-url",
        headers=AUTH_HEADERS,
        json={"base_url": "ftp://not-http"},
    )
    assert res_bad.status_code == 400

    # Set custom LM Studio URL
    res_url = client.post(
        "/v1/providers/localhost-base-url",
        headers=AUTH_HEADERS,
        json={"base_url": "http://localhost:1234/v1/chat/completions"},
    )
    assert res_url.status_code == 200
    assert res_url.json()["localhost_base_url"] == "http://localhost:1234/v1/chat/completions"
    assert storage.get_localhost_base_url() == "http://localhost:1234/v1/chat/completions"

    # Verify provider list reflects custom base URL
    prov_res = client.get("/v1/providers", headers=AUTH_HEADERS)
    assert prov_res.json()["providers"]["localhost_byok"]["base_url"] == "http://localhost:1234/v1/chat/completions"

    # Dispatch uses custom URL
    with patch("rachel.routes.completions.run_agent", new_callable=AsyncMock) as mock_agent:
        mock_agent.return_value = mock_agent_result
        res = client.post(
            "/v1/chat/completions",
            headers=AUTH_HEADERS,
            json={"messages": [{"role": "user", "content": "hello lm studio"}]},
        )
        assert res.status_code == 200
        assert mock_agent.call_args.kwargs["base_url"] == "http://localhost:1234/v1/chat/completions"

    # Reset URL
    res_reset = client.post(
        "/v1/providers/localhost-base-url",
        headers=AUTH_HEADERS,
        json={"base_url": None},
    )
    assert res_reset.status_code == 200
    assert res_reset.json()["localhost_base_url"] is None
    assert storage.get_localhost_base_url() is None


def test_openrouter_pkce_authorize_route():
    res = client.get("/v1/auth/openrouter/authorize", follow_redirects=False)
    assert res.status_code == 307
    location = res.headers.get("location")
    assert "openrouter.ai/auth" in location
    assert "code_challenge=" in location
    assert "code_challenge_method=S256" in location


def test_format_provider_session_id_and_caching_info():
    from rachel.core.session import format_provider_session_id, get_session_caching_info

    # Standard clean session ID
    sid = "my-session_123"
    assert format_provider_session_id(sid) == "my-session_123"

    # Dirty / special characters session ID
    dirty_sid = "my session!@#$with spaces"
    assert format_provider_session_id(dirty_sid) == "my_session____with_spaces"

    # Overly long session ID (truncated to 256 chars)
    long_sid = "a" * 300
    assert len(format_provider_session_id(long_sid)) == 256

    # get_session_caching_info
    info = get_session_caching_info("user-sess-456")
    assert info["session_id"] == "user-sess-456"
    assert info["prompt_cache_key"] == "user-sess-456"
    assert info["user"] == "user-user-sess-456"


@pytest.mark.asyncio
async def test_call_llm_streaming_session_caching_parameters():
    from unittest.mock import patch
    from rachel.agent.openrouter import call_llm_streaming

    captured_requests = []
    stream_queue = asyncio.Queue()

    class DummyStreamResponse:
        def __init__(self):
            self.status_code = 200

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def aiter_lines(self):
            yield 'data: {"choices":[{"delta":{"content":"hello"}}]}'
            yield 'data: [DONE]'

    def mock_stream(method, url, json=None, headers=None, **kwargs):
        captured_requests.append({"json": json, "headers": headers})
        return DummyStreamResponse()

    with patch("httpx.AsyncClient.stream", side_effect=mock_stream):
        await call_llm_streaming(
            api_key="test_key",
            base_url="https://api.openrouter.ai/v1/chat/completions",
            model="gpt-4o",
            openai_messages=[{"role": "user", "content": "hi"}],
            stream_queue=stream_queue,
            session_id="test-session-xyz",
        )

    assert len(captured_requests) == 1
    req = captured_requests[0]
    assert req["headers"]["X-Session-Id"] == "test-session-xyz"
    assert req["json"]["session_id"] == "test-session-xyz"
    assert req["json"]["prompt_cache_key"] == "test-session-xyz"
    assert req["json"]["user"] == "user-test-session-xyz"


@pytest.mark.asyncio
async def test_call_llm_direct_session_caching_parameters():
    from unittest.mock import patch
    from rachel.agent.openrouter import call_llm_direct

    captured_requests = []

    class DummyResponse:
        def __init__(self):
            self.status_code = 200

        def json(self):
            return {"choices": [{"message": {"content": "direct reply"}}]}

    async def mock_post(url, json=None, headers=None, **kwargs):
        captured_requests.append({"json": json, "headers": headers})
        return DummyResponse()

    with patch("httpx.AsyncClient.post", side_effect=mock_post):
        res = await call_llm_direct(
            api_key="test_key",
            base_url="https://api.openrouter.ai/v1/chat/completions",
            model="gpt-4o",
            openai_messages=[{"role": "user", "content": "hi"}],
            session_id="direct-sess-999",
        )
        assert res == "direct reply"

    assert len(captured_requests) == 1
    req = captured_requests[0]
    assert req["headers"]["X-Session-Id"] == "direct-sess-999"
    assert req["json"]["session_id"] == "direct-sess-999"
    assert req["json"]["prompt_cache_key"] == "direct-sess-999"
    assert req["json"]["user"] == "user-direct-sess-999"


@pytest.mark.asyncio
async def test_run_agent_session_info_persistence():
    from unittest.mock import patch
    from rachel.agent.graph import run_agent

    stream_queue = asyncio.Queue()

    class DummyStreamResponse:
        def __init__(self):
            self.status_code = 200

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def aiter_lines(self):
            yield 'data: {"choices":[{"delta":{"content":"agent response"}}]}'
            yield 'data: [DONE]'

    class MockPostResponse:
        def __init__(self, status_code=200):
            self.status_code = status_code
            self.text = "{}"
        def json(self):
            return {"choices": [{"message": {"content": "ok"}}]}

    with patch("httpx.AsyncClient.stream", side_effect=lambda *a, **kw: DummyStreamResponse()), \
         patch("httpx.AsyncClient.post", return_value=MockPostResponse()):
        res = await run_agent(
            messages=[{"role": "user", "content": "hello"}],
            before_state={},
            api_key="test_key",
            base_url="https://api.openrouter.ai/v1/chat/completions",
            model="gpt-4o",
            stream_queue=stream_queue,
            session_id="persistent-session-42",
        )

    assert res["content"] == "agent response"
    session_info = res["after_state"]["hidden_state"]["session_info"]
    assert session_info["session_id"] == "persistent-session-42"
    assert session_info["prompt_cache_key"] == "persistent-session-42"
    assert session_info["user"] == "user-persistent-session-42"


