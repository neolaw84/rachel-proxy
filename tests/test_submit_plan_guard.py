"""Unit tests verifying submit_plan runtime guard and KV-cache preserving static bindings."""

import pytest
from unittest.mock import patch
from langchain_core.messages import HumanMessage, AIMessage

from rachel.agent.tools import make_tools
from rachel.agent.prompts import get_dynamic_turn_directive
from rachel.sandbox.schemas import get_all_tools_schema


def test_submit_plan_disabled_guard():
    """Verify that submit_plan rejects mutations and returns a notice when PLAN_TRIGGER_TYPE is disabled."""
    initial_plan = [{"id": 1, "description": "Original Goal", "status": "to-do", "remark": ""}]
    state_container = {
        "rpg_state": {
            "state": {},
            "hidden_state": {},
            "plan": list(initial_plan),
            "summary": "",
        }
    }

    with patch("rachel.config.PLAN_TRIGGER_TYPE", "disabled"):
        tools = make_tools(state_container, sandbox_timeout=2.0)
        tool_map = {t.name: t for t in tools}
        assert "submit_plan" in tool_map

        new_items = [{"id": 2, "description": "Hacked Goal", "status": "completed", "remark": ""}]
        result = tool_map["submit_plan"].invoke({"items": new_items})

        assert "disabled by system policy" in result
        assert state_container["rpg_state"]["plan"] == initial_plan


def test_submit_plan_enabled_normal():
    """Verify that submit_plan updates the plan normally when PLAN_TRIGGER_TYPE is periodic or probabilistic."""
    initial_plan = [{"id": 1, "description": "Original Goal", "status": "to-do", "remark": ""}]
    state_container = {
        "rpg_state": {
            "state": {},
            "hidden_state": {},
            "plan": list(initial_plan),
            "summary": "",
        }
    }

    with patch("rachel.config.PLAN_TRIGGER_TYPE", "periodic"):
        tools = make_tools(state_container, sandbox_timeout=2.0)
        tool_map = {t.name: t for t in tools}
        assert "submit_plan" in tool_map

        new_items = [{"id": 2, "description": "Updated Goal", "status": "in-progress", "remark": ""}]
        result = tool_map["submit_plan"].invoke({"items": new_items})

        assert result == "Plan submitted successfully."
        assert state_container["rpg_state"]["plan"] == new_items


def test_dynamic_turn_directive_plan_disabled():
    """Verify that get_dynamic_turn_directive injects the disabled plan notice only when planning is disabled."""
    rpg_state = {
        "state": {"hp": 100},
        "plan": [],
        "summary": "",
        "hidden_state": {},
    }

    with patch("rachel.config.PLAN_TRIGGER_TYPE", "disabled"):
        directive = get_dynamic_turn_directive(
            rpg_state=rpg_state,
            max_iterations=5,
            current_iteration=1,
            rem_iterations=4,
            messages=[HumanMessage(content="Hello")],
            turn_number=1,
        )
        assert "Story planning updates via `submit_plan` are disabled by system policy" in directive

    with patch("rachel.config.PLAN_TRIGGER_TYPE", "periodic"):
        directive = get_dynamic_turn_directive(
            rpg_state=rpg_state,
            max_iterations=5,
            current_iteration=1,
            rem_iterations=4,
            messages=[HumanMessage(content="Hello")],
            turn_number=1,
        )
        assert "Story planning updates via `submit_plan` are disabled by system policy" not in directive


def test_tool_binding_schemas_static_and_intact():
    """Verify that all 5 tool schemas remain in the exact same order to preserve KV-cache prefix hits."""
    v8_tools = get_all_tools_schema("v8")
    assert len(v8_tools) == 5
    tool_names = [t["function"]["name"] for t in v8_tools]
    assert tool_names == [
        "execute_code_sandbox",
        "end_turn",
        "submit_plan",
        "submit_summary",
        "submit_cleanup",
    ]

    py_tools = get_all_tools_schema("python")
    assert len(py_tools) == 5
    py_tool_names = [t["function"]["name"] for t in py_tools]
    assert py_tool_names == [
        "execute_code_sandbox",
        "end_turn",
        "submit_plan",
        "submit_summary",
        "submit_cleanup",
    ]
