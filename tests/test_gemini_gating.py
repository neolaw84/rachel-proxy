"""Tests for Gemini model gating (omitting end_turn, prompt adaptation, and empty-narration guard)."""

import json
from unittest.mock import AsyncMock, patch
import pytest
from langchain_core.messages import AIMessage, HumanMessage

from rachel.core.model_utils import is_gemini_model
from rachel.sandbox.schemas import get_all_tools_schema, get_tools_schema
from rachel.agent.tools import make_tools
from rachel.agent.prompts import (
    get_static_system_prompt,
    get_dynamic_turn_directive,
    PromptBuilder,
)
from rachel.agent.nodes import _should_continue, AgentState
from rachel.agent.graph import run_agent


def test_is_gemini_model_detection():
    """Verify is_gemini_model correctly classifies Gemini vs non-Gemini models and providers."""
    # OpenRouter Gemini slugs
    assert is_gemini_model("google/gemini-3.8-flash") is True
    assert is_gemini_model("google/gemini-3.5-flash") is True
    assert is_gemini_model("google/gemini-3-flash-preview") is True
    assert is_gemini_model("google/gemini-2.5-pro") is True
    assert is_gemini_model("google/gemini-2.5-flash") is True

    # Direct Gemini models & providers
    assert is_gemini_model("gemini-2.5-flash") is True
    assert is_gemini_model("gemini-1.5-pro") is True
    assert is_gemini_model(None, provider="gemini_byok") is True
    assert is_gemini_model(
        "custom-model",
        base_url="https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
    ) is True

    # Non-Gemini models
    assert is_gemini_model("deepseek/deepseek-chat") is False
    assert is_gemini_model("deepseek-chat") is False
    assert is_gemini_model("x-ai/grok-4.20") is False
    assert is_gemini_model("openai/gpt-4o") is False
    assert is_gemini_model("meta-llama/llama-3.3-70b-instruct") is False
    assert is_gemini_model(None, None) is False
    assert is_gemini_model("", "") is False


def test_tool_schemas_gating():
    """Verify tool schemas exclude end_turn when include_end_turn is False."""
    # Default (include_end_turn=True)
    all_tools_default = get_all_tools_schema("v8")
    assert any(t["function"]["name"] == "end_turn" for t in all_tools_default)
    assert len(all_tools_default) == 5

    # Gated (include_end_turn=False for Gemini)
    all_tools_gemini = get_all_tools_schema("v8", include_end_turn=False)
    assert not any(t["function"]["name"] == "end_turn" for t in all_tools_gemini)
    assert len(all_tools_gemini) == 4
    tool_names = [t["function"]["name"] for t in all_tools_gemini]
    assert tool_names == ["execute_code_sandbox", "submit_plan", "submit_summary", "submit_cleanup"]

    # get_tools_schema alias parity
    assert get_tools_schema("v8", include_end_turn=False) == all_tools_gemini


def test_make_tools_gating():
    """Verify make_tools excludes end_turn tool when include_end_turn is False."""
    state_container = {"rpg_state": {}}

    # Default include_end_turn=True
    tools_default = make_tools(state_container, sandbox_timeout=2.0, include_end_turn=True)
    names_default = [t.name for t in tools_default]
    assert "end_turn" in names_default
    assert len(tools_default) == 5

    # Gated include_end_turn=False
    tools_gemini = make_tools(state_container, sandbox_timeout=2.0, include_end_turn=False)
    names_gemini = [t.name for t in tools_gemini]
    assert "end_turn" not in names_gemini
    assert len(tools_gemini) == 4
    assert names_gemini == ["execute_code_sandbox", "submit_plan", "submit_summary", "submit_cleanup"]


def test_prompts_gating():
    """Verify prompts and directives adapt when include_end_turn is False."""
    # Dynamic directive with include_end_turn=False
    directive_gemini = get_dynamic_turn_directive(
        rpg_state={},
        max_iterations=5,
        current_iteration=1,
        rem_iterations=4,
        include_end_turn=False,
    )
    assert "Call `end_turn` tool" not in directive_gemini
    assert "Directly output your story narration for this turn" in directive_gemini

    # Dynamic directive with include_end_turn=True
    directive_default = get_dynamic_turn_directive(
        rpg_state={},
        max_iterations=5,
        current_iteration=1,
        rem_iterations=4,
        include_end_turn=True,
    )
    assert "Call `end_turn` tool as soon as sufficient narration" in directive_default

    # Static system prompt with include_end_turn=False
    static_gemini = get_static_system_prompt(include_end_turn=False)
    assert "immediately call `end_turn` tool" not in static_gemini
    assert "conclude your narrative response directly in plain text" in static_gemini

    # Static system prompt with include_end_turn=True
    static_default = get_static_system_prompt(include_end_turn=True)
    assert "immediately call `end_turn` tool" in static_default


