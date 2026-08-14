"""Nodes and conditional routing functions for the LangGraph RPG Agent."""

import json
import logging
import re
from typing import Annotated, Any, Sequence, TypedDict
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END
from langgraph.graph.message import add_messages

from rachel.agent.prompts import (
    get_system_instruction,
    get_summary_prompt,
    get_plan_prompt,
    get_range_reference,
    middle_out_messages,
)
from rachel.agent.openrouter import convert_to_openai_messages, call_openrouter_streaming, call_openrouter_direct
from rachel.sandbox.sandbox import get_sandbox_engine

logger = logging.getLogger(__name__)


def _strip_fenced_code_block(text: str) -> str:
    """Strip starting/ending markdown fenced delimiters including optional language tags."""
    text = text.strip()
    import re
    # Remove leading ```[optional-lang]
    text = re.sub(r"^```[a-zA-Z-]*\s*", "", text)
    # Remove trailing ```
    text = re.sub(r"\s*```$", "", text)
    return text.strip()

class _GraphDelegate:
    """Helper class to delegate calls to graph.py to maintain test patch compatibility."""

    @staticmethod
    def get_system_instruction(*args, **kwargs):
        import rachel.agent.graph as graph
        return graph.get_system_instruction(*args, **kwargs)

    @staticmethod
    async def call_openrouter_streaming(*args, **kwargs):
        import rachel.agent.graph as graph
        return await graph.call_openrouter_streaming(*args, **kwargs)

    @staticmethod
    async def call_openrouter_direct(*args, **kwargs):
        import rachel.agent.graph as graph
        return await graph.call_openrouter_direct(*args, **kwargs)


def _calculate_turns_since_update(current_turn: int, last_update_turn: int) -> tuple[int, str]:
    """Calculate the number of turns since the last update and format the string representation."""
    if last_update_turn == 0:
        turns_val = current_turn
        turns_since_update = f"{current_turn} turns ago (at the start of the game)"
    else:
        turns_val = current_turn - last_update_turn
        turns_since_update = f"{turns_val} turn ago" if turns_val == 1 else f"{turns_val} turns ago"
    return turns_val, turns_since_update


class AgentState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], add_messages]
    rpg_state: dict[str, Any]
    sandbox_timeout: float
    iteration_count: int

