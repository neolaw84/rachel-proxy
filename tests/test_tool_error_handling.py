"""Tests for graceful tool call failure handling and LLM re-attempt mechanism."""

import pytest
import json
from langchain_core.messages import AIMessage, ToolMessage
from rachel.agent.nodes import _build_tool_node, AgentState
from rachel.agent.tools import make_tools


@pytest.fixture
def sample_tools():
    state_container = {
        "rpg_state": {
            "state": {"location": "tavern"},
            "plan": [],
            "summary": "",
            "hidden_state": {}
        }
    }
    return make_tools(state_container, sandbox_timeout=5.0)


@pytest.mark.asyncio
async def test_tool_node_handles_pydantic_validation_error(sample_tools):
    """Test that missing required fields in a tool call return a ToolMessage error output rather than crashing."""
    tool_node = _build_tool_node(sample_tools)
    
    # update_plan_status requires an 'updates' parameter. Passing empty args dict {} causes validation error.
    ai_msg = AIMessage(
        content="",
        tool_calls=[{
            "name": "update_plan_status",
            "args": {},
            "id": "call_bad_args_1",
            "type": "tool_call"
        }]
    )
    
    state: AgentState = {
        "messages": [ai_msg],
        "rpg_state": {},
        "sandbox_timeout": 5.0,
        "iteration_count": 1
    }
    
    res = await tool_node(state, {})
    assert "messages" in res
    assert len(res["messages"]) == 1
    
    msg = res["messages"][0]
    assert isinstance(msg, ToolMessage)
    assert msg.tool_call_id == "call_bad_args_1"
    assert msg.name == "update_plan_status"
    assert "--- Tool Execution Exception ---" in msg.content
    assert "ValidationError" in msg.content or "missing" in msg.content or "Field required" in msg.content


@pytest.mark.asyncio
async def test_tool_node_handles_invalid_json_decode_error(sample_tools):
    """Test that malformed JSON in tool call arguments is captured and returned as a ToolMessage exception."""
    tool_node = _build_tool_node(sample_tools)
    
    # Simulated output from _build_llm_node when JSONDecodeError occurs
    ai_msg = AIMessage(
        content="",
        tool_calls=[{
            "name": "update_plan_status",
            "args": {
                "_invalid_json_error": "JSONDecodeError: Expecting property name enclosed in double quotes",
                "_raw_arguments": "{updates: [unquoted]}"
            },
            "id": "call_bad_json_1",
            "type": "tool_call"
        }]
    )
    
    state: AgentState = {
        "messages": [ai_msg],
        "rpg_state": {},
        "sandbox_timeout": 5.0,
        "iteration_count": 1
    }
    
    res = await tool_node(state, {})
    msg = res["messages"][0]
    assert isinstance(msg, ToolMessage)
    assert msg.tool_call_id == "call_bad_json_1"
    assert "--- Tool Execution Exception ---" in msg.content
    assert "JSONDecodeError" in msg.content
    assert "Raw arguments: '{updates: [unquoted]}'" in msg.content


@pytest.mark.asyncio
async def test_tool_node_handles_unknown_tool(sample_tools):
    """Test calling a non-existent tool name."""
    tool_node = _build_tool_node(sample_tools)
    
    ai_msg = AIMessage(
        content="",
        tool_calls=[{
            "name": "non_existent_tool",
            "args": {"foo": "bar"},
            "id": "call_unknown_1",
            "type": "tool_call"
        }]
    )
    
    state: AgentState = {
        "messages": [ai_msg],
        "rpg_state": {},
        "sandbox_timeout": 5.0,
        "iteration_count": 1
    }
    
    res = await tool_node(state, {})
    msg = res["messages"][0]
    assert isinstance(msg, ToolMessage)
    assert "[Unknown tool: non_existent_tool]" in msg.content
