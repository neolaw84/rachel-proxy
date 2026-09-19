"""Tests for orchestration thinking signals emitted during periodic tasks."""

import asyncio
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from rachel.agent.graph import run_agent
from rachel.agent.nodes import (
    _build_pre_action_node,
    _build_plan_node,
    _build_summary_node,
    _build_cleanup_node,
    _emit_orchestration_signal,
)
from rachel.routes.completions import _stream_generator


@pytest.mark.asyncio
async def test_stream_generator_routes_orchestration_to_reasoning_content():
    """Verify that _stream_generator maps ('orchestration', text) to delta.reasoning_content."""
    stream_queue = asyncio.Queue()
    await stream_queue.put(("orchestration", "[Planning: Reviewing story objectives...]\n"))
    await stream_queue.put(("content", "Hello traveler!"))

    async def dummy_agent_task():
        return {"after_state": {}}

    agent_task = asyncio.create_task(dummy_agent_task())
    mock_store = MagicMock()

    chunks = []
    async for chunk_bytes in _stream_generator(
        agent_task=agent_task,
        stream_queue=stream_queue,
        resolved_sid="sess_orch_1",
        turn_key="turn_orch_1",
        model="test-model",
        cache_miss=False,
        store=mock_store,
        before_state={},
        turn_number=1,
        meta_data={},
    ):
        chunks.append(chunk_bytes.decode())

    # Find the chunk containing the orchestration signal
    orch_chunk = next(
        (c for c in chunks if "[Planning: Reviewing story objectives...]" in c),
        None,
    )
    assert orch_chunk is not None, "Expected orchestration chunk was not yielded in stream"
    assert '"reasoning_content": "[Planning: Reviewing story objectives...]\\n"' in orch_chunk


@pytest.mark.asyncio
async def test_pre_action_node_emits_orchestration_signals():
    """Verify that pre_action_node emits start and completion signals to stream_queue."""
    stream_queue = asyncio.Queue()
    state_container = {
        "rpg_state": {"state": {}, "hidden_state": {}, "summary": "", "plan": []},
    }

    mock_plan = AsyncMock(return_value={"rpg_state": {}})
    mock_summary = AsyncMock(return_value={"rpg_state": {}})

    with patch("rachel.agent.nodes._build_plan_node", return_value=mock_plan), \
         patch("rachel.agent.nodes._build_summary_node", return_value=mock_summary), \
         patch("rachel.agent.nodes._build_cleanup_node", return_value=AsyncMock()):

        pre_action_node = _build_pre_action_node(
            api_key="mock-key",
            state_container=state_container,
            sandbox_timeout=2.0,
        )

        config = {
            "configurable": {
                "plan_fired": True,
                "summary_fired": True,
                "cleanup_fired": False,
                "stream_queue": stream_queue,
            }
        }

        await pre_action_node({"messages": []}, config)

        events = []
        while not stream_queue.empty():
            events.append(await stream_queue.get())

        assert len(events) >= 2
        event_types = [e[0] for e in events]
        assert all(t == "orchestration" for t in event_types)

        event_texts = [e[1] for e in events]
        assert any("[Background Tasks: Story Planning, Memory Summarization triggered...]" in t for t in event_texts)
        assert any("[Background Tasks: All tasks completed.]" in t for t in event_texts)


@pytest.mark.asyncio
async def test_plan_node_emits_orchestration_signals():
    """Verify that plan_node emits review and checklist updated signals."""
    stream_queue = asyncio.Queue()
    state_container = {
        "rpg_state": {"state": {}, "hidden_state": {}, "summary": "", "plan": []},
        "last_plan_turn": 0,
    }

    # Mock call_openrouter_direct to return valid plan tool call
    plan_tc = [{
        "function": {
            "name": "submit_plan",
            "arguments": json.dumps({"items": [{"description": "Find artifact", "status": "to-do"}]}),
        }
    }]

    with patch("rachel.agent.nodes._GraphDelegate.call_openrouter_direct", AsyncMock(return_value=("", plan_tc))):
        plan_node = _build_plan_node(
            api_key="mock-key",
            state_container=state_container,
        )

        config = {
            "configurable": {
                "stream_queue": stream_queue,
            }
        }

        await plan_node({"messages": []}, config)

        events = []
        while not stream_queue.empty():
            events.append(await stream_queue.get())

        assert len(events) >= 2
        event_texts = [e[1] for e in events]
        assert any("[Planning: Reviewing story objectives & NPC directives...]" in t for t in event_texts)
        assert any("[Planning: Checklist updated (1 active items).]" in t for t in event_texts)


