"""LangChain Tool definitions for the RPG Agent."""

import json
import logging
import random
from typing import Any
from langchain_core.tools import tool, StructuredTool
from rachel.sandbox.sandbox import get_sandbox_engine

logger = logging.getLogger(__name__)

def get_dice_interpretation(total: int, interpretation: dict[int | str, str] | list[dict[str, Any]] | None) -> str:
    """Evaluate dice roll total or contest diff against an interpretation list of range objects or legacy dict."""
    if not interpretation:
        return ""

    # Option A: List of range objects, e.g. [{min: 1, max: 7, outcome: "Critical Failure"}, ...]
    if isinstance(interpretation, list):
        for item in interpretation:
            if isinstance(item, dict):
                min_val = item.get("min")
                max_val = item.get("max")
                outcome = (
                    item.get("outcome")
                    or item.get("interpretation")
                    or item.get("result")
                    or item.get("description")
                    or ""
                )
                min_num = float(min_val) if min_val is not None else float("-inf")
                max_num = float(max_val) if max_val is not None else float("inf")
                if min_num <= total <= max_num:
                    return str(outcome)

        # Fallback if outside all explicit ranges: clamp to nearest range or first item
        min_bound = float("inf")
        max_bound = float("-inf")
        min_item = None
        max_item = None
        for item in interpretation:
            if isinstance(item, dict):
                min_val = item.get("min")
                max_val = item.get("max")
                it_min = float(min_val) if min_val is not None else float("-inf")
                it_max = float(max_val) if max_val is not None else float("inf")
                if it_min < min_bound:
                    min_bound = it_min
                    min_item = item
                if it_max > max_bound:
                    max_bound = it_max
                    max_item = item

        if total < min_bound and min_item:
            return str(
                min_item.get("outcome")
                or min_item.get("interpretation")
                or min_item.get("result")
                or min_item.get("description")
                or ""
            )
        if total > max_bound and max_item:
            return str(
                max_item.get("outcome")
                or max_item.get("interpretation")
                or max_item.get("result")
                or max_item.get("description")
                or ""
            )
        if interpretation and isinstance(interpretation[0], dict):
            first = interpretation[0]
            return str(
                first.get("outcome")
                or first.get("interpretation")
                or first.get("result")
                or first.get("description")
                or ""
            )
        return ""

    # Legacy dictionary format: { "10": "Fail", "20": "Success" }
    if isinstance(interpretation, dict):
        sorted_items = []
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

    return ""

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

        validation_error = False
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
            validation_error = True
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

        if not validation_error:
            rpg_current = state_container["rpg_state"]
            state_snapshot = (
                f"\n\n[Updated Game State]:\n"
                f"State:\n{json.dumps(rpg_current.get('state', {}), indent=2, ensure_ascii=False)}\n\n"
                f"Hidden State:\n{json.dumps(rpg_current.get('hidden_state', {}), indent=2, ensure_ascii=False)}\n\n"
                f"Plan:\n{json.dumps(rpg_current.get('plan', []), indent=2, ensure_ascii=False)}"
            )
            base_output = (output or "").strip() or "(no output)"
            output = f"{base_output}{state_snapshot}"

        logger.debug("Sandbox executed (%s). Output:\n%s", engine.name, output or "<no output>")
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

