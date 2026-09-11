"""Unit tests for state.py, sandbox.py, and session.py."""
import json
import tempfile
from pathlib import Path

import pytest

from rachel.core.state import get_session_storage, list_all_sessions
from rachel.sandbox.sandbox import execute_sandbox


# ---------------------------------------------------------------------------
# Session Storage Backend tests
# ---------------------------------------------------------------------------

@pytest.fixture()
def tmp_store(tmp_path):
    return get_session_storage(
        session_id="test-session",
        max_size=3,
        storage_dir=tmp_path,
    )


def test_first_turn_returns_empty_state(tmp_store):
    assert tmp_store.get_before_state(None) == {
        "state": {},
        "plan": [],
        "summary": "",
        "hidden_state": {},
    }


def test_save_and_reload(tmp_path):
    store = get_session_storage("s1", max_size=8, storage_dir=tmp_path)
    store.save_turn("key1", {"hp": 100}, {"hp": 90})

    store2 = get_session_storage("s1", max_size=8, storage_dir=tmp_path)
    assert store2.get_before_state("key1") == {
        "state": {"hp": 90},
        "plan": [],
        "summary": "",
        "hidden_state": {},
    }


def test_missing_key_raises(tmp_store):
    with pytest.raises(KeyError, match="not found"):
        tmp_store.get_before_state("nonexistent")


def test_lru_eviction(tmp_path):
    store = get_session_storage("s1", max_size=3, storage_dir=tmp_path)
    store.save_turn("k1", {}, {"a": 1})
    store.save_turn("k2", {}, {"a": 2})
    store.save_turn("k3", {}, {"a": 3})
    # Access k1 so it becomes the most recently used (MRU)
    assert store.get_before_state("k1") == {
        "state": {"a": 1},
        "plan": [],
        "summary": "",
        "hidden_state": {},
    }
    # Adding a 4th should evict k2 (LRU), not k1 (accessed) or k3 (newer)
    store.save_turn("k4", {}, {"a": 4})
    with pytest.raises(KeyError, match="not found"):
        store.get_before_state("k2")
    assert store.get_before_state("k1") == {
        "state": {"a": 1},
        "plan": [],
        "summary": "",
        "hidden_state": {},
    }
    assert store.get_before_state("k3") == {
        "state": {"a": 3},
        "plan": [],
        "summary": "",
        "hidden_state": {},
    }
    assert store.get_before_state("k4") == {
        "state": {"a": 4},
        "plan": [],
        "summary": "",
        "hidden_state": {},
    }


def test_reset_clears_state(tmp_path):
    store = get_session_storage("s1", max_size=8, storage_dir=tmp_path)
    store.save_turn("k1", {}, {"x": 1})
    store.reset()
    store2 = get_session_storage("s1", max_size=8, storage_dir=tmp_path)
    assert store2.get_before_state(None) == {
        "state": {},
        "plan": [],
        "summary": "",
        "hidden_state": {},
    }


def test_delete_removes_file(tmp_path):
    store = get_session_storage("s1", max_size=8, storage_dir=tmp_path)
    store.save_turn("k1", {}, {"x": 1})
    store.delete()
    assert not (tmp_path / "s1.json").exists()


def test_list_sessions(tmp_path):
    for sid in ["alpha", "beta", "gamma"]:
        s = get_session_storage(sid, max_size=8, storage_dir=tmp_path)
        s.save_turn("k1", {}, {})
    sessions = list_all_sessions(tmp_path)
    assert sorted(sessions) == ["alpha", "beta", "gamma"]


# ---------------------------------------------------------------------------
# Sandbox tests
# ---------------------------------------------------------------------------

from rachel.sandbox.sandbox import V8SandboxEngine

# --- V8 Engine Tests ---

def test_v8_sandbox_mutates_state():
    engine = V8SandboxEngine()
    code = "state.hp -= 10;"
    updated, output = engine.execute(code, {"hp": 100})
    assert updated["hp"] == 90


def test_v8_sandbox_captures_stdout():
    engine = V8SandboxEngine()
    code = "console.log('hello world');"
    _, output = engine.execute(code, {})
    assert "hello world" in output


def test_v8_sandbox_timeout():
    engine = V8SandboxEngine()
    code = "while (true) {}"
    updated, output = engine.execute(code, {}, timeout_seconds=0.3)
    assert "timed out" in output.lower()


def test_v8_sandbox_exception_is_captured():
    engine = V8SandboxEngine()
    code = "throw new Error('oops');"
    updated, output = engine.execute(code, {})
    assert "Error" in output
    assert "oops" in output