@pytest.mark.asyncio
async def test_summary_node_emits_orchestration_signals():
    """Verify that summary_node emits compaction start and complete signals."""
    from langchain_core.messages import AIMessage
    stream_queue = asyncio.Queue()
    state_container = {
        "rpg_state": {"state": {}, "hidden_state": {}, "summary": "", "plan": []},
        "last_summary_turn": 0,
    }

    # Provide messages such that current_turn > last_summary_turn + 1
    state = {"messages": [AIMessage(content="Turn 1"), AIMessage(content="Turn 2")]}

    summary_tc = [{
        "function": {
            "name": "submit_summary",
            "arguments": json.dumps({"summary": "The adventure started."}),
        }
    }]

    with patch("rachel.agent.nodes._GraphDelegate.call_openrouter_direct", AsyncMock(return_value=("", summary_tc))):
        summary_node = _build_summary_node(
            api_key="mock-key",
            state_container=state_container,
        )

        config = {
            "configurable": {
                "stream_queue": stream_queue,
            }
        }

        await summary_node(state, config)

        events = []
        while not stream_queue.empty():
            events.append(await stream_queue.get())

        assert len(events) >= 2
        event_texts = [e[1] for e in events]
        assert any("[Summary: Compacting narrative memory" in t for t in event_texts)
        assert any("[Summary: Memory compaction complete.]" in t for t in event_texts)


@pytest.mark.asyncio
async def test_cleanup_node_emits_orchestration_signals():
    """Verify that cleanup_node emits validation start and complete signals."""
    stream_queue = asyncio.Queue()
    state_container = {
        "rpg_state": {"state": {"gold": 50}, "hidden_state": {}, "summary": "", "plan": []},
        "last_cleanup_turn": 0,
    }

    cleanup_tc = [{
        "function": {
            "name": "submit_cleanup",
            "arguments": json.dumps({"code": "state.gold += 10;"}),
        }
    }]

    with patch("rachel.agent.nodes._GraphDelegate.call_openrouter_direct", AsyncMock(return_value=("", cleanup_tc))):
        cleanup_node = _build_cleanup_node(
            api_key="mock-key",
            state_container=state_container,
            sandbox_timeout=2.0,
        )

        config = {
            "configurable": {
                "stream_queue": stream_queue,
            }
        }

        await cleanup_node({"messages": []}, config)

        events = []
        while not stream_queue.empty():
            events.append(await stream_queue.get())

        assert len(events) >= 2
        event_texts = [e[1] for e in events]
        assert any("[Cleanup: Validating game state constraints" in t for t in event_texts)
        assert any("[Cleanup: State validation complete.]" in t for t in event_texts)


@pytest.mark.asyncio
async def test_orchestration_signals_suppressed_when_include_reasoning_false():
    """Verify that signals are suppressed when INCLUDE_REASONING is False."""
    stream_queue = asyncio.Queue()
    state_container = {}

    with patch("rachel.config.INCLUDE_REASONING", False):
        await _emit_orchestration_signal(stream_queue, state_container, "Test message")
        assert stream_queue.empty()
        assert "orchestration_logs" not in state_container


@pytest.mark.asyncio
async def test_orchestration_logs_included_in_final_reasoning():
    """Verify that orchestration logs are prepended to final_reasoning in run_agent."""
    from langchain_core.messages import AIMessage

    async def mock_ainvoke(state, config=None):
        return {
            "messages": [AIMessage(content="Final story answer.", additional_kwargs={"reasoning_content": "Deep thought."})],
            "rpg_state": {},
        }

    with patch("rachel.agent.graph.build_graph") as mock_bg:
        mock_compiled = MagicMock()
        mock_compiled.ainvoke = mock_ainvoke
        mock_bg.return_value = mock_compiled

        # Mock pre_action side effect to add orchestration logs to state_container
        def side_effect_build_graph(*args, **kwargs):
            state_cont = kwargs.get("state_container", {})
            state_cont["orchestration_logs"] = ["[Planning: Checklist updated (2 items).]\n"]
            return mock_compiled

        mock_bg.side_effect = side_effect_build_graph

        result = await run_agent(
            messages=[{"role": "user", "content": "hello"}],
            before_state={},
            api_key="mock",
            base_url="https://mock",
            model="mock",
        )

        assert "[Planning: Checklist updated (2 items).]" in result["reasoning_content"]
        assert "Deep thought." in result["reasoning_content"]

