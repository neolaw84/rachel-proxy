"""Unit tests verifying Plan and Cleanup validation and retry loops."""

import pytest
import json
from unittest.mock import AsyncMock, patch
from langchain_core.runnables import RunnableConfig
from langchain_core.messages import AIMessage, HumanMessage

from rachel.agent.nodes import _build_plan_node, _build_cleanup_node
from rachel.sandbox.validation import validate_state_constraints

@pytest.mark.asyncio
@patch("rachel.agent.nodes._GraphDelegate.call_openrouter_direct")
async def test_plan_node_retry_invalid_json_then_success(mock_call):
    """Verify that the plan node retries when the first response is invalid JSON, then succeeds."""
    mock_call.side_effect = [
        "This is not a JSON response, just conversational garbage.",
        '[{"id": 1, "description": "Conquer the dungeon", "status": "in-progress", "remark": "Careful!"}]'
    ]

    rpg_state = {
        "state": {},
        "hidden_state": {},
        "plan": [{"id": 1, "description": "Old Goal", "status": "to-do", "remark": ""}],
        "summary": "Old Summary",
    }
    state_container = {"rpg_state": rpg_state}
    plan_node = _build_plan_node(api_key="fake_key", state_container=state_container)

    state = {"messages": [HumanMessage(content="Hello"), AIMessage(content="Hi")]}
    config = RunnableConfig(configurable={"session_id": "test_session"})

    # Run plan node
    res = await plan_node(state, config)

    # Asserts
    assert mock_call.call_count == 2
    assert state_container["rpg_state"]["plan"] == [
        {"id": 1, "description": "Conquer the dungeon", "status": "in-progress", "remark": "Careful!"}
    ]


@pytest.mark.asyncio
@patch("rachel.agent.nodes._GraphDelegate.call_openrouter_direct")
async def test_plan_node_retry_validation_fail_then_success(mock_call):
    """Verify that the plan node retries when description length constraint is violated, then succeeds."""
    too_long_description = "A" * 600
    mock_call.side_effect = [
        # First call: description is too long (exceeds 500 characters)
        f'[{{"id": 1, "description": "{too_long_description}", "status": "to-do", "remark": ""}}]',
        # Second call: valid length
        '[{"id": 1, "description": "Short description", "status": "to-do", "remark": ""}]'
    ]

    rpg_state = {
        "state": {},
        "hidden_state": {},
        "plan": [],
        "summary": "",
    }
    state_container = {"rpg_state": rpg_state}
    plan_node = _build_plan_node(api_key="fake_key", state_container=state_container)

    state = {"messages": [HumanMessage(content="Hello")]}
    config = RunnableConfig(configurable={})

    res = await plan_node(state, config)

    assert mock_call.call_count == 2
    assert len(state_container["rpg_state"]["plan"]) == 1
    assert state_container["rpg_state"]["plan"][0]["description"] == "Short description"


@pytest.mark.asyncio
@patch("rachel.agent.nodes._GraphDelegate.call_openrouter_direct")
async def test_plan_node_exhausts_retries(mock_call):
    """Verify that when all plan retries are exhausted, the previous plan is preserved."""
    mock_call.side_effect = [
        "Bad JSON 1",
        "Bad JSON 2",
        "Bad JSON 3",
        "Bad JSON 4",
    ]

    old_plan = [{"id": 1, "description": "Preserved Goal", "status": "to-do", "remark": ""}]
    rpg_state = {
        "state": {},
        "hidden_state": {},
        "plan": list(old_plan),
        "summary": "",
    }
    state_container = {"rpg_state": rpg_state}
    plan_node = _build_plan_node(api_key="fake_key", state_container=state_container)

    state = {"messages": [HumanMessage(content="Hello")]}
    config = RunnableConfig(configurable={})

    res = await plan_node(state, config)

    # PLAN_MAX_RETRIES defaults to 3
    assert mock_call.call_count == 3
    assert state_container["rpg_state"]["plan"] == old_plan


@pytest.mark.asyncio
@patch("rachel.agent.nodes._GraphDelegate.call_openrouter_direct")
async def test_cleanup_node_retry_syntax_error_then_success(mock_call):
    """Verify that cleanup node retries when the sandbox execution encounters syntax errors, then succeeds."""
    mock_call.side_effect = [
        # Syntax error: missing quote or bracket
        "delete state.temp_var = {;",
        # Successful clean code snippet
        "delete state.temp_var;"
    ]

    rpg_state = {
        "state": {"temp_var": "temporary_data", "permanent_var": "save_this"},
        "hidden_state": {},
        "plan": [],
        "summary": "",
    }
    state_container = {"rpg_state": rpg_state}
    cleanup_node = _build_cleanup_node(api_key="fake_key", state_container=state_container, sandbox_timeout=2.0)

    state = {"messages": [HumanMessage(content="Hello")]}
    config = RunnableConfig(configurable={})

    res = await cleanup_node(state, config)

    assert mock_call.call_count == 2
    assert "temp_var" not in state_container["rpg_state"]["state"]
    assert state_container["rpg_state"]["state"]["permanent_var"] == "save_this"


@pytest.mark.asyncio
@patch("rachel.agent.nodes._GraphDelegate.call_openrouter_direct")
async def test_cleanup_node_retry_validation_fail_then_success(mock_call):
    """Verify that cleanup node retries when state limits are exceeded, then succeeds."""
    too_long_str = "x" * 200 # config.yaml limit is 128 (max_string_length: 128)
    mock_call.side_effect = [
        # First call: code attempts to create a string too long, violating constraints
        f"state.temp_var = '{too_long_str}';",
        # Second call: code performs correct pruning
        "delete state.temp_var;"
    ]

    rpg_state = {
        "state": {"temp_var": "old_val", "permanent_var": "save_this"},
        "hidden_state": {},
        "plan": [],
        "summary": "",
    }
    state_container = {"rpg_state": rpg_state}
    cleanup_node = _build_cleanup_node(api_key="fake_key", state_container=state_container, sandbox_timeout=2.0)

    state = {"messages": [HumanMessage(content="Hello")]}
    config = RunnableConfig(configurable={})

    res = await cleanup_node(state, config)

    assert mock_call.call_count == 2
    assert "temp_var" not in state_container["rpg_state"]["state"]
    assert state_container["rpg_state"]["state"]["permanent_var"] == "save_this"


@pytest.mark.asyncio
@patch("rachel.agent.nodes._GraphDelegate.call_openrouter_direct")
async def test_cleanup_node_exhausts_retries(mock_call):
    """Verify that when cleanup retries are exhausted, the previous state is cleanly restored."""
    mock_call.side_effect = [
        "state.temp_var = 'bad_state_attempt_1'; throw new Error('Simulated Error 1');",
        "state.temp_var = 'bad_state_attempt_2'; throw new Error('Simulated Error 2');",
        "state.temp_var = 'bad_state_attempt_3'; throw new Error('Simulated Error 3');",
    ]

    original_state = {"temp_var": "original_val", "permanent_var": "save_this"}
    rpg_state = {
        "state": dict(original_state),
        "hidden_state": {},
        "plan": [],
        "summary": "",
    }
    state_container = {"rpg_state": rpg_state}
    cleanup_node = _build_cleanup_node(api_key="fake_key", state_container=state_container, sandbox_timeout=2.0)

    state = {"messages": [HumanMessage(content="Hello")]}
    config = RunnableConfig(configurable={})

    res = await cleanup_node(state, config)

    # CLEANUP_MAX_RETRIES defaults to 3
    assert mock_call.call_count == 3
    assert state_container["rpg_state"]["state"] == original_state
