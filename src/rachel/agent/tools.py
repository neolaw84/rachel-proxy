"""LangChain Tool definitions for the RPG Agent."""

import logging
import random
from typing import Any
from langchain_core.tools import tool, StructuredTool
from rachel.sandbox.sandbox import get_sandbox_engine

logger = logging.getLogger(__name__)

def get_dice_interpretation(total: int, interpretation: dict[int | str, str]) -> str:
    """Evaluate dice roll total against an interpretation dictionary mapping integer upper bounds to descriptions."""
    sorted_items = []
    if isinstance(interpretation, dict):
        for k, v in interpretation.items():
            try:
                sorted_items.append((int(k), str(v)))
            except (ValueError, TypeError):
                pass
    sorted_items.sort(key=lambda x: x[0])
    for k, v in sorted_items:
        if total <= k:
            return v
    return sorted_items[-1][1] if sorted_items else ""

def make_tools(state_container: dict[str, Any], sandbox_timeout: float):
    """Return a list of LangChain tools that share ``state_container`` by
    reference so that every tool call sees the latest state.
    """
    engine = get_sandbox_engine()
    if engine.name == "v8":
        description = (
            "Execute a JavaScript code snippet to read or modify the current RPG state. "
            "Variables: `state` (JSON object representing the RPG state). Use `console.log(...)` to print outputs."
        )
    else:
        description = (
            "Execute a Python code snippet to read or modify the current RPG state. "
            "Variables: `state` (dict representing the RPG state). Available libraries: "
            "math, random, json, time, datetime, collections, itertools, functools, re, string. "
            "No other libraries are available."
        )

    def _execute_code_sandbox(code: str) -> str:
        import copy
        import rachel.config as config
        from rachel.sandbox.validation import validate_state_constraints

        # Take a deep copy of the original state to restore on validation failure
        rpg_copy = copy.deepcopy(state_container["rpg_state"])

        rpg = state_container["rpg_state"]
        wrapper = {
            "state": rpg.get("state", {}),
            "hidden_state": rpg.get("hidden_state", {}),
            "plan": rpg.get("plan", []),
        }
        updated, output = engine.execute(code, wrapper, sandbox_timeout)
        if isinstance(updated, dict) and "state" in updated and "hidden_state" in updated:
            rpg["state"] = updated["state"]
            rpg["hidden_state"] = updated["hidden_state"]
            rpg["plan"] = updated.get("plan", [])
        elif isinstance(updated, dict):
            rpg["state"] = updated

        # Perform post-execution validation checks
        try:
            rpg_current = state_container["rpg_state"]
            validate_state_constraints(
                rpg_current.get("state", {}),
                config.MAX_DEPTH,
                config.MAX_WIDTH,
                config.MAX_STRING_LENGTH,
                "state",
                1
            )
            validate_state_constraints(
                rpg_current.get("hidden_state", {}),
                config.MAX_DEPTH,
                config.MAX_WIDTH,
                config.MAX_STRING_LENGTH,
                "hidden_state",
                1
            )

        except ValueError as e:
            # Revert any mutations back to the clean pre-execution copy
            state_container["rpg_state"] = rpg_copy
            
            validation_error_msg = (
                f"\n--- Sandbox Validation Error ---\n{str(e)}\n"
                f"Notice: You have wasted one tool call due to this validation failure. Please adjust your state modifications."
            )
            output = (output or "").strip()
            if output:
                output = f"{output}\n{validation_error_msg}"
            else:
                output = validation_error_msg

        logger.info("Sandbox executed (%s). Output:\n%s", engine.name, output or "<no output>")
        return output or "(no output)"

    execute_code_sandbox = StructuredTool.from_function(
        func=_execute_code_sandbox,
        name="execute_code_sandbox",
        description=description,
    )

    def _end_turn() -> str:
        return "Turn completed."

    end_turn = StructuredTool.from_function(
        func=_end_turn,
        name="end_turn",
        description="Signal that you have completed narrating your story response for the current turn to pass agency back to the user.",
    )

    def _submit_plan(items: list) -> str:
        rpg = state_container.get("rpg_state", {})
        if isinstance(rpg, dict):
            rpg["plan"] = items
        return "Plan submitted successfully."

    submit_plan = StructuredTool.from_function(
        func=_submit_plan,
        name="submit_plan",
        description="Submit the updated checklist of story goals and NPC plans as a structured array.",
    )

    def _submit_summary(summary: str) -> str:
        rpg = state_container.get("rpg_state", {})
        if isinstance(rpg, dict):
            prev = rpg.get("summary", "")
            if prev:
                rpg["summary"] = prev.strip() + "\n\n" + summary.strip()
            else:
                rpg["summary"] = summary.strip()
        return "Summary submitted successfully."

    submit_summary = StructuredTool.from_function(
        func=_submit_summary,
        name="submit_summary",
        description="Submit the narrative summary block describing developments.",
    )

    def _submit_cleanup(code: str) -> str:
        return _execute_code_sandbox(code)

    submit_cleanup = StructuredTool.from_function(
        func=_submit_cleanup,
        name="submit_cleanup",
        description="Submit code snippet to clean up state and hidden_state variables.",
    )

    return [execute_code_sandbox, end_turn, submit_plan, submit_summary, submit_cleanup]

