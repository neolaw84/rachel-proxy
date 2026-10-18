"""Tests for Plan/Summary/Cleanup model configuration priority and overrides."""

import pytest
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient

from rachel.auth import PROXY_API_KEY
from rachel.proxy import app

client = TestClient(app)
AUTH_HEADERS = {"Authorization": f"Bearer {PROXY_API_KEY}"}


@pytest.mark.asyncio
async def test_end_to_end_orchestration_model_priority_openrouter(tmp_path, monkeypatch):
    """Test priority with OpenRouter provider:
    1. Config exists -> overwrites client model.
    2. Config empty -> uses client model.
    3. Config empty and client model omitted -> fallback to deepseek/deepseek-v4.1-flash.
    4. Progress mode is untouched.
    """
    from rachel.core import settings_storage
    storage = settings_storage.FileSettingsStorage(tenant_id="local", storage_dir=str(tmp_path))
    monkeypatch.setattr("rachel.routes.system.get_settings_storage", lambda tenant_id="local": storage)
    monkeypatch.setattr("rachel.routes.completions.get_settings_storage", lambda tenant_id="local": storage)

    storage.set_active_provider("openrouter_byok")
    storage.set_credential("openrouter_byok", "sk-or-test-key")

    mock_agent_result = {
        "content": "Assistant test reply",
        "after_state": {
            "state": {},
            "hidden_state": {},
            "plan": [],
            "summary": "",
            "notes": [],
        },
        "reasoning": "",
        "iteration_count": 1,
        "logs": [],
        "last_plan_turn": 0,
        "last_summary_turn": 0,
        "last_cleanup_turn": 0,
    }

    # Case 1: Config is empty (default), user defines model
    with patch("rachel.routes.completions.run_agent", new_callable=AsyncMock) as mock_agent:
        mock_agent.return_value = mock_agent_result
        res = client.post(
            "/v1/chat/completions",
            headers=AUTH_HEADERS,
            json={
                "model": "anthropic/claude-3.5-sonnet",
                "messages": [{"role": "user", "content": "hello"}]
            },
        )
        assert res.status_code == 200
        mock_agent.assert_called_once()
        kwargs = mock_agent.call_args.kwargs
        # Progress mode gets the client model
        assert kwargs["model"] == "anthropic/claude-3.5-sonnet"
        assert kwargs["client_model"] == "anthropic/claude-3.5-sonnet"
        # Fallback model for OpenRouter is deepseek v4.1 flash
        assert kwargs["fallback_orchestration_model"] == "deepseek/deepseek-v4.1-flash"

    # Case 2: Config is empty (default), user DOES NOT define model
    with patch("rachel.routes.completions.run_agent", new_callable=AsyncMock) as mock_agent:
        mock_agent.return_value = mock_agent_result
        res = client.post(
            "/v1/chat/completions",
            headers=AUTH_HEADERS,
            json={
                "messages": [{"role": "user", "content": "hello"}]
            },
        )
        assert res.status_code == 200
        mock_agent.assert_called_once()
        kwargs = mock_agent.call_args.kwargs
        # Progress mode falls back to default model (e.g. google/gemini-3.5-flash) - NO change to progress mode!
        assert kwargs["model"] == "google/gemini-3.5-flash"
        assert kwargs["client_model"] is None
        # Orchestration fallback for OpenRouter is deepseek v4.1 flash
        assert kwargs["fallback_orchestration_model"] == "deepseek/deepseek-v4.1-flash"


