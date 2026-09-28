"""Unit tests for the LLM Notes to Future Self (Epistemic Working Memory) feature."""

import copy
import json
import pytest
from rachel.sandbox.sandbox import get_sandbox_engine
from rachel.core.state import _migrate_state
from rachel.agent.tools import make_tools
from rachel.agent.prompts import (
    get_dynamic_turn_directive,
    get_plan_prompt,
    get_dynamic_plan_directive,
    _format_notes_for_prompt,
)
import rachel.config as config


def test_v8_sandbox_append_to_notes_basic():
    """Verify that append_to_notes adds a note to the notes array in V8 sandbox."""
    engine = get_sandbox_engine()
    state = {
        "state": {"hp": 100},
        "hidden_state": {"secret": "trap"},
        "plan": [],
        "notes": [],
    }
    code = 'append_to_notes("Player asked about the mysterious ruined tower.");'
    updated, output = engine.execute(code, state, timeout_seconds=3.0)

    assert isinstance(updated, dict)
    notes = updated.get("notes", [])
    assert len(notes) == 1
    assert notes[0]["text"] == "Player asked about the mysterious ruined tower."
    assert "[Notes] Appended note." in output


def test_v8_sandbox_append_to_notes_array():
    """Verify that append_to_notes handles an array of strings."""
    engine = get_sandbox_engine()
    state = {
        "state": {},
        "hidden_state": {},
        "plan": [],
        "notes": [],
    }
    code = 'append_to_notes(["First note", "Second note"]);'
    updated, output = engine.execute(code, state, timeout_seconds=3.0)

    notes = updated.get("notes", [])
    assert len(notes) == 2
    assert notes[0]["text"] == "First note"
    assert notes[1]["text"] == "Second note"


def test_v8_sandbox_append_to_notes_truncation():
    """Verify that notes exceeding max_chars_per_note are truncated with ellipsis."""
    engine = get_sandbox_engine()
    state = {
        "state": {},
        "hidden_state": {},
        "plan": [],
        "notes": [],
    }
    long_note = "A" * 400
    code = f'append_to_notes("{long_note}");'
    updated, _ = engine.execute(code, state, timeout_seconds=3.0)

    notes = updated.get("notes", [])
    assert len(notes) == 1
    # Should be truncated to 300 chars + "..."
    assert len(notes[0]["text"]) == config.NOTES_MAX_CHARS_PER_NOTE + 3
    assert notes[0]["text"].endswith("...")


def test_v8_sandbox_append_to_notes_turn_caps():
    """Verify per-turn call cap and combined character cap."""
    engine = get_sandbox_engine()
    state = {
        "state": {},
        "hidden_state": {},
        "plan": [],
        "notes": [],
    }
    # Attempt 5 calls (max allowed is 3)
    code = """
    append_to_notes("Note 1");
    append_to_notes("Note 2");
    append_to_notes("Note 3");
    append_to_notes("Note 4");
    append_to_notes("Note 5");
    """
    updated, output = engine.execute(code, state, timeout_seconds=3.0)

    notes = updated.get("notes", [])
    assert len(notes) == config.NOTES_MAX_CALLS_PER_TURN
    assert notes[0]["text"] == "Note 1"
    assert notes[1]["text"] == "Note 2"
    assert notes[2]["text"] == "Note 3"
    assert "[Notes] Cap reached" in output


def test_v8_sandbox_append_to_notes_fifo():
    """Verify FIFO rollover when notes reach max_total_notes limit."""
    engine = get_sandbox_engine()
    # Pre-populate with max_total_notes (8)
    initial_notes = [{"text": f"Old Note {i}"} for i in range(config.NOTES_MAX_TOTAL_NOTES)]
    state = {
        "state": {},
        "hidden_state": {},
        "plan": [],
        "notes": initial_notes,
    }
    code = 'append_to_notes("Brand New Note");'
    updated, _ = engine.execute(code, state, timeout_seconds=3.0)

    notes = updated.get("notes", [])
    assert len(notes) == config.NOTES_MAX_TOTAL_NOTES
    # The oldest note (Old Note 0) must have been evicted
    assert notes[0]["text"] == "Old Note 1"
    assert notes[-1]["text"] == "Brand New Note"