def test_v8_sandbox_non_dict_state_reverts():
    engine = V8SandboxEngine()
    code = "state = 42;"
    original = {"hp": 10}
    updated, output = engine.execute(code, original)
    assert updated == original
    assert "Warning" in output


# ---------------------------------------------------------------------------
# Session tests
# ---------------------------------------------------------------------------

from rachel.core.session import (
    resolve_session_id,
    extract_system_suffix_hash,
    extract_session_from_proxy_annotation,
    extract_first_assistant_suffix_hash,
)
import hashlib

def test_extract_system_suffix_hash_scans_newest_to_oldest():
    messages = [
        {"role": "system", "content": "This is system prompt A"},
        {"role": "user", "content": "Hello"},
        {"role": "system", "content": "This is system prompt B"},
    ]
    
    # It should extract from the newest (bottom-most) system message, which is "This is system prompt B"
    hash_b = extract_system_suffix_hash([{"role": "system", "content": "This is system prompt B"}])
    assert extract_system_suffix_hash(messages) == hash_b


def test_extract_session_from_proxy_annotation():
    # 1. No assistant message
    assert extract_session_from_proxy_annotation([{"role": "user", "content": "Hi"}]) is None

    # 2. Assistant message without annotation
    assert extract_session_from_proxy_annotation([
        {"role": "assistant", "content": "Hello player!"}
    ]) is None

    # 3. Newest first scan
    messages = [
        {"role": "assistant", "content": "[proxy: session=old-session turn=xyz]\n\nFirst"},
        {"role": "user", "content": "Hello"},
        {"role": "assistant", "content": "[proxy: session=new-session turn=abc]\n\nSecond"},
    ]
    assert extract_session_from_proxy_annotation(messages) == "new-session"


def test_extract_first_assistant_suffix_hash():
    # 1. No assistant message
    assert extract_first_assistant_suffix_hash([{"role": "user", "content": "Hi"}]) is None

    # 2. Assistant message with whitespace and proxy block
    messages = [
        {"role": "user", "content": "Hi"},
        {"role": "assistant", "content": "[proxy: session=sess turn=xyz]\n\nHello   World \n\n Good game. "},
        {"role": "assistant", "content": "Should be ignored since it is the second assistant message."},
    ]
    # Content of first assistant: "Hello   World \n\n Good game. "
    # Stripped proxy: "Hello   World \n\n Good game. "
    # Stripped whitespace: "HelloWorldGoodgame."
    # len("HelloWorldGoodgame.") is 19. Suffix is "HelloWorldGoodgame."
    expected_hash = hashlib.md5(b"HelloWorldGoodgame.").hexdigest()[:16]
    assert extract_first_assistant_suffix_hash(messages) == expected_hash


def test_resolve_session_id_4_levels():
    messages = [
        {"role": "system", "content": "System prompt info"},
        {"role": "assistant", "content": "[proxy: session=prox-sess turn=xyz]\n\nHello player"},
        {"role": "user", "content": "Shan Yu: [session: ooc-sess] I attack!"},
    ]

    # Level 1: Explicit session ID
    assert resolve_session_id(messages, explicit_session_id="explicit-sess") == ("explicit-sess", "explicit")

    # Level 2: OOC tag
    assert resolve_session_id(messages) == ("ooc-sess", "ooc-tag")

    # Level 3: Proxy annotation (no OOC tag)
    messages_no_ooc = [
        {"role": "system", "content": "System prompt info"},
        {"role": "assistant", "content": "[proxy: session=prox-sess turn=xyz]\n\nHello player"},
        {"role": "user", "content": "Shan Yu: I attack!"},
    ]
    assert resolve_session_id(messages_no_ooc) == ("prox-sess", "proxy-annotation")

    # Level 4: First assistant suffix hash + username hash (no OOC, no proxy annotation)
    messages_fallback = [
        {"role": "system", "content": "System prompt info"},
        {"role": "assistant", "content": "Hello World. Good game."},
        {"role": "user", "content": "Shan Yu: I attack!"},
    ]
    # Suffix hash for "HelloWorld.Goodgame." is md5 of it.
    asst_hash = hashlib.md5(b"HelloWorld.Goodgame.").hexdigest()[:16]
    # Username hash for "Shan Yu" is md5 of it.
    u_hash = hashlib.md5(b"Shan Yu").hexdigest()[:16]
    expected_l4 = f"{asst_hash}__{u_hash}"
    assert resolve_session_id(messages_fallback) == (expected_l4, "assistant-suffix-hash+username-hash")

    # Level 4: Only username hash (no assistant message yet)
    messages_no_asst = [
        {"role": "system", "content": "System prompt info"},
        {"role": "user", "content": "Shan Yu: I attack!"},
    ]
    assert resolve_session_id(messages_no_asst) == (u_hash, "assistant-suffix-hash+username-hash")