@pytest.mark.asyncio
async def test_end_to_end_orchestration_model_priority_openai(tmp_path, monkeypatch):
    """Test priority with OpenAI provider:
    When client model is omitted, fallback orchestration model is low-cost model in OpenAI (gpt-4o-mini).
    """
    from rachel.core import settings_storage
    storage = settings_storage.FileSettingsStorage(tenant_id="local", storage_dir=str(tmp_path))
    monkeypatch.setattr("rachel.routes.system.get_settings_storage", lambda tenant_id="local": storage)
    monkeypatch.setattr("rachel.routes.completions.get_settings_storage", lambda tenant_id="local": storage)

    storage.set_active_provider("openai_byok")
    storage.set_credential("openai_byok", "sk-openai-key")

    mock_agent_result = {
        "content": "Assistant test reply",
        "after_state": {
            "state": {},
            "hidden_state": {},
            "plan": [],
            "summary": "",
            "notes": [],
        },
        "reasoning": "",
        "iteration_count": 1,
        "logs": [],
        "last_plan_turn": 0,
        "last_summary_turn": 0,
        "last_cleanup_turn": 0,
    }

    # Case: Client model omitted
    with patch("rachel.routes.completions.run_agent", new_callable=AsyncMock) as mock_agent:
        mock_agent.return_value = mock_agent_result
        res = client.post(
            "/v1/chat/completions",
            headers=AUTH_HEADERS,
            json={
                "messages": [{"role": "user", "content": "hello openai"}]
            },
        )
        assert res.status_code == 200
        mock_agent.assert_called_once()
        kwargs = mock_agent.call_args.kwargs
        assert kwargs["model"] == "gpt-4o-mini"
        assert kwargs["client_model"] is None
        # Fallback orchestration model for OpenAI defaults to low-cost gpt-4o-mini
        assert kwargs["fallback_orchestration_model"] == "gpt-4o-mini"


@pytest.mark.asyncio
async def test_pre_action_node_independent_config_overwrites():
    """Verify that plan, summary, and cleanup nodes independently check their config,
    overwriting the user request model when config exists, or falling back when empty.
    """
    from langchain_core.messages import AIMessage, HumanMessage
    from langchain_core.runnables import RunnableConfig
    from rachel.agent.nodes import _build_pre_action_node

    state_container = {
        "rpg_state": {
            "state": {"x": 1},
            "hidden_state": {},
            "plan": [],
            "summary": "Existing summary",
            "notes": [],
        },
        "last_plan_turn": 0,
        "last_summary_turn": 0,
        "last_cleanup_turn": 0,
    }
    state = {
        "messages": [
            HumanMessage(content="Turn 1 User"),
            AIMessage(content="Turn 1 Asst"),
            HumanMessage(content="Turn 2 User"),
            AIMessage(content="Turn 2 Asst"),
        ]
    }
    config = RunnableConfig(configurable={
        "plan_fired": True,
        "summary_fired": True,
        "cleanup_fired": True,
    })

    # Scenario:
    # - PLAN_MODEL is explicitly set in config to "plan-model-override"
    # - SUMMARY_MODEL is None (default empty) -> should use client model "user-client-model"
    # - CLEANUP_MODEL is explicitly set in config to "cleanup-model-override"
    with patch("rachel.config.PLAN_MODEL", "plan-model-override"), \
         patch("rachel.config.SUMMARY_MODEL", None), \
         patch("rachel.config.CLEANUP_MODEL", "cleanup-model-override"), \
         patch("rachel.agent.nodes._GraphDelegate.call_openrouter_direct") as mock_direct:

        async def fake_direct(*args, **kwargs):
            tool_choice = kwargs.get("tool_choice")
            if tool_choice and isinstance(tool_choice, dict) and tool_choice.get("function", {}).get("name") == "submit_summary":
                return ("Summary updated", [])
            tools = kwargs.get("tools")
            if not tools:
                return "state.x = 2;"
            return '[{"id": 1, "description": "task", "status": "to-do", "remark": ""}]'

        mock_direct.side_effect = fake_direct

        node_fn = _build_pre_action_node(
            api_key="fake-key",
            state_container=state_container,
            sandbox_timeout=2.0,
            base_url="https://fake-url",
            model="user-client-model",
            fallback_model="deepseek/deepseek-v4.1-flash",
        )

        await node_fn(state, config)

        assert mock_direct.call_count == 3
        calls = mock_direct.call_args_list

        # Verify models called:
        called_models = {c.kwargs["model"] for c in calls}
        assert "plan-model-override" in called_models       # Overwrote user-client-model!
        assert "user-client-model" in called_models         # Used user-client-model because config was empty!
        assert "cleanup-model-override" in called_models    # Overwrote user-client-model!
