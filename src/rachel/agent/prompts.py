"""System Prompt Templates for the RPG Proxy Agent."""

import json
import re
from typing import Any, Sequence
from langchain_core.messages import BaseMessage, AIMessage, SystemMessage
from rachel.agent.prompt_constants import (
    PROGRESS_STORY_TASK,
    PROGRESS_STORY_TASK_NO_END_TURN,
    PROGRESS_AGENCY_INSTRUCTIONS_END_TURN,
    PROGRESS_AGENCY_INSTRUCTIONS_DIRECT,
    STATE_SECTION_TEMPLATE,
    SANDBOX_INFO_V8,
    STATE_CONSTRAINTS_INFO_TEMPLATE,
    STATIC_SYSTEM_INSTRUCTION_TEMPLATE,
    DYNAMIC_TURN_DIRECTIVE_TEMPLATE,
    DYNAMIC_PLAN_DIRECTIVE_TEMPLATE,
    DYNAMIC_SUMMARY_DIRECTIVE_TEMPLATE,
    DYNAMIC_CLEANUP_DIRECTIVE_TEMPLATE,
)



class PromptBuilder:
    """Builder class responsible for constructing dynamic and static prompts with configurable constraints."""

    def __init__(
        self,
        max_string_length: int | None = None,
        max_width: int | None = None,
        max_depth: int | None = None,
        summary_target_words: int | None = None,
        plan_interval_turns: int | None = None,
    ):
        self._max_string_length = max_string_length
        self._max_width = max_width
        self._max_depth = max_depth
        self._summary_target_words = summary_target_words
        self._plan_interval_turns = plan_interval_turns

    def _resolve_config(self):
        import rachel.config as config
        msl = self._max_string_length if self._max_string_length is not None else config.MAX_STRING_LENGTH
        mw = self._max_width if self._max_width is not None else config.MAX_WIDTH
        md = self._max_depth if self._max_depth is not None else config.MAX_DEPTH
        stw = self._summary_target_words if self._summary_target_words is not None else config.SUMMARY_TARGET_WORDS
        pit = self._plan_interval_turns if self._plan_interval_turns is not None else getattr(config, "PLAN_INTERVAL_TURNS", 10)
        return msl, mw, md, stw, pit

    def get_static_system_prompt(
        self,
        sandbox_timeout: float = 2.0,
        engine_name: str = "v8",
        include_end_turn: bool = True,
    ) -> str:
        msl, mw, md, stw, pit = self._resolve_config()
        state_constraints_info = STATE_CONSTRAINTS_INFO_TEMPLATE.format(
            max_string_length=msl,
            max_width=mw,
            max_depth=md,
        )
        lang = "JavaScript" if engine_name == "v8" else "Python"
        agency_instructions = (
            PROGRESS_AGENCY_INSTRUCTIONS_END_TURN
            if include_end_turn
            else PROGRESS_AGENCY_INSTRUCTIONS_DIRECT
        )
        return STATIC_SYSTEM_INSTRUCTION_TEMPLATE.format(
            target_words=stw,
            plan_interval_turns=pit,
            lang=lang,
            sandbox_info=SANDBOX_INFO_V8,
            state_constraints_info=state_constraints_info,
            sandbox_timeout=sandbox_timeout,
            progress_agency_instructions=agency_instructions,
        )



def get_message_repr(message: BaseMessage, max_len: int = 150) -> str:
    """Format a single message as a clean single line for representation."""
    content = message.content or ""
    if not isinstance(content, str):
        content = str(content)
    # Strip proxy tags
    cleaned = re.sub(r"\[proxy:[^\]]*\]\n*", "", content, flags=re.IGNORECASE).strip()
    # Replace newlines/spaces with a single space
    single_line = re.sub(r"\s+", " ", cleaned)
    if len(single_line) > max_len:
        single_line = single_line[:max_len] + "..."
    return single_line