def _build_llm_node(
    api_key: str,
    base_url: str,
    model: str,
    max_iterations: int,
    sandbox_timeout: float,
    state_container: dict[str, Any],
    temperature: float | None = None,
):
    """Return the LLM node callable."""
    async def llm_node(state: AgentState, config: RunnableConfig) -> dict:
        stream_queue = config.get("configurable", {}).get("stream_queue")
        bundle_plan_fired = config.get("configurable", {}).get("bundle_plan_fired", False)
        bundle_summary_fired = config.get("configurable", {}).get("bundle_summary_fired", False)
        bundle_cleanup_fired = config.get("configurable", {}).get("bundle_cleanup_fired", False)

        # Check if the tools have already been invoked in the current turn (since the last user message)
        plan_called = False
        summary_called = False
        last_human_idx = -1
        for idx, msg in enumerate(state["messages"]):
            if isinstance(msg, HumanMessage):
                last_human_idx = idx

        messages_to_scan = state["messages"][last_human_idx + 1:] if last_human_idx != -1 else state["messages"]
        for msg in messages_to_scan:
            if isinstance(msg, AIMessage) and msg.tool_calls:
                for tc in msg.tool_calls:
                    if tc.get("name") == "update_plan":
                        plan_called = True
                    elif tc.get("name") == "append_summary":
                        summary_called = True

        # Override trigger flags if they have already been executed
        if plan_called:
            bundle_plan_fired = False
        if summary_called:
            bundle_summary_fired = False

        # 1. Inject the Dynamic System Instruction warning the LLM about the remaining budget
        rem_iterations = max(0, max_iterations - state["iteration_count"] - 1)
        current_rpg_state = state_container.get("rpg_state", {})
        turn_number = sum(1 for m in state["messages"] if isinstance(m, AIMessage)) + 1

        session_id = config.get("configurable", {}).get("session_id") or state_container.get("session_id")
        session_kwargs = {}
        if session_id:
            from rachel.core.session import get_session_caching_info
            caching_info = get_session_caching_info(session_id)
            session_kwargs = {
                "session_id": caching_info["session_id"],
                "prompt_cache_key": caching_info["prompt_cache_key"],
                "user": caching_info["user"],
            }
            if "hidden_state" not in current_rpg_state or not isinstance(current_rpg_state["hidden_state"], dict):
                current_rpg_state["hidden_state"] = {}
            current_rpg_state["hidden_state"]["session_info"] = caching_info

        system_instruction = _GraphDelegate.get_system_instruction(
            rpg_state=current_rpg_state,
            sandbox_timeout=sandbox_timeout,
            max_iterations=max_iterations,
            current_iteration=state["iteration_count"] + 1,
            rem_iterations=rem_iterations,
            messages=state["messages"],
            engine_name=get_sandbox_engine().name,
            bundle_plan_fired=bundle_plan_fired,
            bundle_summary_fired=bundle_summary_fired,
            bundle_cleanup_fired=bundle_cleanup_fired,
            turn_number=turn_number,
        )

        openai_msgs = convert_to_openai_messages(
            state["messages"],
            turn_numbers=state_container.get("turn_numbers"),
        )
        
        found_user = False
        for msg in reversed(openai_msgs):
            if msg.get("role") == "user":
                orig_content = msg.get("content") or ""
                instruction_block = (
                    f"\n\n---\n"
                    f"[RPG DIRECTIVE & GAME STATE (Turn {turn_number})]\n"
                    f"{system_instruction}"
                )
                msg["content"] = orig_content + instruction_block
                found_user = True
                break
                
        if not found_user:
            openai_msgs.append({"role": "system", "content": system_instruction})

        # 2. Call OpenRouter
        content, reasoning, tcs = await _GraphDelegate.call_openrouter_streaming(
            api_key=api_key,
            base_url=base_url,
            model=model,
            openai_messages=openai_msgs,
            stream_queue=stream_queue,
            include_plan=bundle_plan_fired,
            include_summary=bundle_summary_fired,
            temperature=temperature,
            **session_kwargs,
        )

        # Strip accidental Turn X prefix from the generated content
        if content:
            pattern = re.compile(
                r"^\s*(?:\[proxy:[^\]]*\]\s*)*(?:(?:\*\*|###|#|\(|\[)?\s*Turn\s*\d+\s*[:\-\)]?\s*(?:\*\*|\]|\))?\s*)*",
                re.IGNORECASE
            )
            content = pattern.sub("", content).strip()

        # Convert tool calls to LangChain format
        lc_tool_calls = []
        for tc in tcs:
            raw_args = tc.get("function", {}).get("arguments", "")
            try:
                args = json.loads(raw_args) if raw_args else {}
            except json.JSONDecodeError as exc:
                args = {
                    "_invalid_json_error": f"JSONDecodeError: {exc}",
                    "_raw_arguments": raw_args,
                }
            lc_tool_calls.append({
                "name": tc["function"]["name"],
                "args": args,
                "id": tc["id"],
                "type": "tool_call"
            })

        ai_msg = AIMessage(
            content=content,
            tool_calls=lc_tool_calls,
            additional_kwargs={"reasoning_content": reasoning} if reasoning else {}
        )

        return {
            "messages": [ai_msg],
            "iteration_count": state["iteration_count"] + 1,
        }
    return llm_node

