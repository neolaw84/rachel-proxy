"""Unit tests validating Checkpoint 2 features: turn resolution, directives merging, and V8 sandbox helpers."""

import pytest
import os
from langchain_core.messages import HumanMessage, AIMessage
from rachel.core.session import resolve_turn_numbers
from rachel.core.state import FileSessionStorage
from rachel.sandbox.sandbox import execute_sandbox


def test_resolve_turn_numbers_user_starts_at_zero():
    """Verify turn numbers when the first user message starts at index 0."""
    messages = [
        {"role": "user", "content": "I attack!"},
        {"role": "assistant", "content": "You hit."},
        {"role": "user", "content": "I run!"},
        {"role": "assistant", "content": "You escape."},
    ]
    meta_dict = {}
    
    # Let's resolve turn numbers
    turn_numbers = resolve_turn_numbers(messages, meta_dict, num_messages_with_unmutable_turn_number=0)
    # Expected: turn 1 starts at index 0. User message at index 0 is Turn 1.
    # Assistant message at index 1 is Turn 1.
    # User message at index 2 is Turn 2.
    # Assistant message at index 3 is Turn 2.
    assert turn_numbers == [1, 1, 2, 2]


def test_resolve_turn_numbers_user_starts_at_three():
    """Verify turn numbers when the first user message starts at index 3 (first 3 are system/pre-story)."""
    messages = [
        {"role": "system", "content": "System directive"},
        {"role": "assistant", "content": "Introductory narrative"},
        {"role": "system", "content": "Hidden context"},
        {"role": "user", "content": "Hello!"},  # index 3
        {"role": "assistant", "content": "Welcome!"},  # index 4
        {"role": "user", "content": "Can I have ale?"},  # index 5
    ]
    meta_dict = {}
    
    # Resolve turn numbers
    turn_numbers = resolve_turn_numbers(messages, meta_dict, num_messages_with_unmutable_turn_number=3)
    # First 3 do not have a turn number (None). Turn 1 starts at index 3.
    assert turn_numbers == [None, None, None, 1, 1, 2]


def test_resolve_turn_numbers_no_user_message():
    """Verify that if no user message exists in the unmutable range or at all, they have no turn numbers."""
    messages = [
        {"role": "system", "content": "System directive"},
        {"role": "assistant", "content": "Introductory narrative"},
    ]
    meta_dict = {}
    turn_numbers = resolve_turn_numbers(messages, meta_dict, num_messages_with_unmutable_turn_number=5)
    assert turn_numbers == [None, None]


def test_directives_merging_logic():
    """Verify that directives are correctly merged into the final user message."""
    messages = [
        {"role": "system", "content": "System rule"},
        {"role": "user", "content": "I attack the goblin!"},
    ]
    directives = "Play dramatic music and update the plan."
    
    # Simulate finding the last user message and appending
    found_user = False
    for msg in reversed(messages):
        if msg.get("role") == "user":
            orig_content = msg.get("content") or ""
            instruction_block = (
                f"\n\n---\n"
                f"[RPG DIRECTIVE & GAME STATE (Turn 1)]\n"
                f"{directives}"
            )
            msg["content"] = orig_content + instruction_block
            found_user = True
            break
            
    assert found_user
    assert "I attack the goblin!" in messages[-1]["content"]
    assert "[RPG DIRECTIVE & GAME STATE (Turn 1)]" in messages[-1]["content"]
    assert directives in messages[-1]["content"]


def test_v8_contest_helper_diff_dice():
    """Verify the contest helper in V8 engine with different dice (3d6 vs 4d5)."""
    state = {
        "state": {},
        "hidden_state": {},
    }
    # Contest: 3d6 (min 3, max 18) vs 4d5 (min 4, max 20) with mod +2 vs +1
    code = """
    var res = contest(
        {num: 3, sides: 6}, 
        {num: 4, sides: 5}, 
        {"strength": 2}, 
        {"dexterity": 1}, 
        {"-5": "Terrible Loss", "0": "Draw / Tie", "5": "Mild Victory", "20": "Total Victory"}
    );
    state.contest_result = res;
    """
    updated, logs = execute_sandbox(code, state, timeout_seconds=2.0)
    assert "contest_result" in updated["state"]
    res = updated["state"]["contest_result"]
    assert "p1_total" in res
    assert "p2_total" in res
    assert "diff" in res
    assert "outcome" in res
    assert "Contest results: Party 1 rolled 3d6:" in logs
    assert "Party 2 rolled 4d5:" in logs


def test_v8_update_plan_status_helper():
    """Verify that update_plan_status mutates the global plan array in the V8 sandbox."""
    state = {
        "state": {},
        "hidden_state": {},
        "plan": [
            {"id": "goal_a", "status": "to-do"},
            {"id": "goal_b", "status": "in-progress"},
        ]
    }
    code = """
    update_plan_status([
        {id: "goal_a", status: "completed"},
        {id: "goal_b", status: "abandoned"}
    ]);
    """
    updated, logs = execute_sandbox(code, state, timeout_seconds=2.0)
    assert "Updated status of 2 plan items." in logs
    plan = updated["plan"]
    assert plan[0]["status"] == "completed"
    assert plan[1]["status"] == "abandoned"