def get_range_reference(messages: Sequence[BaseMessage], turns_since_update: int) -> str:
    """Return a single range reference string like 'StartMsg ... EndMsg'."""
    if not messages:
        return ""
    num_messages = turns_since_update * 2
    num_messages = min(max(1, num_messages), len(messages))
    
    start_idx = len(messages) - num_messages
    end_idx = len(messages) - 1
    
    start_repr = get_message_repr(messages[start_idx])
    end_repr = get_message_repr(messages[end_idx])
    
    if start_idx == end_idx:
        return start_repr
    return f"{start_repr} ... {end_repr}"

# TODO: Clean up / re-evaluate middle_out_messages in next cleanup session (currently unwired in agent graph)
def middle_out_messages(
    messages: Sequence[BaseMessage],
    turns_since_update: int,
) -> list[BaseMessage]:
    """Middle-out messages history. Returns a list where the prefix of already-processed
    messages is condensed into a single SystemMessage representing the start and end of that prefix.
    """
    if not messages:
        return []
    
    num_recent = turns_since_update * 2
    num_recent = min(max(1, num_recent), len(messages))
    
    prefix_len = len(messages) - num_recent
    
    # If the prefix has 0 or 1 message, no middle-out compression is needed
    if prefix_len < 2:
        return list(messages)
    
    first_msg = messages[0]
    last_prefix_msg = messages[prefix_len - 1]
    
    first_repr = get_message_repr(first_msg)
    last_prefix_repr = get_message_repr(last_prefix_msg)
    
    # Construct the condensed message
    condensed_content = f"{first_repr}\n\n<omitted for brevity>\n\n{last_prefix_repr}"
    condensed_msg = SystemMessage(content=condensed_content)
    
    # Combine condensed message with the remaining messages since last update
    result = [condensed_msg] + list(messages[prefix_len:])
    return result

def get_static_system_prompt(
    sandbox_timeout: float = 2.0,
    max_string_length: int | None = None,
    max_width: int | None = None,
    max_depth: int | None = None,
    engine_name: str = "v8",
    include_end_turn: bool = True,
    plan_interval_turns: int | None = None,
) -> str:
    """Return the invariant static system instruction prompt for Message 0."""
    builder = PromptBuilder(
        max_string_length=max_string_length,
        max_width=max_width,
        max_depth=max_depth,
        plan_interval_turns=plan_interval_turns,
    )
    return builder.get_static_system_prompt(
        sandbox_timeout=sandbox_timeout,
        engine_name=engine_name,
        include_end_turn=include_end_turn,
    )



def _format_notes_for_prompt(notes: list | None) -> str:
    if not notes:
        return "[No active notes]"
    notes_lines = []
    for n in notes:
        if isinstance(n, dict):
            t = n.get("turn", "?")
            txt = n.get("text", "") or n.get("note", "")
            notes_lines.append(f"- (Turn {t}): {txt}")
        elif isinstance(n, str) and n.strip():
            notes_lines.append(f"- {n.strip()}")
    return "\n".join(notes_lines) if notes_lines else "[No active notes]"


def get_dynamic_turn_directive(
    rpg_state: Any,
    max_iterations: int,
    current_iteration: int,
    rem_iterations: int,
    messages: Sequence[BaseMessage] = (),
    turn_number: int = 1,
    include_end_turn: bool = True,
) -> str:
    """Return the dynamic turn directive block appended to the last user message."""
    # 1. Build tasks list
    task_desc = PROGRESS_STORY_TASK if include_end_turn else PROGRESS_STORY_TASK_NO_END_TURN
    tasks = [task_desc]
    total_tasks = len(tasks)
    tasks_formatted = [f"- Task 1 of 1: {task_desc}"]
    tasks_block = "\n".join(tasks_formatted)
    task_word = "task"

    # 2. Format state sections
    rpg_dict = rpg_state if isinstance(rpg_state, dict) else {}
    notes_formatted = _format_notes_for_prompt(rpg_dict.get("notes", []))
    state_section = STATE_SECTION_TEMPLATE.format(
        state_json=json.dumps(rpg_dict.get("state", {}), indent=2, ensure_ascii=False),
        hidden_state_json=json.dumps(rpg_dict.get("hidden_state", {}), indent=2, ensure_ascii=False),
        summary=rpg_dict.get("summary") or "[No events summarized yet]",
        plan_json=json.dumps(rpg_dict.get("plan", []), indent=2, ensure_ascii=False),
        notes_section=notes_formatted,
    )


    import rachel.config as config
    rendered_directive = DYNAMIC_TURN_DIRECTIVE_TEMPLATE.format(
        total_tasks=total_tasks,
        task_word=task_word,
        tasks_block=tasks_block,
        state_section=state_section,
        max_iterations=max_iterations,
        current_iteration=current_iteration,
        rem_iterations=rem_iterations,
    )
    if getattr(config, "PLAN_TRIGGER_TYPE", "periodic") == "disabled":
        rendered_directive += (
            "\n\n- Notice: Story planning updates via `submit_plan` are disabled by system policy. "
            "Do not call `submit_plan`. Use `update_plan_status()` inside `execute_code_sandbox` to adjust item statuses."
        )
    else:
        rendered_directive += (
            "\n\n- Notice: Story planning updates via `submit_plan` are disabled in Progress Mode. "
            "Do not call `submit_plan`. Use `update_plan_status()` inside `execute_code_sandbox` to adjust item statuses."
        )
    return rendered_directive


