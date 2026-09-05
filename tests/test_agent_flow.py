"""Integration test for the LangGraph agent execution and streaming queue."""

import asyncio
import json
import pytest
from unittest.mock import AsyncMock, patch

from langchain_core.messages import AIMessage, SystemMessage

from rachel.agent.graph import run_agent, _convert_messages


@pytest.mark.asyncio
async def test_run_agent_flow_with_streaming():
    """Verify that run_agent correctly puts reasoning chunks, tool execution logs,
    and final content chunks onto the provided stream_queue.
    """
    stream_queue = asyncio.Queue()
    before_state = {"state": {"hp": 100}, "hidden_state": {}, "summary": "", "plan": []}


    # Custom responses to simulate 2 iterations of the LLM node:
    # Iteration 1: Calls execute_code_sandbox
    # Iteration 2: Final text response
    mock_responses = [
        # Response 1
        {
            "choices": [{
                "delta": {
                    "reasoning_content": "Checking player health first...",
                }
            }]
        },
        {
            "choices": [{
                "delta": {
                    "tool_calls": [{
                        "index": 0,
                        "id": "call_123",
                        "function": {
                            "name": "execute_code_sandbox",
                            "arguments": '{"code": "state[\'hp\'] -= 20"}'
                        }
                    }]
                }
            }]
        },
        # DONE indicator for Iteration 1 stream
        "[DONE]",

        # Response 2 (Final)
        {
            "choices": [{
                "delta": {
                    "content": "You took damage! Your HP is now 80."
                }
            }]
        },
        "[DONE]"
    ]

    mock_response_idx = 0

    class MockStreamResponse:
        def __init__(self, status_code=200):
            self.status_code = status_code

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass

        async def aiter_lines(self):
            nonlocal mock_response_idx
            # Yield lines for the current mock response stream
            while mock_response_idx < len(mock_responses):
                val = mock_responses[mock_response_idx]
                mock_response_idx += 1
                if val == "[DONE]":
                    yield "data: [DONE]"
                    break
                else:
                    yield f"data: {json.dumps(val)}"

    def mock_stream(*args, **kwargs):
        return MockStreamResponse()

    class MockPostResponse:
        def __init__(self, status_code=200):
            self.status_code = status_code
            self.text = "{}"
        def json(self):
            return {"choices": [{"message": {"content": "ok"}}]}

    # Patch httpx.AsyncClient.stream and post
    with patch("httpx.AsyncClient.stream", side_effect=mock_stream), \
         patch("httpx.AsyncClient.post", return_value=MockPostResponse()):
        result = await run_agent(
            messages=[{"role": "user", "content": "attack me"}],
            before_state=before_state,
            api_key="mock_key",
            base_url="https://mock-openrouter/api/v1/chat/completions",
            model="mock-model",
            sandbox_timeout=1.0,
            max_iterations=5,
            stream_queue=stream_queue,
        )

        # 1. Assert return payload values
        assert result["content"] == "You took damage! Your HP is now 80."
        assert result["after_state"]["state"] == {"hp": 80}


        # 2. Extract queue items to check the exact order of events
        events = []
        while not stream_queue.empty():
            events.append(await stream_queue.get())

        # Ensure we captured:
        # - Reasoning chunks from Iteration 1
        # - Tool start log from Tool Node
        # - Sandbox execution output from Tool Node
        # - Content chunks from Iteration 2
        assert len(events) > 0
        
        # Verify reasoning event was captured
        reasoning_events = [val for ctype, val in events if ctype == "reasoning"]
        assert len(reasoning_events) > 0
        assert "Checking player health" in reasoning_events[0]

        # Verify tool log event was captured
        tool_events = [val for ctype, val in events if ctype == "tool_log"]
        assert len(tool_events) >= 2
        assert any("Calling tool: execute_code_sandbox" in e for e in tool_events)
        assert any("[Output]" in e for e in tool_events)

        # Verify content event was captured
        content_events = [val for ctype, val in events if ctype == "content"]
        assert len(content_events) > 0
        assert "You took damage!" in content_events[0]