def _build_summary_node(api_key: str, state_container: dict[str, Any], base_url: str | None = None):
    """Return the Summary node callable."""
    async def summary_node(state: AgentState, config: RunnableConfig) -> dict:
        from rachel.config import (
            SUMMARY_MODEL,
            SUMMARY_BASE_URL,
            SUMMARY_TEMPERATURE,
            SUMMARY_TARGET_WORDS,
        )

        rpg = state_container["rpg_state"]
        current_turn = sum(1 for m in state["messages"] if isinstance(m, AIMessage)) + 1
        last_summary_turn = state_container.get("last_summary_turn", 0)

        session_id = config.get("configurable", {}).get("session_id") or state_container.get("session_id")
        session_kwargs = {}
        if session_id:
            from rachel.core.session import get_session_caching_info
            caching_info = get_session_caching_info(session_id)
            session_kwargs = {
                "session_id": caching_info["session_id"],
                "prompt_cache_key": caching_info["prompt_cache_key"],
                "user": caching_info["user"],
            }

        summary_turns_val, turns_since_update = _calculate_turns_since_update(current_turn, last_summary_turn)

        range_ref = get_range_reference(state["messages"], summary_turns_val)
        prev_summary = rpg.get("summary", "")
        summary_prompt = get_summary_prompt(
            prev_summary=prev_summary,
            target_words=SUMMARY_TARGET_WORDS,
            turns_since_update=turns_since_update,
            range_ref=range_ref,
            state=rpg.get("state", {}),
            hidden_state=rpg.get("hidden_state", {}),
            is_bundle=False,
        )

        middled_msgs = middle_out_messages(state["messages"], summary_turns_val)
        history_msgs = convert_to_openai_messages(middled_msgs)
        history_msgs.append({"role": "system", "content": summary_prompt})

        try:
            summary_delta = await _GraphDelegate.call_openrouter_direct(
                api_key=api_key,
                base_url=base_url or SUMMARY_BASE_URL,
                model=SUMMARY_MODEL,
                openai_messages=history_msgs,
                temperature=SUMMARY_TEMPERATURE,
                **session_kwargs,
            )
            summary_delta = summary_delta.strip()
            if summary_delta.startswith('"') and summary_delta.endswith('"'):
                summary_delta = summary_delta[1:-1].strip()
            if prev_summary:
                rpg["summary"] = prev_summary.strip() + "\n\n" + summary_delta
            else:
                rpg["summary"] = summary_delta

            state_container["last_summary_turn"] = current_turn

            logger.info("Graph Summary node update complete: %s", summary_delta)
        except Exception as exc:
            logger.error("Failed to run summary node update: %s", exc)

        return {"rpg_state": rpg}
    return summary_node