def get_summary_prompt(
    prev_summary: str,
    target_words: int | None = None,
    turns_since_update: str = "",
    range_ref: str = "",
    state: dict = {},
    hidden_state: dict = {},
    start_turn: int | str = 1,
    end_turn: int | str = 1,
) -> str:
    """Return the prompt for the narrative summarizer."""
    from rachel.agent.prompt_constants import DYNAMIC_SUMMARY_DIRECTIVE_TEMPLATE
    return DYNAMIC_SUMMARY_DIRECTIVE_TEMPLATE.format(
        state_str=json.dumps(state, indent=2, ensure_ascii=False) if state is not None else "{}",
        prev_summary=prev_summary or '[None]',
        range_ref=range_ref,
        start_turn=start_turn,
        end_turn=end_turn,
    )


def get_plan_prompt(
    prev_plan: list[dict],
    turns_since_update: str,
    range_ref: str,
    state: dict = {},
    hidden_state: dict = {},
    summary: str = "",
    summary_up_to_turn: int | str = 0,
    start_turn: int | str = 1,
    end_turn: int | str = 1,
    interval_turns: int | None = None,
    notes: list[dict] | None = None,
) -> str:
    """Return the prompt for the story planner."""
    import rachel.config as config
    from rachel.agent.prompt_constants import DYNAMIC_PLAN_DIRECTIVE_TEMPLATE
    k_turns = interval_turns if interval_turns is not None else getattr(config, "PLAN_INTERVAL_TURNS", 10)
    return DYNAMIC_PLAN_DIRECTIVE_TEMPLATE.format(
        state_str=json.dumps(state, indent=2, ensure_ascii=False) if state is not None else "{}",
        hidden_str=json.dumps(hidden_state, indent=2, ensure_ascii=False) if hidden_state is not None else "{}",
        summary_str=summary or "[No events summarized yet]",
        summary_up_to_turn=summary_up_to_turn,
        notes_str=_format_notes_for_prompt(notes),
        prev_plan=json.dumps(prev_plan, indent=2, ensure_ascii=False) if prev_plan is not None else "[]",
        turns_since_update=turns_since_update,
        range_ref=range_ref,
        start_turn=start_turn,
        end_turn=end_turn,
        interval_turns=k_turns,
    )


def get_cleanup_prompt(
    state: dict = {},
    hidden_state: dict = {},
    engine_name: str = "v8",
) -> str:
    """Return the prompt for the storage cleanup task/node."""
    from rachel.agent.prompt_constants import DYNAMIC_CLEANUP_DIRECTIVE_TEMPLATE
    lang = "JavaScript" if engine_name == "v8" else "Python"
    syntax_example = (
        "delete state.temp_buff; delete hidden_state.expired_quest_flag;"
        if engine_name == "v8"
        else "state.pop('temp_buff', None)\nhidden_state.pop('expired_quest_flag', None)"
    )
    return DYNAMIC_CLEANUP_DIRECTIVE_TEMPLATE.format(
        state_str=json.dumps(state, indent=2, ensure_ascii=False) if state is not None else "{}",
        hidden_str=json.dumps(hidden_state, indent=2, ensure_ascii=False) if hidden_state is not None else "{}",
        plan_str="[]",
        summary_str="[No summary available]",
        lang=lang,
        syntax_example=syntax_example,
    )