def test_tools_turn_tagging():
    """Verify that execute_code_sandbox in tools.py tags new notes with current turn number."""
    state_container = {
        "rpg_state": {
            "state": {"gold": 50},
            "hidden_state": {},
            "plan": [],
            "notes": [{"turn": 1, "text": "Prior turn note"}],
        },
        "current_turn": 3,
    }
    tools = make_tools(state_container, sandbox_timeout=2.0)
    sandbox_tool = next(t for t in tools if t.name == "execute_code_sandbox")

    # Add a new note via sandbox
    result = sandbox_tool.func('append_to_notes("Player negotiated a discount.");')

    rpg = state_container["rpg_state"]
    notes = rpg["notes"]
    assert len(notes) == 2
    assert notes[0]["turn"] == 1
    assert notes[0]["text"] == "Prior turn note"
    assert notes[1]["turn"] == 3
    assert notes[1]["text"] == "Player negotiated a discount."
    assert "Notes:\n" in result


def test_state_migration_with_notes():
    """Verify that _migrate_state converts legacy 4-element state to 5-element state with notes."""
    legacy_state = {
        "state": {"hp": 10},
        "plan": [{"id": 1, "description": "Test", "status": "to-do"}],
        "summary": "Old summary",
        "hidden_state": {"secret": 42},
    }
    migrated = _migrate_state(legacy_state)
    assert "notes" in migrated
    assert migrated["notes"] == []

    # If notes already exist, preserve them
    existing_notes_state = {
        "state": {},
        "plan": [],
        "summary": "",
        "hidden_state": {},
        "notes": [{"turn": 1, "text": "Keep me"}],
    }
    migrated2 = _migrate_state(existing_notes_state)
    assert migrated2["notes"] == [{"turn": 1, "text": "Keep me"}]


def test_prompts_format_notes():
    """Verify that prompt builders format notes cleanly into Progress and Plan directives."""
    # 1. Helper formatting
    assert _format_notes_for_prompt([]) == "[No active notes]"
    formatted = _format_notes_for_prompt([
        {"turn": 2, "text": "Guard was bribed."},
        {"turn": 4, "text": "Party left town."},
    ])
    assert "- (Turn 2): Guard was bribed." in formatted
    assert "- (Turn 4): Party left town." in formatted

    # 2. Dynamic turn directive (Progress mode)
    rpg_state = {
        "state": {},
        "hidden_state": {},
        "summary": "",
        "plan": [],
        "notes": [{"turn": 2, "text": "Guard was bribed."}],
    }
    turn_directive = get_dynamic_turn_directive(
        rpg_state=rpg_state,
        max_iterations=4,
        current_iteration=1,
        rem_iterations=3,
        turn_number=3,
    )
    assert "Notes to Future Self:" in turn_directive
    assert "- (Turn 2): Guard was bribed." in turn_directive

    # 3. Dynamic plan directive (Plan mode)
    plan_directive = get_dynamic_plan_directive(
        prev_plan=[],
        turns_since_update="2",
        range_ref="Turn 1 ... Turn 2",
        notes=[{"turn": 2, "text": "Guard was bribed."}],
    )
    assert "Recent Narrator Notes (from preceding Progress turns):" in plan_directive
    assert "- (Turn 2): Guard was bribed." in plan_directive


@pytest.mark.asyncio
async def test_plan_node_consolidates_and_flushes_notes(monkeypatch):
    """Verify that successful submit_plan clears the notes buffer in rpg_state."""
    from unittest.mock import AsyncMock
    from langchain_core.messages import HumanMessage, AIMessage
    from langchain_core.runnables import RunnableConfig
    from rachel.agent.nodes import _build_plan_node, _GraphDelegate

    fake_response = json.dumps([
        {"id": 1, "description": "Formulate alliance with guards", "status": "to-do", "remark": ""}
    ])
    mock_call = AsyncMock(return_value=fake_response)
    monkeypatch.setattr(_GraphDelegate, "call_openrouter_direct", mock_call)

    rpg_state = {
        "state": {},
        "hidden_state": {},
        "plan": [],
        "summary": "",
        "notes": [
            {"turn": 1, "text": "Player talked to elder"},
            {"turn": 2, "text": "Guards are suspicious"},
        ],
    }
    state_container = {"rpg_state": rpg_state}
    plan_node = _build_plan_node(api_key="fake_key", state_container=state_container)

    state = {"messages": [HumanMessage(content="Action"), AIMessage(content="Response")]}
    config_obj = RunnableConfig(configurable={"session_id": "test_sess"})

    await plan_node(state, config_obj)

    # The plan must be updated
    assert len(rpg_state["plan"]) == 1
    assert rpg_state["plan"][0]["description"] == "Formulate alliance with guards"
    # And the notes buffer must be flushed!
    assert rpg_state["notes"] == []