def _build_plan_node(api_key: str, state_container: dict[str, Any], base_url: str | None = None):
    """Return the Plan node callable."""
    async def plan_node(state: AgentState, config: RunnableConfig) -> dict:
        from rachel.config import (
            PLAN_MODEL,
            PLAN_BASE_URL,
            PLAN_TEMPERATURE,
            PLAN_MAX_RETRIES,
        )

        rpg = state_container["rpg_state"]
        current_turn = sum(1 for m in state["messages"] if isinstance(m, AIMessage)) + 1
        last_plan_turn = state_container.get("last_plan_turn", 0)

        session_id = config.get("configurable", {}).get("session_id") or state_container.get("session_id")
        session_kwargs = {}
        if session_id:
            from rachel.core.session import get_session_caching_info
            caching_info = get_session_caching_info(session_id)
            session_kwargs = {
                "session_id": caching_info["session_id"],
                "prompt_cache_key": caching_info["prompt_cache_key"],
                "user": caching_info["user"],
            }

        plan_turns_val, turns_since_update = _calculate_turns_since_update(current_turn, last_plan_turn)

        range_ref = get_range_reference(state["messages"], plan_turns_val)
        prev_plan = rpg.get("plan", [])
        plan_prompt = get_plan_prompt(
            prev_plan=prev_plan,
            turns_since_update=turns_since_update,
            range_ref=range_ref,
            state=rpg.get("state", {}),
            hidden_state=rpg.get("hidden_state", {}),
            is_bundle=False,
        )

        middled_msgs = middle_out_messages(state["messages"], plan_turns_val)
        history_msgs = convert_to_openai_messages(middled_msgs)
        history_msgs.append({"role": "system", "content": plan_prompt})

        errors = []
        plan_updated = False
        max_retries = max(1, PLAN_MAX_RETRIES)
        for attempt in range(max_retries):
            current_msgs = list(history_msgs)
            if errors:
                error_context = "\n".join(errors)
                current_msgs.append({
                    "role": "system",
                    "content": f"The previous attempt failed with the following error(s):\n{error_context}\n\nPlease try again and output ONLY a valid JSON array matching the requested schema."
                })

            try:
                plan_response = await _GraphDelegate.call_openrouter_direct(
                    api_key=api_key,
                    base_url=base_url or PLAN_BASE_URL,
                    model=PLAN_MODEL,
                    openai_messages=current_msgs,
                    temperature=PLAN_TEMPERATURE,
                    **session_kwargs,
                )
                clean_resp = _strip_fenced_code_block(plan_response)

                new_plan = json.loads(clean_resp)
                if not isinstance(new_plan, list):
                    raise ValueError("Output must be a JSON array of objects.")

                normalized = []
                for idx, item in enumerate(new_plan, 1):
                    if isinstance(item, dict):
                        desc = item.get("description") or ""
                        remark = item.get("remark") or ""
                        item_id = item.get("id", idx)
                        status = item.get("status", "to-do")
                    else:
                        desc = str(item)
                        remark = ""
                        item_id = idx
                        status = "to-do"

                    if len(desc) > 500:
                        raise ValueError(f"Plan item description at index {idx} exceeds 500 characters limit ({len(desc)} characters).")
                    if len(remark) > 500:
                        raise ValueError(f"Plan item remark at index {idx} exceeds 500 characters limit ({len(remark)} characters).")

                    normalized.append({
                        "id": item_id,
                        "description": desc,
                        "status": status,
                        "remark": remark,
                    })

                rpg["plan"] = normalized

                state_container["last_plan_turn"] = current_turn

                logger.info("Graph Plan node update complete: %s", rpg["plan"])
                plan_updated = True
                break
            except Exception as exc:
                err_msg = f"Attempt {attempt + 1} failed: {str(exc)}"
                logger.warning("Plan update retry loop warning: %s", err_msg)
                errors.append(err_msg)

        if not plan_updated:
            logger.error("Failed to run plan node update after %d attempts. Errors: %s", max_retries, errors)

        return {"rpg_state": rpg}
    return plan_node