def get_dynamic_plan_directive(
    prev_plan: list[dict],
    turns_since_update: str,
    range_ref: str,
    state: dict = {},
    hidden_state: dict = {},
    summary: str = "",
    summary_up_to_turn: int | str = 0,
    start_turn: int | str = 1,
    end_turn: int | str = 1,
    interval_turns: int | None = None,
    notes: list[dict] | None = None,
) -> str:
    """Return dynamic directive for plan node."""
    import rachel.config as config
    from rachel.agent.prompt_constants import DYNAMIC_PLAN_DIRECTIVE_TEMPLATE
    state_str = json.dumps(state, indent=2, ensure_ascii=False) if state is not None else "{}"
    hidden_str = json.dumps(hidden_state, indent=2, ensure_ascii=False) if hidden_state is not None else "{}"
    prev_plan_str = json.dumps(prev_plan, indent=2, ensure_ascii=False) if prev_plan is not None else "[]"
    summary_str = summary or "[No events summarized yet]"
    k_turns = interval_turns if interval_turns is not None else getattr(config, "PLAN_INTERVAL_TURNS", 10)
    return DYNAMIC_PLAN_DIRECTIVE_TEMPLATE.format(
        state_str=state_str,
        hidden_str=hidden_str,
        summary_str=summary_str,
        summary_up_to_turn=summary_up_to_turn,
        notes_str=_format_notes_for_prompt(notes),
        prev_plan=prev_plan_str,
        turns_since_update=turns_since_update,
        range_ref=range_ref,
        start_turn=start_turn,
        end_turn=end_turn,
        interval_turns=k_turns,
    )


def get_dynamic_summary_directive(
    prev_summary: str,
    range_ref: str,
    state: dict = {},
    start_turn: int | str = 1,
    end_turn: int | str = 1,
) -> str:
    """Return dynamic directive for summary node."""
    from rachel.agent.prompt_constants import DYNAMIC_SUMMARY_DIRECTIVE_TEMPLATE
    state_str = json.dumps(state, indent=2, ensure_ascii=False) if state is not None else "{}"
    return DYNAMIC_SUMMARY_DIRECTIVE_TEMPLATE.format(
        state_str=state_str,
        prev_summary=prev_summary or "[None]",
        range_ref=range_ref,
        start_turn=start_turn,
        end_turn=end_turn,
    )




def get_dynamic_cleanup_directive(
    state: dict = {},
    hidden_state: dict = {},
    plan: list = [],
    summary: str = "",
    engine_name: str = "v8",
) -> str:
    """Return dynamic directive for cleanup node."""
    from rachel.agent.prompt_constants import DYNAMIC_CLEANUP_DIRECTIVE_TEMPLATE
    lang = "JavaScript" if engine_name == "v8" else "Python"
    syntax_example = (
        "delete state.temp_buff; delete hidden_state.expired_quest_flag;"
        if engine_name == "v8"
        else "state.pop('temp_buff', None)\nhidden_state.pop('expired_quest_flag', None)"
    )
    state_str = json.dumps(state, indent=2, ensure_ascii=False) if state is not None else "{}"
    hidden_str = json.dumps(hidden_state, indent=2, ensure_ascii=False) if hidden_state is not None else "{}"
    plan_str = json.dumps(plan, indent=2, ensure_ascii=False) if plan is not None else "[]"
    summary_str = summary or "[No summary available]"
    return DYNAMIC_CLEANUP_DIRECTIVE_TEMPLATE.format(
        state_str=state_str,
        hidden_str=hidden_str,
        plan_str=plan_str,
        summary_str=summary_str,
        lang=lang,
        syntax_example=syntax_example,
    )