@pytest.mark.asyncio
@patch("rachel.agent.graph.call_openrouter_streaming", new_callable=AsyncMock)
async def test_end_turn_tool_call_routing(mock_streaming):
    """Verify that calling end_turn tool stops iteration and routes to route_end."""
    mock_streaming.return_value = (
        "I have narrated the scene.",
        None,
        [{"id": "call_end_1", "type": "function", "function": {"name": "end_turn", "arguments": "{}"}}]
    )

    before_state = {"hp": 100}
    messages = [{"role": "user", "content": "I look around."}]

    result = await run_agent(
        messages=messages,
        before_state=before_state,
        api_key="mock_key",
        base_url="https://mock-openrouter/api/v1/chat/completions",
        model="mock-model",
        sandbox_timeout=1.0,
        max_iterations=5,
    )

    # Should finish after 1 call because end_turn was called
    assert mock_streaming.call_count == 1
    assert result["content"] == "I have narrated the scene."


@pytest.mark.asyncio
async def test_multi_round_message_structure_and_tool_state_expansion():
    """Verify that in multi-round execution:
    1. In Round 1, the user message contains the directive and is cached.
    2. In Round 2, the user message is identical to Round 1 (reused from cache).
    3. In Round 2, the message sequence ends with the 'tool' role (NO synthetic user message).
    4. The ToolMessage contains [Updated Game State] with mutated state, hidden_state, and plan.
    """
    import copy
    captured_calls = []

    async def mock_streaming(*args, **kwargs):
        openai_messages = kwargs.get("openai_messages", [])
        captured_calls.append(copy.deepcopy(openai_messages))

        if len(captured_calls) == 1:
            # Round 1: Model calls execute_code_sandbox to drink potion and update plan status
            return (
                "Drinking a potion...",
                None,
                [{
                    "id": "call_potion_1",
                    "type": "function",
                    "function": {
                        "name": "execute_code_sandbox",
                        "arguments": json.dumps({"code": "state.hp = 95; hidden_state.buff = 'regen'; update_plan_status([{id: 1, status: 'completed'}]);"})
                    }
                }]
            )
        else:
            # Round 2: Model finishes the turn
            return (
                "You feel revitalized! Your wounds heal completely.",
                None,
                [{
                    "id": "call_end_turn_1",
                    "type": "function",
                    "function": {
                        "name": "end_turn",
                        "arguments": "{}"
                    }
                }]
            )

    before_state = {
        "state": {"hp": 50},
        "hidden_state": {"secret": 123},
        "plan": [{"id": 1, "text": "rest", "status": "to-do"}],
        "summary": "Previous adventures."
    }
    messages = [{"role": "user", "content": "I drink the potion."}]

    with patch("rachel.agent.graph.call_openrouter_streaming", side_effect=mock_streaming):
        result = await run_agent(
            messages=messages,
            before_state=before_state,
            api_key="mock_key",
            base_url="https://mock-openrouter/api/v1/chat/completions",
            model="mock-model",
            sandbox_timeout=1.0,
            max_iterations=5,
        )

    # 1. Assert two rounds occurred
    assert len(captured_calls) == 2

    # 2. Round 1 checks
    round1_msgs = captured_calls[0]
    r1_user_msgs = [m for m in round1_msgs if m.get("role") == "user"]
    assert len(r1_user_msgs) == 1
    r1_user_content = r1_user_msgs[0]["content"]
    assert "I drink the potion." in r1_user_content
    assert "[RPG DIRECTIVE & GAME STATE" in r1_user_content
    assert '"hp": 50' in r1_user_content

    # 3. Round 2 checks
    round2_msgs = captured_calls[1]
    # Trailing message MUST be role 'tool', NOT a synthetic 'user' message!
    assert round2_msgs[-1]["role"] == "tool"
    assert round2_msgs[-1]["tool_call_id"] == "call_potion_1"

    # Verify tool message has stdout + [Updated Game State] snapshot
    tool_content = round2_msgs[-1]["content"]
    assert "[Updated Game State]:" in tool_content
    assert '"hp": 95' in tool_content
    assert '"buff": "regen"' in tool_content
    assert '"text": "rest"' in tool_content

    # Verify the user message in Round 2 is bitwise identical to Round 1 (reused from cache)
    r2_user_msgs = [m for m in round2_msgs if m.get("role") == "user"]
    assert len(r2_user_msgs) == 1
    assert r2_user_msgs[0]["content"] == r1_user_content

    # 4. Result checks
    assert result["content"] == "You feel revitalized! Your wounds heal completely."
    assert result["after_state"]["state"]["hp"] == 95
    assert result["after_state"]["hidden_state"]["buff"] == "regen"


