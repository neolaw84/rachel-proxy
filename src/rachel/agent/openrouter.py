"""Multi-Provider API Client (OpenRouter, OpenAI, Google Gemini, DeepSeek)."""

import asyncio
import json
import os
from typing import Any, Sequence
import httpx
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from rachel.sandbox.schemas import get_tools_schema
from rachel.sandbox.sandbox import get_sandbox_engine
from rachel.config import INCLUDE_REASONING, REASONING_PAYLOAD

import re

def parse_think_tags(text: str) -> tuple[str, str]:
    """Extract reasoning from <think>, <thought>, <thinking>, <reasoning> tags and return (clean_content, extracted_reasoning).
    
    Handles both closed tags `<think>reasoning</think>` and unclosed `<think>reasoning`.
    """
    if not text:
        return "", ""

    reasoning_parts = []
    
    # 1. Matches complete <think>...</think>, <thought>...</thought>, etc.
    pattern = re.compile(r"<(think|thought|thinking|reasoning)[^>]*>(.*?)</\1>", re.DOTALL | re.IGNORECASE)
    
    def replacer(match: re.Match) -> str:
        reasoning_parts.append(match.group(2))
        return ""

    clean_content = pattern.sub(replacer, text)
    
    # 2. Match unclosed <think>... at the end of text
    unclosed_pattern = re.compile(r"<(think|thought|thinking|reasoning)[^>]*>(.*)$", re.DOTALL | re.IGNORECASE)
    match = unclosed_pattern.search(clean_content)
    if match:
        clean_content = clean_content[:match.start()]
        reasoning_parts.append(match.group(2))

    extracted_reasoning = "\n\n".join(r.strip() for r in reasoning_parts if r.strip())
    clean_content = clean_content.strip()
    
    return clean_content, extracted_reasoning


class IncrementalThinkParser:
    """Stream parser that detects <think>, <thought>, <thinking>, <reasoning> tags in real-time as chunks arrive."""
    
    OPEN_PATTERN = re.compile(r"<(think|thought|thinking|reasoning)[^>]*>", re.IGNORECASE)
    CLOSE_PATTERN = re.compile(r"</(think|thought|thinking|reasoning)>", re.IGNORECASE)
    
    def __init__(self, stream_queue: asyncio.Queue | None):
        self.stream_queue = stream_queue
        self.in_think = False
        self.buf = ""
        self.extracted_reasoning = []
        self.extracted_content = []

    async def feed(self, chunk: str) -> None:
        if not chunk:
            return
        
        self.buf += chunk
        
        while self.buf:
            if not self.in_think:
                match = self.OPEN_PATTERN.search(self.buf)
                if match:
                    pre_content = self.buf[:match.start()]
                    if pre_content:
                        self.extracted_content.append(pre_content)
                        if self.stream_queue:
                            await self.stream_queue.put(("content", pre_content))
                    
                    self.in_think = True
                    self.buf = self.buf[match.end():]
                else:
                    if "<" in self.buf:
                        idx = self.buf.rfind("<")
                        safe_content = self.buf[:idx]
                        if safe_content:
                            self.extracted_content.append(safe_content)
                            if self.stream_queue:
                                await self.stream_queue.put(("content", safe_content))
                        self.buf = self.buf[idx:]
                        break
                    else:
                        self.extracted_content.append(self.buf)
                        if self.stream_queue:
                            await self.stream_queue.put(("content", self.buf))
                        self.buf = ""
            else:
                match = self.CLOSE_PATTERN.search(self.buf)
                if match:
                    think_text = self.buf[:match.start()]
                    if think_text:
                        self.extracted_reasoning.append(think_text)
                        if self.stream_queue:
                            await self.stream_queue.put(("reasoning", think_text))
                    
                    self.in_think = False
                    self.buf = self.buf[match.end():]
                else:
                    if "<" in self.buf:
                        idx = self.buf.rfind("<")
                        safe_think = self.buf[:idx]
                        if safe_think:
                            self.extracted_reasoning.append(safe_think)
                            if self.stream_queue:
                                await self.stream_queue.put(("reasoning", safe_think))
                        self.buf = self.buf[idx:]
                        break
                    else:
                        self.extracted_reasoning.append(self.buf)
                        if self.stream_queue:
                            await self.stream_queue.put(("reasoning", self.buf))
                        self.buf = ""

    async def flush(self) -> None:
        if not self.buf:
            return
        
        if self.in_think:
            clean_buf = self.CLOSE_PATTERN.sub("", self.buf).strip()
            if clean_buf:
                self.extracted_reasoning.append(clean_buf)
                if self.stream_queue:
                    await self.stream_queue.put(("reasoning", clean_buf))
        else:
            clean_buf = self.OPEN_PATTERN.sub("", self.buf).strip()
            if clean_buf:
                self.extracted_content.append(clean_buf)
                if self.stream_queue:
                    await self.stream_queue.put(("content", clean_buf))
        self.buf = ""


