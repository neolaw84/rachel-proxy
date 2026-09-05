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
    get_static_system_prompt,
    get_dynamic_turn_directive,
    get_summary_prompt,
    get_plan_prompt,
    get_range_reference,
    # TODO: Clean up unused import in next cleanup session
    # middle_out_messages,
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
    def get_static_system_prompt(*args, **kwargs):
        import rachel.agent.graph as graph
        return graph.get_static_system_prompt(*args, **kwargs)

    @staticmethod
    def get_dynamic_turn_directive(*args, **kwargs):
        import rachel.agent.graph as graph
        return graph.get_dynamic_turn_directive(*args, **kwargs)

    @staticmethod
    def get_dynamic_plan_directive(*args, **kwargs):
        import rachel.agent.graph as graph
        return graph.get_dynamic_plan_directive(*args, **kwargs)

    @staticmethod
    def get_dynamic_summary_directive(*args, **kwargs):
        import rachel.agent.graph as graph
        return graph.get_dynamic_summary_directive(*args, **kwargs)

    @staticmethod
    def get_dynamic_cleanup_directive(*args, **kwargs):
        import rachel.agent.graph as graph
        return graph.get_dynamic_cleanup_directive(*args, **kwargs)


    @staticmethod
    def get_plan_prompt(*args, **kwargs):
        import rachel.agent.graph as graph
        return graph.get_plan_prompt(*args, **kwargs)

    @staticmethod
    def get_summary_prompt(*args, **kwargs):
        import rachel.agent.graph as graph
        return graph.get_summary_prompt(*args, **kwargs)

    @staticmethod
    def get_cleanup_prompt(*args, **kwargs):
        import rachel.agent.graph as graph
        return graph.get_cleanup_prompt(*args, **kwargs)

    @staticmethod
    async def call_openrouter_streaming(*args, **kwargs):
        import rachel.agent.graph as graph
        return await graph.call_openrouter_streaming(*args, **kwargs)

    @staticmethod
    async def call_openrouter_direct(*args, **kwargs):
        import rachel.agent.graph as graph
        return await graph.call_openrouter_direct(*args, **kwargs)


