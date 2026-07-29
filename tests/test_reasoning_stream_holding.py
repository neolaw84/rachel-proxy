"""Tests for holding reasoning/thinking stream signals across multi-turn tool calls."""

import pytest
import asyncio
from unittest.mock import patch, MagicMock
from rachel.agent.openrouter import call_openrouter_streaming
from rachel.routes.completions import _stream_generator


class MockAsyncLineStream:
    def __init__(self, lines):
        self.lines = lines

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass

    async def aiter_lines(self):
        for line in self.lines:
            yield line


@pytest.mark.asyncio
async def test_streaming_buffers_content_in_tool_calling_turn():
    """Test that LLM turn produces both reasoning and content properly without reclassifying content."""
    stream_queue = asyncio.Queue()
    
    # SSE lines simulating an LLM turn that outputs reasoning, content, and a tool call
    sse_lines = [
        'data: {"choices": [{"delta": {"reasoning_content": "Thinking about plan update..."}}]}',
        'data: {"choices": [{"delta": {"content": "Intermediate note before tool call."}}]}',
        'data: {"choices": [{"delta": {"tool_calls": [{"index": 0, "id": "tc1", "function": {"name": "update_plan", "arguments": "[]"}}]}}]}',
        'data: [DONE]'
    ]
    
    mock_response = MockAsyncLineStream(sse_lines)
    mock_response.status_code = 200

    with patch("httpx.AsyncClient.stream", return_value=mock_response):
        content, reasoning, tcs = await call_openrouter_streaming(
            api_key="test-key",
            base_url="https://openrouter.ai/api/v1",
            model="test-model",
            openai_messages=[],
            stream_queue=stream_queue,
        )

    # Collect events sent to stream_queue
    events = []
    while not stream_queue.empty():
        events.append(await stream_queue.get())

    assert len(tcs) == 1
    assert tcs[0]["function"]["name"] == "update_plan"
    
    # Verification: Both reasoning and content events were emitted accurately
    event_types = [e[0] for e in events]
    assert "reasoning" in event_types
    assert "content" in event_types
    assert content == "Intermediate note before tool call."
    assert reasoning == "Thinking about plan update..."


@pytest.mark.asyncio
async def test_extract_think_tags_streaming():
    """Test that inline <think>...</think> tags in content stream are extracted to reasoning."""
    stream_queue = asyncio.Queue()
    
    sse_lines = [
        'data: {"choices": [{"delta": {"content": "<think>Analysing player situation...</think>Let us begin."}}]}',
        'data: [DONE]'
    ]
    
    mock_response = MockAsyncLineStream(sse_lines)
    mock_response.status_code = 200

    with patch("httpx.AsyncClient.stream", return_value=mock_response):
        content, reasoning, tcs = await call_openrouter_streaming(
            api_key="test-key",
            base_url="https://openrouter.ai/api/v1",
            model="test-model",
            openai_messages=[],
            stream_queue=stream_queue,
        )

    events = []
    while not stream_queue.empty():
        events.append(await stream_queue.get())

    assert ("content", "Let us begin.") in events


@pytest.mark.asyncio
async def test_incremental_think_parser_various_tags():
    """Test that IncrementalThinkParser parses <thought>, <thinking>, <reasoning> case-insensitively across chunk boundaries."""
    from rachel.agent.openrouter import IncrementalThinkParser
    stream_queue = asyncio.Queue()
    parser = IncrementalThinkParser(stream_queue)
    
    await parser.feed("Some intro text. <THOUGHT>I should check player ")
    await parser.feed("status first.</THOUGHT> ")
    await parser.feed("<thinking>Now computing stats...</thinking>")
    await parser.feed("Here is your output.")
    await parser.flush()
    
    events = []
    while not stream_queue.empty():
        events.append(await stream_queue.get())
        
    reasoning_texts = [e[1] for e in events if e[0] == "reasoning"]
    content_texts = [e[1] for e in events if e[0] == "content"]
    
    assert "I should check player " in reasoning_texts
    assert "status first." in reasoning_texts
    assert "Now computing stats..." in reasoning_texts
    assert "Some intro text. " in content_texts
    assert "Here is your output." in content_texts



@pytest.mark.asyncio
async def test_stream_generator_emits_stop_finish_reason():
    """Test that _stream_generator yields finish_reason='stop' upon successful task completion."""
    stream_queue = asyncio.Queue()
    await stream_queue.put(("reasoning", "Thinking..."))
    await stream_queue.put(("content", "Final output."))

    async def dummy_agent_task():
        return {"after_state": {}}

    agent_task = asyncio.create_task(dummy_agent_task())
    mock_store = MagicMock()

    chunks = []
    async for chunk_bytes in _stream_generator(
        agent_task=agent_task,
        stream_queue=stream_queue,
        resolved_sid="sess_123",
        turn_key="turn_123",
        model="test-model",
        cache_miss=False,
        store=mock_store,
        before_state={},
    ):
        chunks.append(chunk_bytes.decode())

    # Verify that the final chunk has finish_reason: "stop"
    stop_chunk_found = any('"finish_reason": "stop"' in chunk for chunk in chunks)
    assert stop_chunk_found