def deep_merge(dict1: dict, dict2: dict) -> dict:
    """Recursively merge dict2 into dict1."""
    for key, value in dict2.items():
        if isinstance(value, dict) and key in dict1 and isinstance(dict1[key], dict):
            deep_merge(dict1[key], value)
        else:
            dict1[key] = value
    return dict1

def convert_to_openai_messages(
    messages: Sequence[BaseMessage],
    turn_numbers: list[int | None] | None = None,
) -> list[dict]:
    """Convert LangChain messages to OpenAI-compatible message dicts."""
    openai_msgs = []
    current_turn_number = turn_numbers[-1] if turn_numbers else None
    for i, m in enumerate(messages):
        turn_num = None
        if turn_numbers and i < len(turn_numbers):
            turn_num = turn_numbers[i]
        elif turn_numbers:
            turn_num = current_turn_number

        prefix = f"Turn {turn_num}: " if turn_num is not None else ""

        if isinstance(m, SystemMessage):
            openai_msgs.append({"role": "system", "content": m.content})
        elif isinstance(m, AIMessage):
            msg: dict[str, Any] = {"role": "assistant"}
            if m.content:
                msg["content"] = prefix + m.content
            if m.tool_calls:
                msg["tool_calls"] = [
                    {
                        "id": tc["id"],
                        "type": "function",
                        "function": {
                            "name": tc["name"],
                            "arguments": json.dumps(tc["args"])
                        }
                    }
                    for tc in m.tool_calls
                ]
            rc = m.additional_kwargs.get("reasoning_content")
            if rc:
                msg["reasoning_content"] = rc
            openai_msgs.append(msg)
        elif isinstance(m, ToolMessage):
            openai_msgs.append({
                "role": "tool",
                "tool_call_id": m.tool_call_id,
                "name": m.name,
                "content": m.content
            })
        else:
            openai_msgs.append({"role": "user", "content": prefix + m.content})
    return openai_msgs