def _build_cleanup_node(api_key: str, state_container: dict[str, Any], sandbox_timeout: float, base_url: str | None = None):
    """Return the Cleanup node callable."""
    async def cleanup_node(state: AgentState, config: RunnableConfig) -> dict:
        import copy
        from rachel.config import (
            CLEANUP_MODEL,
            CLEANUP_BASE_URL,
            CLEANUP_TEMPERATURE,
            CLEANUP_MAX_RETRIES,
            MAX_DEPTH,
            MAX_WIDTH,
            MAX_STRING_LENGTH,
        )
        from rachel.agent.prompts import get_cleanup_prompt
        from rachel.sandbox.validation import validate_state_constraints

        engine = get_sandbox_engine()
        rpg = state_container["rpg_state"]
        current_turn = sum(1 for m in state["messages"] if isinstance(m, AIMessage)) + 1

        session_id = config.get("configurable", {}).get("session_id") or state_container.get("session_id")
        session_kwargs = {}
        if session_id:
            from rachel.core.session import get_session_caching_info
            caching_info = get_session_caching_info(session_id)
            session_kwargs = {
                "session_id": caching_info["session_id"],
                "prompt_cache_key": caching_info["prompt_cache_key"],
                "user": caching_info["user"],
            }

        orig_state = copy.deepcopy(rpg.get("state", {})) if isinstance(rpg, dict) else {}
        orig_hidden = copy.deepcopy(rpg.get("hidden_state", {})) if isinstance(rpg, dict) else {}

        errors = []
        cleanup_updated = False
        max_retries = max(1, CLEANUP_MAX_RETRIES)
        for attempt in range(max_retries):
            # Recalculate prompt incorporating errors if any
            cleanup_prompt = get_cleanup_prompt(
                state=orig_state,
                hidden_state=orig_hidden,
                engine_name=engine.name,
                is_bundle=False,
            )
            if errors:
                error_context = "\n".join(errors)
                cleanup_prompt += (
                    f"\n\n[ERROR FROM PREVIOUS CODE RUN]:\n{error_context}\n\n"
                    f"Please correct your {engine.name.upper()} script and try again."
                )

            history_msgs = [{"role": "system", "content": cleanup_prompt}]

            try:
                code_response = await _GraphDelegate.call_openrouter_direct(
                    api_key=api_key,
                    base_url=base_url or CLEANUP_BASE_URL,
                    model=CLEANUP_MODEL,
                    openai_messages=history_msgs,
                    temperature=CLEANUP_TEMPERATURE,
                    **session_kwargs,
                )
                code = _strip_fenced_code_block(code_response)

                # Execute sandbox code
                if isinstance(rpg, dict) and all(k in rpg for k in ("state", "plan", "summary", "hidden_state")):
                    wrapper = {
                        "state": copy.deepcopy(orig_state),
                        "hidden_state": copy.deepcopy(orig_hidden),
                    }
                    updated, output = engine.execute(code, wrapper, sandbox_timeout)
                    if output and "--- Sandbox Exception ---" in output:
                        raise ValueError(f"Cleanup script execution failed:\n{output}")
                    if output and "[Sandbox timed out" in output:
                        raise ValueError("Cleanup script execution timed out.")

                    if not isinstance(updated, dict) or "state" not in updated or "hidden_state" not in updated:
                        raise ValueError("Cleanup script execution did not return a dictionary object with both 'state' and 'hidden_state' keys.")

                    # Validate state constraints on mutated objects
                    validate_state_constraints(updated["state"], MAX_DEPTH, MAX_WIDTH, MAX_STRING_LENGTH, "state")
                    validate_state_constraints(updated["hidden_state"], MAX_DEPTH, MAX_WIDTH, MAX_STRING_LENGTH, "hidden_state")

                    rpg["state"] = updated["state"]
                    rpg["hidden_state"] = updated["hidden_state"]
                else:
                    orig_rpg = copy.deepcopy(rpg)
                    updated, output = engine.execute(code, orig_rpg, sandbox_timeout)
                    if output and "--- Sandbox Exception ---" in output:
                        raise ValueError(f"Cleanup script execution failed:\n{output}")
                    if output and "[Sandbox timed out" in output:
                        raise ValueError("Cleanup script execution timed out.")

                    validate_state_constraints(updated, MAX_DEPTH, MAX_WIDTH, MAX_STRING_LENGTH, "state")
                    state_container["rpg_state"] = updated

                state_container["last_cleanup_turn"] = current_turn

                logger.info("Graph Cleanup node execution complete. Sandbox Output: %s", output or "<none>")
                cleanup_updated = True
                break
            except Exception as exc:
                err_msg = f"Attempt {attempt + 1} failed: {str(exc)}"
                logger.warning("Cleanup retry loop warning: %s", err_msg)
                errors.append(err_msg)

        if not cleanup_updated:
            logger.error("Failed to run cleanup node after %d attempts. Errors: %s", max_retries, errors)
            # Revert states to originals in case we modified the containers partially
            if isinstance(rpg, dict) and "state" in rpg and "hidden_state" in rpg:
                rpg["state"] = orig_state
                rpg["hidden_state"] = orig_hidden

        return {"rpg_state": rpg}
    return cleanup_node