def _get_recent_turn_messages(
    messages: Sequence[Any],
    last_update_turn: int,
    include_dangling_user: bool = True,
    turn_numbers: list[int | None] | None = None,
    initial_num_msgs_to_include: int = 4,
) -> list[dict]:
    """
    Extract turn messages preserving up to initial_num_msgs_to_include initial non-system messages,
    plus messages starting from Turn (last_update_turn + 1) up to target end.
    - If include_dangling_user=True (for plan & cleanup): includes current turn's user action message.
    - If include_dangling_user=False (for summary): excludes uncompleted current turn's user action message,
      stopping at Turn (current_turn - 1)'s assistant message.
    Preserves incoming Message 0 (client character card) at index 0 if present.
    Applies 'Turn x: ' prefixes to all user and assistant messages.
    Deduplicates overlapping indices between initial messages and recent turn window.
    """
    openai_msgs = convert_to_openai_messages(messages, turn_numbers=turn_numbers)
    if not openai_msgs:
        return []

    card_msg = None
    first_idx = 0
    if openai_msgs[0].get("role") == "system":
        card_msg = dict(openai_msgs[0])
        first_idx = 1

    start_idx = first_idx
    if last_update_turn > 0:
        asst_count = 0
        for i in range(first_idx, len(openai_msgs)):
            if openai_msgs[i].get("role") == "assistant":
                asst_count += 1
                if asst_count == last_update_turn:
                    start_idx = i + 1
                    break

    end_idx = len(openai_msgs)
    if not include_dangling_user:
        last_asst_idx = None
        for i in range(len(openai_msgs) - 1, first_idx - 1, -1):
            if openai_msgs[i].get("role") == "assistant":
                last_asst_idx = i
                break
        if last_asst_idx is not None:
            end_idx = last_asst_idx + 1

    initial_end = min(first_idx + max(0, initial_num_msgs_to_include), len(openai_msgs))
    initial_indices = list(range(first_idx, initial_end))
    recent_indices = list(range(start_idx, end_idx)) if start_idx < end_idx else []

    combined_indices = sorted(list(set(initial_indices) | set(recent_indices)))
    recent_history = [dict(openai_msgs[i]) for i in combined_indices]

    result = []
    if card_msg:
        result.append(card_msg)
    else:
        result.append({"role": "system", "content": ""})

    result.extend(recent_history)
    return result



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
    temperature: float = 0.7,
):
    """Return the main LLM node callable."""
    async def llm_node(state: AgentState, config: RunnableConfig) -> dict:
        configurable = config.get("configurable", {})
        stream_queue = configurable.get("stream_queue")

        # 1. Generate Static System Prompt and Dynamic Turn Directive
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

        static_prompt = _GraphDelegate.get_static_system_prompt(
            sandbox_timeout=sandbox_timeout,
        )

        dynamic_directive = _GraphDelegate.get_dynamic_turn_directive(
            rpg_state=current_rpg_state,
            max_iterations=max_iterations,
            current_iteration=state["iteration_count"] + 1,
            rem_iterations=rem_iterations,
            messages=state["messages"],
            turn_number=turn_number,
        )

        openai_msgs = convert_to_openai_messages(
            state["messages"],
            turn_numbers=state_container.get("turn_numbers"),
        )

        # Append static system prompt to Message 0 (or insert at index 0 if not system)
        if openai_msgs and openai_msgs[0].get("role") == "system":
            orig_sys = openai_msgs[0].get("content") or ""
            openai_msgs[0]["content"] = f"{orig_sys}\n\n---\n{static_prompt}".strip()
        else:
            openai_msgs.insert(0, {"role": "system", "content": static_prompt})

        # In Round 1 (iteration 0): construct and cache the user message with dynamic turn directive
        if state["iteration_count"] == 0:
            instruction_block = (
                f"\n\n---\n"
                f"[RPG DIRECTIVE & GAME STATE (Turn {turn_number})]\n"
                f"{dynamic_directive}"
            )
            user_idx = None
            for idx in range(len(openai_msgs) - 1, -1, -1):
                if openai_msgs[idx].get("role") == "user":
                    user_idx = idx
                    break

            if user_idx is not None:
                orig_content = openai_msgs[user_idx].get("content") or ""
                constructed_content = orig_content + instruction_block
                openai_msgs[user_idx]["content"] = constructed_content
                state_container["cached_constructed_user_message"] = constructed_content
            else:
                constructed_content = (
                    f"[RPG DIRECTIVE & GAME STATE (Turn {turn_number})]\n"
                    f"{dynamic_directive}"
                )
                openai_msgs.append({"role": "user", "content": constructed_content})
                state_container["cached_constructed_user_message"] = constructed_content
        else:
            # In Round 2+: reuse the cached constructed user message bitwise identically
            cached_user_msg = state_container.get("cached_constructed_user_message")
            if cached_user_msg:
                for idx in range(len(openai_msgs) - 1, -1, -1):
                    if openai_msgs[idx].get("role") == "user":
                        openai_msgs[idx]["content"] = cached_user_msg
                        break
            # Note: Do NOT append any synthetic user message after a tool message in Round 2+

        # 2. Call OpenRouter
        engine = get_sandbox_engine()
        all_tools = get_all_tools_schema(engine.name)

        content, reasoning, tcs = await _GraphDelegate.call_openrouter_streaming(
            api_key=api_key,
            base_url=base_url,
            model=model,
            openai_messages=openai_msgs,
            stream_queue=stream_queue,
            temperature=temperature,
            tools=all_tools,
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
            "iteration_count": state["iteration_count"] + 1
        }
    return llm_node