async def call_llm_streaming(
    api_key: str,
    base_url: str,
    model: str,
    openai_messages: list[dict],
    stream_queue: asyncio.Queue | None,
    include_plan: bool = False,
    include_summary: bool = False,
    temperature: float | None = None,
    session_id: str | None = None,
    prompt_cache_key: str | None = None,
    user: str | None = None,
) -> tuple[str, str, list[dict]]:
    """Call LLM provider, streaming reasoning/content chunks to stream_queue if present."""
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "http://localhost",
        "X-Title": "RPG Agent Proxy",
    }
    payload: dict[str, Any] = {
        "model": model,
        "messages": openai_messages,
        "tools": get_tools_schema(
            get_sandbox_engine().name,
            include_plan=include_plan,
            include_summary=include_summary,
        ),
        "stream": stream_queue is not None,
    }
    if temperature is not None:
        payload["temperature"] = temperature
    if session_id:
        headers["X-Session-Id"] = session_id
        payload["session_id"] = session_id
        if not prompt_cache_key:
            prompt_cache_key = session_id
        if not user:
            user = f"user-{session_id}"
    if prompt_cache_key:
        payload["prompt_cache_key"] = prompt_cache_key
    if user:
        payload["user"] = user

    # Request reasoning explicitly if configured
    if INCLUDE_REASONING:
        deep_merge(payload, REASONING_PAYLOAD)

    if stream_queue is not None:
        final_content = []
        final_reasoning = []
        parser = IncrementalThinkParser(stream_queue)
        tool_calls_map = {}

        async with httpx.AsyncClient(timeout=120.0) as client:
            async with client.stream(
                "POST",
                base_url,
                json=payload,
                headers=headers,
            ) as response:
                if response.status_code >= 400:
                    err = await response.aread()
                    raise RuntimeError(f"Provider API error ({response.status_code}): {err.decode()}")

                async for line in response.aiter_lines():
                    line = line.strip()
                    if not line.startswith("data: "):
                        continue
                    data_str = line[6:]
                    if data_str == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data_str)
                    except json.JSONDecodeError:
                        continue

                    choices = chunk.get("choices", [])
                    if not choices:
                        continue
                    delta = choices[0].get("delta", {})

                    # 1. Parse native reasoning_content / reasoning / thought / thinking
                    rc = (
                        delta.get("reasoning_content")
                        or delta.get("reasoning")
                        or delta.get("thought")
                        or delta.get("thinking")
                    )
                    if rc:
                        final_reasoning.append(str(rc))
                        await stream_queue.put(("reasoning", str(rc)))

                    # 2. Parse content into turn buffer with incremental real-time tag extraction
                    c = delta.get("content")
                    if c:
                        await parser.feed(c)

                    # 3. Parse tool_calls
                    tcs = delta.get("tool_calls", [])
                    for tc in tcs:
                        idx = tc.get("index", 0)
                        if idx not in tool_calls_map:
                            tool_calls_map[idx] = {
                                "id": tc.get("id", ""),
                                "name": tc.get("function", {}).get("name", ""),
                                "arguments": ""
                            }
                        if tc.get("id"):
                            tool_calls_map[idx]["id"] = tc["id"]
                        if tc.get("function", {}).get("name"):
                            tool_calls_map[idx]["name"] = tc["function"]["name"]

                        arg_frag = tc.get("function", {}).get("arguments", "")
                        tool_calls_map[idx]["arguments"] += arg_frag

        # Flush incremental parser
        await parser.flush()
        if parser.extracted_content:
            final_content.append("".join(parser.extracted_content))
        if parser.extracted_reasoning:
            final_reasoning.append("".join(parser.extracted_reasoning))

        tc_list = []
        for idx in sorted(tool_calls_map.keys()):
            tc = tool_calls_map[idx]
            tc_list.append({
                "id": tc["id"],
                "type": "function",
                "function": {
                    "name": tc["name"],
                    "arguments": tc["arguments"]
                }
            })
        return "".join(final_content), "".join(final_reasoning), tc_list
    else:
        # Non-streaming call
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                base_url,
                json=payload,
                headers=headers,
            )
            if response.status_code >= 400:
                raise RuntimeError(f"Provider API error ({response.status_code}): {response.text}")

            res_json = response.json()
            msg = res_json["choices"][0]["message"]
            raw_content = msg.get("content") or ""
            reasoning = (
                msg.get("reasoning_content")
                or msg.get("reasoning")
                or msg.get("thought")
                or msg.get("thinking")
                or ""
            )
            tcs = msg.get("tool_calls") or []

            clean_content, think_reasoning = parse_think_tags(raw_content)
            if think_reasoning:
                reasoning = f"{reasoning}\n{think_reasoning}".strip() if reasoning else think_reasoning

            return clean_content, reasoning, tcs

async def call_llm_direct(
    api_key: str,
    base_url: str,
    model: str,
    openai_messages: list[dict],
    temperature: float = 0.2,
    session_id: str | None = None,
    prompt_cache_key: str | None = None,
    user: str | None = None,
) -> str:
    """Make a simple, direct, non-streaming completion call to provider without tool injection."""
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "http://localhost",
        "X-Title": "RPG Agent Proxy",
    }
    payload: dict[str, Any] = {
        "model": model,
        "messages": openai_messages,
        "temperature": temperature,
    }
    if session_id:
        headers["X-Session-Id"] = session_id
        payload["session_id"] = session_id
        if not prompt_cache_key:
            prompt_cache_key = session_id
        if not user:
            user = f"user-{session_id}"
    if prompt_cache_key:
        payload["prompt_cache_key"] = prompt_cache_key
    if user:
        payload["user"] = user

    async with httpx.AsyncClient(timeout=120.0) as client:
        response = await client.post(base_url, json=payload, headers=headers)
        if response.status_code >= 400:
            raise RuntimeError(f"Provider API error ({response.status_code}): {response.text}")
        res_json = response.json()
        raw_content = res_json["choices"][0]["message"].get("content") or ""
        clean_content, _ = parse_think_tags(raw_content)
        return clean_content

# Backward compatibility aliases
call_openrouter_streaming = call_llm_streaming
call_openrouter_direct = call_llm_direct