def test_should_continue_safety_guard():
    """Verify _should_continue prevents premature termination on empty content and respects gating."""
    edge_gated = _should_continue(max_iterations=5, include_end_turn=False)
    edge_default = _should_continue(max_iterations=5, include_end_turn=True)

    # Case 1: Model emits end_turn with empty content -> must NOT exit to route_end
    ai_empty_end_turn = AIMessage(
        content="",
        tool_calls=[{"name": "end_turn", "args": {}, "id": "call_1"}],
    )
    state_empty: AgentState = {
        "messages": [ai_empty_end_turn],
        "rpg_state": {},
        "sandbox_timeout": 2.0,
        "iteration_count": 1,
    }
    # For default, empty content prevents has_end_turn; since tool_calls exist, routes to "tools"
    assert edge_default(state_empty) == "tools"
    # For gated, include_end_turn=False prevents has_end_turn; routes to "tools"
    assert edge_gated(state_empty) == "tools"

    # Case 2: Model emits end_turn with actual narration text -> routes to route_end under default
    ai_narrated_end_turn = AIMessage(
        content="The wind howled through the ruined towers.",
        tool_calls=[{"name": "end_turn", "args": {}, "id": "call_1"}],
    )
    state_narrated: AgentState = {
        "messages": [ai_narrated_end_turn],
        "rpg_state": {},
        "sandbox_timeout": 2.0,
        "iteration_count": 1,
    }
    assert edge_default(state_narrated) == "route_end"
    # For gated, end_turn is ignored, so tool_calls would route to tools
    assert edge_gated(state_narrated) == "tools"

    # Case 3: Model emits narration with NO tool calls -> routes to route_end under both
    ai_pure_narration = AIMessage(
        content="The wind howled through the ruined towers.",
        tool_calls=[],
    )
    state_pure: AgentState = {
        "messages": [ai_pure_narration],
        "rpg_state": {},
        "sandbox_timeout": 2.0,
        "iteration_count": 1,
    }
    assert edge_default(state_pure) == "route_end"
    assert edge_gated(state_pure) == "route_end"


@pytest.mark.asyncio
async def test_run_agent_gemini_direct_narration():
    """Verify that Gemini model generates narration without end_turn and finishes cleanly."""
    captured_tools = []

    async def mock_streaming(*args, **kwargs):
        captured_tools.append(kwargs.get("tools", []))
        return ("The dragon let out a mighty roar across the valley.", "Thinking about dragon roar...", [])

    messages = [{"role": "user", "content": "What does the dragon do?"}]
    before_state = {"state": {"hp": 100}}

    with patch("rachel.agent.graph.call_openrouter_streaming", side_effect=mock_streaming):
        result = await run_agent(
            messages=messages,
            before_state=before_state,
            api_key="mock_key",
            base_url="https://openrouter.ai/api/v1/chat/completions",
            model="google/gemini-3.8-flash",
            sandbox_timeout=1.0,
            max_iterations=5,
        )

    # Assert tools provided to Gemini did NOT include end_turn
    assert len(captured_tools) == 1
    tool_names = [t["function"]["name"] for t in captured_tools[0]]
    assert "end_turn" not in tool_names
    assert "execute_code_sandbox" in tool_names

    # Assert narrative content was delivered
    assert result["content"] == "The dragon let out a mighty roar across the valley."
    assert "Thinking about dragon roar..." in result["reasoning_content"]


@pytest.mark.asyncio
async def test_run_agent_gemini_multi_round_with_sandbox():
    """Verify Gemini can execute sandbox in Round 1 and then narrate in Round 2 without end_turn."""
    captured_rounds = []

    async def mock_streaming(*args, **kwargs):
        captured_rounds.append(kwargs)
        if len(captured_rounds) == 1:
            # Round 1: Gemini calls execute_code_sandbox, no text content
            return (
                "",
                "I should roll 1d20 for the attack.",
                [{
                    "id": "call_sb_1",
                    "type": "function",
                    "function": {
                        "name": "execute_code_sandbox",
                        "arguments": json.dumps({"code": "state.hp -= 20;"})
                    }
                }]
            )
        else:
            # Round 2: Gemini sees sandbox result, outputs pure narration text
            return (
                "The strike lands true! The beast reels back in agony.",
                "Attack resolved successfully.",
                []
            )

    messages = [{"role": "user", "content": "I strike the beast!"}]
    before_state = {"state": {"hp": 100}}

    with patch("rachel.agent.graph.call_openrouter_streaming", side_effect=mock_streaming):
        result = await run_agent(
            messages=messages,
            before_state=before_state,
            api_key="mock_key",
            base_url="https://openrouter.ai/api/v1/chat/completions",
            model="google/gemini-3.8-flash",
            sandbox_timeout=1.0,
            max_iterations=5,
        )

    assert len(captured_rounds) == 2
    # Verify neither round included end_turn
    for r in captured_rounds:
        tool_names = [t["function"]["name"] for t in r.get("tools", [])]
        assert "end_turn" not in tool_names

    # Verify state was mutated and narration was delivered
    assert result["after_state"]["state"]["hp"] == 80
    assert result["content"] == "The strike lands true! The beast reels back in agony."
    assert "I should roll 1d20" in result["reasoning_content"]
    assert "Attack resolved successfully." in result["reasoning_content"]