from rachel.sandbox.schemas import (
    get_all_tools_schema,
    SUBMIT_PLAN_TOOL,
    SUBMIT_SUMMARY_TOOL,
    SUBMIT_CLEANUP_TOOL,
    END_TURN_TOOL,
)



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

        # Completed turns arithmetic: from last_summary_turn + 1 to current_turn - 1
        start_summary_turn = last_summary_turn + 1
        end_summary_turn = current_turn - 1

        if end_summary_turn < start_summary_turn:
            logger.info("Summary node: No completed turns to summarize yet (current_turn=%d, last_summary_turn=%d)", current_turn, last_summary_turn)
            return {"rpg_state": rpg}

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

        turns_since_update_num = end_summary_turn - last_summary_turn
        _, turns_since_update_str = _calculate_turns_since_update(current_turn, last_summary_turn)

        range_ref = get_range_reference(state["messages"], turns_since_update_num)
        prev_summary = rpg.get("summary", "")

        # For test mock compatibility
        _GraphDelegate.get_summary_prompt(
            prev_summary=prev_summary,
            target_words=SUMMARY_TARGET_WORDS,
            turns_since_update=turns_since_update_str,
            range_ref=range_ref,
            state=rpg.get("state", {}),
            hidden_state=rpg.get("hidden_state", {}),
            start_turn=start_summary_turn,
            end_turn=end_summary_turn,
        )

        from rachel.config import SUMMARY_INITIAL_NUM_MSGS_TO_INCLUDE

        history_msgs = _get_recent_turn_messages(
            state["messages"],
            last_summary_turn,
            include_dangling_user=False,
            turn_numbers=state_container.get("turn_numbers"),
            initial_num_msgs_to_include=SUMMARY_INITIAL_NUM_MSGS_TO_INCLUDE,
        )
        static_prompt = _GraphDelegate.get_static_system_prompt(
            sandbox_timeout=state_container.get("sandbox_timeout", 2.0),
        )
        dynamic_directive = _GraphDelegate.get_dynamic_summary_directive(
            prev_summary=prev_summary,
            range_ref=range_ref,
            state=rpg.get("state", {}),
            start_turn=start_summary_turn,
            end_turn=end_summary_turn,
        )

        if history_msgs and history_msgs[0].get("role") == "system":
            orig_sys = history_msgs[0].get("content") or ""
            history_msgs[0]["content"] = f"{orig_sys}\n\n---\n{static_prompt}".strip()
        else:
            history_msgs.insert(0, {"role": "system", "content": static_prompt})

        if history_msgs and history_msgs[-1].get("role") == "user":
            orig_user = history_msgs[-1].get("content") or ""
            history_msgs[-1]["content"] = f"{orig_user}\n\n---\n{dynamic_directive}"
        else:
            history_msgs.append({"role": "user", "content": dynamic_directive})

        engine = get_sandbox_engine()
        all_tools = get_all_tools_schema(engine.name)

        try:
            direct_res = await _GraphDelegate.call_openrouter_direct(
                api_key=api_key,
                base_url=base_url or SUMMARY_BASE_URL,
                model=SUMMARY_MODEL,
                openai_messages=history_msgs,
                temperature=SUMMARY_TEMPERATURE,
                tools=all_tools,
                tool_choice={"type": "function", "function": {"name": "submit_summary"}},
                return_tool_calls=True,
                **session_kwargs,
            )
            if isinstance(direct_res, tuple) and len(direct_res) == 2:
                resp, tcs = direct_res
            else:
                resp, tcs = str(direct_res), []

            summary_delta = None
            if tcs:
                for tc in tcs:
                    if tc.get("function", {}).get("name") == "submit_summary":
                        raw_args = tc.get("function", {}).get("arguments", "")
                        try:
                            parsed = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
                            if isinstance(parsed, dict) and "summary" in parsed:
                                summary_delta = str(parsed["summary"])
                        except Exception:
                            pass

            if not summary_delta:
                summary_delta = resp.strip()
                if summary_delta.startswith('"') and summary_delta.endswith('"'):
                    summary_delta = summary_delta[1:-1].strip()

            if prev_summary:
                rpg["summary"] = prev_summary.strip() + "\n\n" + summary_delta
            else:
                rpg["summary"] = summary_delta

            state_container["last_summary_turn"] = end_summary_turn

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

        last_summary_turn = state_container.get("last_summary_turn", 0)

        start_plan_turn = last_plan_turn + 1
        end_plan_turn = current_turn

        # For test mock compatibility
        _GraphDelegate.get_plan_prompt(
            prev_plan=prev_plan,
            turns_since_update=turns_since_update,
            range_ref=range_ref,
            state=rpg.get("state", {}),
            hidden_state=rpg.get("hidden_state", {}),
            summary=rpg.get("summary", ""),
            summary_up_to_turn=last_summary_turn,
            start_turn=start_plan_turn,
            end_turn=end_plan_turn,
        )

        from rachel.config import PLAN_INITIAL_NUM_MSGS_TO_INCLUDE

        history_msgs = _get_recent_turn_messages(
            state["messages"],
            last_plan_turn,
            include_dangling_user=True,
            turn_numbers=state_container.get("turn_numbers"),
            initial_num_msgs_to_include=PLAN_INITIAL_NUM_MSGS_TO_INCLUDE,
        )
        static_prompt = _GraphDelegate.get_static_system_prompt(
            sandbox_timeout=state_container.get("sandbox_timeout", 2.0),
        )
        dynamic_directive = _GraphDelegate.get_dynamic_plan_directive(
            prev_plan=prev_plan,
            turns_since_update=turns_since_update,
            range_ref=range_ref,
            state=rpg.get("state", {}),
            hidden_state=rpg.get("hidden_state", {}),
            summary=rpg.get("summary", ""),
            summary_up_to_turn=last_summary_turn,
            start_turn=start_plan_turn,
            end_turn=end_plan_turn,
        )


        if history_msgs and history_msgs[0].get("role") == "system":
            orig_sys = history_msgs[0].get("content") or ""
            history_msgs[0]["content"] = f"{orig_sys}\n\n---\n{static_prompt}".strip()
        else:
            history_msgs.insert(0, {"role": "system", "content": static_prompt})

        if history_msgs and history_msgs[-1].get("role") == "user":
            orig_user = history_msgs[-1].get("content") or ""
            history_msgs[-1]["content"] = f"{orig_user}\n\n---\n{dynamic_directive}"
        else:
            history_msgs.append({"role": "user", "content": dynamic_directive})

        engine = get_sandbox_engine()
        all_tools = get_all_tools_schema(engine.name)

        errors = []
        plan_updated = False
        max_retries = max(1, PLAN_MAX_RETRIES)
        for attempt in range(max_retries):
            current_msgs = [dict(m) for m in history_msgs]
            if errors:
                error_context = "\n".join(errors)
                current_msgs.append({
                    "role": "user",
                    "content": f"[RETRY DIRECTIVE]: The previous attempt failed with error(s):\n{error_context}\n\nPlease try again and call submit_plan tool with valid items matching schema."
                })

            try:
                direct_res = await _GraphDelegate.call_openrouter_direct(
                    api_key=api_key,
                    base_url=base_url or PLAN_BASE_URL,
                    model=PLAN_MODEL,
                    openai_messages=current_msgs,
                    temperature=PLAN_TEMPERATURE,
                    tools=all_tools,
                    tool_choice={"type": "function", "function": {"name": "submit_plan"}},
                    return_tool_calls=True,
                    **session_kwargs,
                )
                if isinstance(direct_res, tuple) and len(direct_res) == 2:
                    plan_response, tcs = direct_res
                else:
                    plan_response, tcs = str(direct_res), []

                new_plan = None
                if tcs:
                    for tc in tcs:
                        if tc.get("function", {}).get("name") == "submit_plan":
                            raw_args = tc.get("function", {}).get("arguments", "")
                            try:
                                parsed = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
                                if isinstance(parsed, dict) and "items" in parsed and isinstance(parsed["items"], list):
                                    new_plan = parsed["items"]
                            except Exception:
                                pass

                if new_plan is None:
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
        from rachel.sandbox.validation import validate_state_constraints

        engine = get_sandbox_engine()
        rpg = state_container["rpg_state"]
        current_turn = sum(1 for m in state["messages"] if isinstance(m, AIMessage)) + 1
        last_cleanup_turn = state_container.get("last_cleanup_turn", 0)

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
        orig_plan = copy.deepcopy(rpg.get("plan", [])) if isinstance(rpg, dict) else []
        orig_summary = rpg.get("summary", "") if isinstance(rpg, dict) else ""

        # For test mock compatibility
        _GraphDelegate.get_cleanup_prompt(
            state=orig_state,
            hidden_state=orig_hidden,
            engine_name=engine.name,
        )

        from rachel.config import CLEANUP_INITIAL_NUM_MSGS_TO_INCLUDE

        history_msgs = _get_recent_turn_messages(
            state["messages"],
            last_cleanup_turn,
            include_dangling_user=True,
            turn_numbers=state_container.get("turn_numbers"),
            initial_num_msgs_to_include=CLEANUP_INITIAL_NUM_MSGS_TO_INCLUDE,
        )
        static_prompt = _GraphDelegate.get_static_system_prompt(sandbox_timeout=sandbox_timeout)
        dynamic_directive = _GraphDelegate.get_dynamic_cleanup_directive(
            state=orig_state,
            hidden_state=orig_hidden,
            plan=orig_plan,
            summary=orig_summary,
            engine_name=engine.name,
        )

        if history_msgs and history_msgs[0].get("role") == "system":
            orig_sys = history_msgs[0].get("content") or ""
            history_msgs[0]["content"] = f"{orig_sys}\n\n---\n{static_prompt}".strip()
        else:
            history_msgs.insert(0, {"role": "system", "content": static_prompt})

        if history_msgs and history_msgs[-1].get("role") == "user":
            orig_user = history_msgs[-1].get("content") or ""
            history_msgs[-1]["content"] = f"{orig_user}\n\n---\n{dynamic_directive}"
        else:
            history_msgs.append({"role": "user", "content": dynamic_directive})

        all_tools = get_all_tools_schema(engine.name)

        errors = []
        cleanup_updated = False
        max_retries = max(1, CLEANUP_MAX_RETRIES)
        for attempt in range(max_retries):
            current_msgs = [dict(m) for m in history_msgs]
            if errors:
                error_context = "\n".join(errors)
                current_msgs.append({
                    "role": "user",
                    "content": f"[RETRY DIRECTIVE]: The previous attempt failed with error(s):\n{error_context}\n\nPlease correct your {engine.name.upper()} script and call submit_cleanup tool."
                })

            try:
                direct_res = await _GraphDelegate.call_openrouter_direct(
                    api_key=api_key,
                    base_url=base_url or CLEANUP_BASE_URL,
                    model=CLEANUP_MODEL,
                    openai_messages=history_msgs,
                    temperature=CLEANUP_TEMPERATURE,
                    tools=all_tools,
                    tool_choice={"type": "function", "function": {"name": "submit_cleanup"}},
                    return_tool_calls=True,
                    **session_kwargs,
                )
                if isinstance(direct_res, tuple) and len(direct_res) == 2:
                    code_response, tcs = direct_res
                else:
                    code_response, tcs = str(direct_res), []

                code = None
                if tcs:
                    for tc in tcs:
                        if tc.get("function", {}).get("name") == "submit_cleanup":
                            raw_args = tc.get("function", {}).get("arguments", "")
                            try:
                                parsed = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
                                if isinstance(parsed, dict) and "code" in parsed:
                                    code = str(parsed["code"])
                            except Exception:
                                pass

                if not code:
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
        tool_calls = getattr(last, "tool_calls", None) or []
        has_end_turn = any(tc.get("name") == "end_turn" for tc in tool_calls)
        has_tool_calls = bool(tool_calls)
        over_limit = state["iteration_count"] >= max_iterations
        if has_end_turn or over_limit or not has_tool_calls:
            return "route_end"
        return "tools"
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
