"""LangGraph agent for the RPG proxy.

Implements a multi-node state graph for orchestration.
"""

from __future__ import annotations

import asyncio
from typing import Annotated, Any, Sequence, TypedDict
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages

# Expose node builders and helpers from nodes
from rachel.agent.nodes import (
    AgentState,
    _build_llm_node,
    _build_tool_node,
    _should_continue,
    _convert_messages,
    _build_pre_action_node,
    _build_route_end_node,
)

# Exported/delegated for test mock compatibility
from rachel.agent.prompts import (
    PromptBuilder,
    get_static_system_prompt,
    get_dynamic_turn_directive,
    get_dynamic_plan_directive,
    get_dynamic_summary_directive,
    get_dynamic_cleanup_directive,
    get_plan_prompt,
    get_summary_prompt,
    get_cleanup_prompt,
)


async def call_openrouter_direct(*args, **kwargs):
    from rachel.agent import openrouter
    return await openrouter.call_openrouter_direct(*args, **kwargs)

async def call_openrouter_streaming(*args, **kwargs):
    from rachel.agent import openrouter
    return await openrouter.call_openrouter_streaming(*args, **kwargs)

from rachel.agent.tools import make_tools

def build_graph(
    api_key: str,
    base_url: str,
    model: str,
    state_container: dict[str, Any],
    sandbox_timeout: float,
    max_iterations: int,
    temperature: float | None = None,
):
    """Compile and return the LangGraph agent graph."""
    tools = make_tools(state_container, sandbox_timeout)

    graph = StateGraph(AgentState)  # type: ignore[arg-type]
    graph.add_node("pre_action", _build_pre_action_node(api_key, state_container, sandbox_timeout, base_url=base_url))
    graph.add_node("llm", _build_llm_node(api_key, base_url, model, max_iterations, sandbox_timeout, state_container, temperature=temperature))
    graph.add_node("tools", _build_tool_node(tools))
    graph.add_node("route_end", _build_route_end_node())

    graph.set_entry_point("pre_action")
    graph.add_edge("pre_action", "llm")
    graph.add_conditional_edges("llm", _should_continue(max_iterations), {
        "tools": "tools",
        "route_end": "route_end",
    })
    graph.add_edge("tools", "llm")
    graph.add_edge("route_end", END)

    return graph.compile()