def test_contest_in_v8_sandbox():
    from rachel.sandbox.v8_engine import V8SandboxEngine
    engine = V8SandboxEngine()
    code_diff_dice = """
    var res = contest({num: 3, sides: 6}, {num: 4, sides: 5}, {"strength": 2}, {"dexterity": 1}, {"-10": "Total Defeat", "0": "Failure", "10": "Success", "20": "Total Victory"});
    state.res = res;
    """
    updated_state, output = engine.execute(code_diff_dice, {}, 2.0)
    assert "res" in updated_state
    res = updated_state["res"]
    assert "p1_total" in res
    assert "p2_total" in res
    assert "diff" in res
    assert "outcome" in res
    assert "Contest results: " in output


def test_roll_xdy_in_v8_sandbox():
    from rachel.sandbox.v8_engine import V8SandboxEngine
    engine = V8SandboxEngine()
    code = """
    var res = roll_xdy(3, 6, {"4": "crit fail", "8": "fail", "16": "success", "18": "crit success"});
    state.res = res;
    """
    updated_state, output = engine.execute(code, {}, 2.0)
    assert "res" in updated_state
    res = updated_state["res"]
    assert isinstance(res["rolls"], list) and len(res["rolls"]) == 3
    assert res["total"] == sum(res["rolls"])
    assert res["interpretation"].startswith("interpretation of the dice roll is '")
    assert "interpretation of the dice roll is '" in output


def test_get_dice_interpretation_option_a_array():
    from rachel.agent.tools import get_dice_interpretation

    ranges = [
        {"min": 1, "max": 5, "outcome": "Critical Failure"},
        {"min": 6, "max": 12, "outcome": "Failure"},
        {"min": 13, "max": 17, "outcome": "Success"},
        {"min": 18, "max": 20, "outcome": "Critical Success"},
    ]

    assert get_dice_interpretation(1, ranges) == "Critical Failure"
    assert get_dice_interpretation(5, ranges) == "Critical Failure"
    assert get_dice_interpretation(6, ranges) == "Failure"
    assert get_dice_interpretation(12, ranges) == "Failure"
    assert get_dice_interpretation(13, ranges) == "Success"
    assert get_dice_interpretation(17, ranges) == "Success"
    assert get_dice_interpretation(18, ranges) == "Critical Success"
    assert get_dice_interpretation(20, ranges) == "Critical Success"

    # Out of bounds clamping / fallback
    assert get_dice_interpretation(0, ranges) == "Critical Failure"
    assert get_dice_interpretation(25, ranges) == "Critical Success"

    # Support alternative field names like 'interpretation', 'result', 'description'
    alt_ranges = [
        {"min": 1, "max": 10, "result": "Low"},
        {"min": 11, "max": 20, "description": "High"},
    ]
    assert get_dice_interpretation(5, alt_ranges) == "Low"
    assert get_dice_interpretation(15, alt_ranges) == "High"

    # Open-ended bounds (only min or only max)
    open_ranges = [
        {"max": 5, "outcome": "Low"},
        {"min": 6, "outcome": "High"},
    ]
    assert get_dice_interpretation(2, open_ranges) == "Low"
    assert get_dice_interpretation(10, open_ranges) == "High"

    # Empty or invalid
    assert get_dice_interpretation(10, []) == ""
    assert get_dice_interpretation(10, None) == ""


def test_v8_roll_xdy_and_contest_option_a():
    from rachel.sandbox.v8_engine import V8SandboxEngine
    engine = V8SandboxEngine()

    code = """
    var rollRes = roll_xdy(3, 6, [
        {min: 3, max: 8, outcome: "Low Roll"},
        {min: 9, max: 18, outcome: "High Roll"}
    ]);
    var contestRes = contest(
        {num: 1, sides: 20},
        {num: 1, sides: 20},
        {strength: 3},
        {strength: 1},
        [
            {min: -30, max: -1, outcome: "Defeat"},
            {min: 0, max: 0, outcome: "Tie"},
            {min: 1, max: 30, outcome: "Victory"}
        ]
    );
    state.roll = rollRes;
    state.contest = contestRes;
    """
    updated, logs = engine.execute(code, {}, 2.0)
    assert "roll" in updated
    assert "contest" in updated
    assert updated["roll"]["interpretation"].startswith("interpretation of the dice roll is '")
    assert updated["contest"]["outcome"] in ["Defeat", "Tie", "Victory"]