def _build_tool_node(tools: list):
    """Return the Tool node callable."""
    tool_map = {t.name: t for t in tools}

    async def tool_node(state: AgentState, config: RunnableConfig) -> dict:
        stream_queue = config.get("configurable", {}).get("stream_queue")
        last_message = state["messages"][-1]
        tool_results: list[ToolMessage] = []

        tool_calls = getattr(last_message, "tool_calls", None) or []
        for call in tool_calls:
            tool_fn = tool_map.get(call["name"])
            if tool_fn is None:
                result = f"[Unknown tool: {call['name']}]"
                if stream_queue:
                    await stream_queue.put(("tool_log", f"\n[Unknown tool call: {call['name']}]\n"))
            else:
                args_str = json.dumps(call["args"], ensure_ascii=False)
                if stream_queue:
                    await stream_queue.put((
                        "tool_log",
                        f"\n[Calling tool: {call['name']} with args: {args_str}]\n"
                    ))
                try:
                    if isinstance(call.get("args"), dict) and "_invalid_json_error" in call["args"]:
                        err_msg = call["args"]["_invalid_json_error"]
                        raw_args = call["args"].get("_raw_arguments", "")
                        result = (
                            f"--- Tool Execution Exception ---\n"
                            f"{err_msg}\n"
                            f"Raw arguments: '{raw_args}'\n"
                            f"Notice: The tool parameters could not be parsed as valid JSON. "
                            f"Please adjust your parameters to valid JSON format matching the schema and re-attempt."
                        )
                    else:
                        result = await tool_fn.ainvoke(call["args"])
                except Exception as exc:
                    logger.warning("Tool execution error for tool '%s': %s", call["name"], exc, exc_info=True)
                    result = (
                        f"--- Tool Execution Exception ---\n"
                        f"{type(exc).__name__}: {exc}\n"
                        f"Notice: The tool call failed due to invalid arguments or an internal error. "
                        f"Please review the error and parameter requirements, then re-attempt."
                    )
                if stream_queue:
                    await stream_queue.put((
                        "tool_log",
                        f"[Output]: {result}\n"
                    ))
            tool_results.append(
                ToolMessage(content=str(result), tool_call_id=call["id"], name=call["name"])
            )
        return {"messages": tool_results}

    return tool_node

def _should_continue(max_iterations: int):
    """Return the conditional edge function."""
    def _edge(state: AgentState) -> str:
        last = state["messages"][-1]
        if not isinstance(last, AIMessage):
            return "llm"
        has_tool_calls = bool(getattr(last, "tool_calls", None))
        over_limit = state["iteration_count"] >= max_iterations
        if has_tool_calls and not over_limit:
            return "tools"
        return "route_end"
    return _edge


def _build_pre_action_node(api_key: str, state_container: dict[str, Any], sandbox_timeout: float, base_url: str | None = None):
    """Return a node that executes Plan, Summary, and Cleanup concurrently if triggered."""
    summary_fn = _build_summary_node(api_key, state_container, base_url=base_url)
    plan_fn = _build_plan_node(api_key, state_container, base_url=base_url)
    cleanup_fn = _build_cleanup_node(api_key, state_container, sandbox_timeout, base_url=base_url)

    async def pre_action_node(state: AgentState, config: RunnableConfig) -> dict:
        import asyncio
        tasks = []
        conf = config.get("configurable", {})
        if conf.get("plan_fired", False):
            tasks.append(plan_fn(state, config))
        if conf.get("summary_fired", False):
            tasks.append(summary_fn(state, config))
        if conf.get("cleanup_fired", False):
            tasks.append(cleanup_fn(state, config))

        if tasks:
            await asyncio.gather(*tasks)

        return {"rpg_state": state_container["rpg_state"]}
    return pre_action_node


def _build_route_end_node():
    """Return the final housekeeping node callable."""
    async def route_end_node(state: AgentState, config: RunnableConfig) -> dict:
        logger.info("Housekeeping end node reached.")
        return {"rpg_state": state.get("rpg_state", {})}
    return route_end_node

def _convert_messages(openai_messages: list[dict]) -> list[BaseMessage]:
    """Convert OpenAI-format message dicts to LangChain BaseMessage objects."""
    lc_messages: list[BaseMessage] = []
    for m in openai_messages:
        role = m.get("role", "system")
        content = m.get("content") or ""
        if role == "system":
            lc_messages.append(SystemMessage(content=content))
        elif role == "assistant":
            # Reconstruct reasoning content if present in history
            additional = {}
            if "reasoning_content" in m:
                additional["reasoning_content"] = m["reasoning_content"]
            lc_messages.append(AIMessage(content=content, additional_kwargs=additional))
        else:
            lc_messages.append(HumanMessage(content=content))
    return lc_messages