async def run_agent(
    messages: list[dict],
    before_state: dict[str, Any],
    api_key: str,
    base_url: str,
    model: str,
    temperature: float | None = None,
    sandbox_timeout: float = 2.0,
    max_iterations: int = 5,
    stream_queue: asyncio.Queue | None = None,
    session_id: str | None = None,
    turn_number: int | None = None,
    turn_numbers: list[int | None] | None = None,
    last_plan_turn: int = 0,
    last_summary_turn: int = 0,
    last_cleanup_turn: int = 0,
) -> dict[str, Any]:
    """Run the LangGraph agent for one proxy turn."""
    if turn_number is None:
        turn_number = sum(1 for m in messages if m.get("role") == "assistant") + 1
    rpg_dict = dict(before_state) if isinstance(before_state, dict) else {}
    if not all(k in rpg_dict for k in ("state", "hidden_state", "summary", "plan")):
        rpg_dict = {
            "state": rpg_dict,
            "hidden_state": {},
            "summary": "",
            "plan": [],
        }
    state_container: dict[str, Any] = {
        "rpg_state": rpg_dict,
        "current_turn": turn_number,
        "turn_numbers": turn_numbers,
        "last_plan_turn": last_plan_turn,
        "last_summary_turn": last_summary_turn,
        "last_cleanup_turn": last_cleanup_turn,
    }
    if session_id:
        state_container["session_id"] = session_id
        from rachel.core.session import get_session_caching_info
        caching_info = get_session_caching_info(session_id)
        if "hidden_state" not in state_container["rpg_state"] or not isinstance(state_container["rpg_state"]["hidden_state"], dict):
            state_container["rpg_state"]["hidden_state"] = {}
        state_container["rpg_state"]["hidden_state"]["session_info"] = caching_info

    compiled = build_graph(
        api_key=api_key,
        base_url=base_url,
        model=model,
        state_container=state_container,
        sandbox_timeout=sandbox_timeout,
        max_iterations=max_iterations,
        temperature=temperature,
    )

    initial_state: AgentState = {
        "messages": _convert_messages(messages),
        "rpg_state": state_container["rpg_state"],
        "sandbox_timeout": sandbox_timeout,
        "iteration_count": 0,
    }

    # 1. Decoupled trigger calculations for plan, summary, and cleanup
    from rachel.config import (
        PLAN_OFFSET,
        PLAN_TRIGGER_TYPE,
        PLAN_INTERVAL_TURNS,
        PLAN_TRIGGER_PROBABILITY,
        SUMMARY_TRIGGER_TYPE,
        SUMMARY_INTERVAL_TURNS,
        SUMMARY_TRIGGER_PROBABILITY,
        PLAN_SUMMARY_GAP,
        CLEANUP_TRIGGER_TYPE,
        CLEANUP_INTERVAL_TURNS,
        CLEANUP_TRIGGER_PROBABILITY,
        PLAN_CLEANUP_GAP,
    )
    import hashlib
    import random

    # Plan Trigger
    if PLAN_TRIGGER_TYPE == "disabled":
        plan_fired = False
    elif PLAN_TRIGGER_TYPE == "probabilistic":
        msg_contents = [m.get("content") or "" for m in messages]
        seed = int(hashlib.sha256("\x00".join(msg_contents).encode("utf-8")).hexdigest(), 16)
        seed_plan = seed ^ 0xAAAA_AAAA
        rng = random.Random(seed_plan)
        plan_fired = rng.random() < PLAN_TRIGGER_PROBABILITY
    else:
        if PLAN_OFFSET > 0:
            plan_fired = (turn_number >= PLAN_OFFSET and (turn_number - PLAN_OFFSET) % PLAN_INTERVAL_TURNS == 0)
        else:
            if turn_number == 1:
                plan_fired = True
            else:
                plan_fired = (turn_number % PLAN_INTERVAL_TURNS == 0)

    # Summary Trigger
    if SUMMARY_TRIGGER_TYPE == "disabled":
        summary_fired = False
    elif SUMMARY_TRIGGER_TYPE == "probabilistic":
        msg_contents = [m.get("content") or "" for m in messages]
        seed = int(hashlib.sha256("\x00".join(msg_contents).encode("utf-8")).hexdigest(), 16)
        seed_summary = seed ^ 0x5555_5555
        rng = random.Random(seed_summary)
        summary_fired = rng.random() < SUMMARY_TRIGGER_PROBABILITY
    else:
        summary_fired = (turn_number >= PLAN_SUMMARY_GAP and (turn_number - PLAN_SUMMARY_GAP) % SUMMARY_INTERVAL_TURNS == 0)

    # Cleanup Trigger
    if CLEANUP_TRIGGER_TYPE == "disabled":
        cleanup_fired = False
    elif CLEANUP_TRIGGER_TYPE == "probabilistic":
        msg_contents = [m.get("content") or "" for m in messages]
        seed = int(hashlib.sha256("\x00".join(msg_contents).encode("utf-8")).hexdigest(), 16)
        seed_cleanup = seed ^ 0x3333_3333
        rng = random.Random(seed_cleanup)
        cleanup_fired = rng.random() < CLEANUP_TRIGGER_PROBABILITY
    else:
        cleanup_fired = (turn_number >= PLAN_CLEANUP_GAP and (turn_number - PLAN_CLEANUP_GAP) % CLEANUP_INTERVAL_TURNS == 0)

    config: RunnableConfig = {"recursion_limit": max_iterations * 2 + 10}
    config["configurable"] = {
        "plan_fired": plan_fired,
        "summary_fired": summary_fired,
        "cleanup_fired": cleanup_fired,
    }
    if session_id:
        config["configurable"]["session_id"] = session_id
    if stream_queue is not None:
        config["configurable"]["stream_queue"] = stream_queue


    final_state = await compiled.ainvoke(initial_state, config=config)

    # Extract final AIMessage details and accumulate reasoning across turns
    from rachel.agent.openrouter import parse_think_tags
    final_content = ""
    reasoning_parts = []
    for msg in final_state["messages"]:
        if isinstance(msg, AIMessage):
            content = msg.content or ""
            if not isinstance(content, str):
                content = str(content)
            clean, think = parse_think_tags(content)
            if think:
                reasoning_parts.append(think)
            if clean:
                final_content = clean
            rc = msg.additional_kwargs.get("reasoning_content")
            if rc:
                reasoning_parts.append(rc)
    final_reasoning = "\n\n".join(r for r in reasoning_parts if r)

    return {
        "content": final_content,
        "reasoning_content": final_reasoning,
        "after_state": state_container["rpg_state"],
        "last_plan_turn": state_container.get("last_plan_turn", 0),
        "last_summary_turn": state_container.get("last_summary_turn", 0),
        "last_cleanup_turn": state_container.get("last_cleanup_turn", 0),
    }
