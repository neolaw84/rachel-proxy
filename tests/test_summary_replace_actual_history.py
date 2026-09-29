"""Unit tests for summary_replace_actual_history in Progress mode."""

import pytest
from unittest.mock import AsyncMock, patch
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, ToolMessage
from rachel.agent.nodes import _filter_outgoing_messages_with_summary, _build_llm_node
from rachel.config import (
    PROGRESS_SUMMARY_REPLACE_ACTUAL_HISTORY,
    PROGRESS_INITIAL_NUM_MSGS_TO_INCLUDE,
    PROGRESS_LAST_NUM_MSGS_TO_INCLUDE,
    SUMMARY_REPLACE_ACTUAL_HISTORY,
)


def test_default_config_values():
    """Verify that summary_replace_actual_history, initial_num_msgs_to_include, and last_num_msgs_to_include load properly."""
    assert PROGRESS_SUMMARY_REPLACE_ACTUAL_HISTORY is True
    assert SUMMARY_REPLACE_ACTUAL_HISTORY is True
    assert PROGRESS_INITIAL_NUM_MSGS_TO_INCLUDE == 4
    assert PROGRESS_LAST_NUM_MSGS_TO_INCLUDE == 4


def test_filter_outgoing_messages_no_summary_or_zero():
    """Verify that messages are unchanged when last_summary_turn <= 0 or empty."""
    msgs = [
        {"role": "system", "content": "Card"},
        {"role": "user", "content": "Turn 1 user"},
        {"role": "assistant", "content": "Turn 1 asst"},
    ]
    assert _filter_outgoing_messages_with_summary(msgs, last_summary_turn=0) == msgs
    assert _filter_outgoing_messages_with_summary(msgs, last_summary_turn=-1) == msgs
    assert _filter_outgoing_messages_with_summary([], last_summary_turn=5) == []


def test_filter_outgoing_messages_preserves_initial_k_and_recent_turns():
    """Verify that the first k non-system messages and messages after last_summary_turn are preserved."""
    # 10 turns = 1 System + 20 User/Assistant messages
    openai_msgs = [{"role": "system", "content": "Character Card"}]
    for t in range(1, 11):
        openai_msgs.append({"role": "user", "content": f"Turn {t}: User action"})
        openai_msgs.append({"role": "assistant", "content": f"Turn {t}: Assistant reply"})

    # Current turn is Turn 11 User action
    openai_msgs.append({"role": "user", "content": "Turn 11: Current User action"})

    # Suppose last_summary_turn is 8, and initial_num_msgs_to_include is 4 (Turns 1 and 2)
    filtered = _filter_outgoing_messages_with_summary(
        openai_msgs,
        last_summary_turn=8,
        initial_num_msgs_to_include=4,
    )

    # Expected:
    # - Index 0: System
    # - Indices 1..4: Turn 1 User, Turn 1 Asst, Turn 2 User, Turn 2 Asst
    # - After Turn 8 (Assistant #8 at original index 16):
    #   Turn 9 User (orig 17), Turn 9 Asst (orig 18), Turn 10 User (orig 19), Turn 10 Asst (orig 20), Turn 11 User (orig 21)
    # Total = 1 (System) + 4 (Initial) + 5 (Recent) = 10 messages
    assert len(filtered) == 10
    assert filtered[0]["content"] == "Character Card"

    contents = [m["content"] for m in filtered]
    assert "Turn 1: User action" in contents
    assert "Turn 1: Assistant reply" in contents
    assert "Turn 2: User action" in contents
    assert "Turn 2: Assistant reply" in contents

    # Turns 3-8 should be omitted to save tokens
    for t in range(3, 9):
        assert f"Turn {t}: User action" not in contents
        assert f"Turn {t}: Assistant reply" not in contents

    # Turns 9, 10, and 11 should be present
    assert "Turn 9: User action" in contents
    assert "Turn 9: Assistant reply" in contents
    assert "Turn 10: User action" in contents
    assert "Turn 10: Assistant reply" in contents
    assert "Turn 11: Current User action" in contents


def test_filter_outgoing_messages_overlap_deduplication():
    """Verify that when the initial k messages overlap with the post-summary recent messages, they are cleanly deduplicated."""
    # 4 turns: 1 System + 8 User/Asst
    openai_msgs = [{"role": "system", "content": "Card"}]
    for t in range(1, 5):
        openai_msgs.append({"role": "user", "content": f"Turn {t}: User"})
        openai_msgs.append({"role": "assistant", "content": f"Turn {t}: Asst"})

    # If last_summary_turn = 1 and initial_num_msgs_to_include = 4:
    # Initial: indices 1, 2, 3, 4 (Turn 1 & Turn 2)
    # Recent (after Turn 1 Asst, which is index 2): indices 3..8 (Turn 2, 3, 4)
    # Overlap at indices 3 & 4 must not produce duplicate messages!
    filtered = _filter_outgoing_messages_with_summary(
        openai_msgs,
        last_summary_turn=1,
        initial_num_msgs_to_include=4,
    )

    # All 9 messages should be present once
    assert len(filtered) == 9
    assert [m["content"] for m in filtered].count("Turn 2: User") == 1
    assert [m["content"] for m in filtered].count("Turn 2: Asst") == 1


def test_filter_outgoing_messages_without_system_message():
    """Verify proper behavior when history does not start with a system message."""
    openai_msgs = []
    for t in range(1, 10):
        openai_msgs.append({"role": "user", "content": f"Turn {t}: User"})
        openai_msgs.append({"role": "assistant", "content": f"Turn {t}: Asst"})

    filtered = _filter_outgoing_messages_with_summary(
        openai_msgs,
        last_summary_turn=6,
        initial_num_msgs_to_include=4,
    )

    # Initial 4 non-system messages (Turn 1 & 2: indices 0..3)
    # Recent (after Turn 6 Asst, index 11): indices 12..17 (Turns 7, 8, 9)
    # Total = 4 + 6 = 10 messages
    assert len(filtered) == 10
    contents = [m["content"] for m in filtered]
    assert contents[0] == "Turn 1: User"
    assert contents[3] == "Turn 2: Asst"
    assert contents[4] == "Turn 7: User"


def test_filter_outgoing_messages_boundary_not_found_safeguard():
    """Verify that if the last_summary_turn boundary is not found, messages are returned unchanged."""
    openai_msgs = [
        {"role": "system", "content": "Card"},
        {"role": "user", "content": "Turn 1: User"},
        {"role": "assistant", "content": "Turn 1: Asst"},
    ]
    # last_summary_turn = 5 exceeds available assistant count (1)
    filtered = _filter_outgoing_messages_with_summary(
        openai_msgs,
        last_summary_turn=5,
        initial_num_msgs_to_include=4,
    )
    assert filtered == openai_msgs


@pytest.mark.asyncio
async def test_llm_node_outgoing_messages_with_summary_replacement():
    """Verify that llm_node trims outgoing messages when summary_replace_actual_history is enabled."""
    # Build 10 turns of LangChain messages
    messages = [SystemMessage(content="Character Card")]
    for t in range(1, 11):
        messages.append(HumanMessage(content=f"User action {t}"))
        messages.append(AIMessage(content=f"Assistant narrative {t}"))
    # Current turn 11 user action
    messages.append(HumanMessage(content="Current action 11"))

    state_container = {
        "rpg_state": {
            "state": {"hp": 100},
            "hidden_state": {},
            "summary": "This is the summary of turns 1 through 8.",
            "plan": [],
        },
        "last_summary_turn": 8,
        "summary_replace_actual_history": True,
        "initial_num_msgs_to_include": 4,
    }

    captured_openai_messages = []

    async def mock_call_openrouter_streaming(**kwargs):
        captured_openai_messages.extend(kwargs.get("openai_messages", []))
        return "Narrative response", "", []

    with patch("rachel.agent.nodes._GraphDelegate.call_openrouter_streaming", side_effect=mock_call_openrouter_streaming):
        llm_node = _build_llm_node(
            api_key="test-key",
            base_url="http://localhost:8000",
            model="google/gemini-3.5-flash",
            max_iterations=4,
            sandbox_timeout=4.0,
            state_container=state_container,
        )

        state = {
            "messages": messages,
            "rpg_state": state_container["rpg_state"],
            "sandbox_timeout": 4.0,
            "iteration_count": 0,
        }
        config = {"configurable": {}}

        await llm_node(state, config)

    # Verify that captured_openai_messages has trimmed history
    assert len(captured_openai_messages) == 10
    contents = [m["content"] for m in captured_openai_messages]

    # Message 0 has static prompt merged
    assert "Character Card" in contents[0]
    assert "[Agentic Roleplay AI System Standing Instructions]" in contents[0]

    # Initial 4 messages preserved
    assert any("User action 1" in c for c in contents)
    assert any("Assistant narrative 1" in c for c in contents)
    assert any("User action 2" in c for c in contents)
    assert any("Assistant narrative 2" in c for c in contents)

    # Turns 3-8 omitted
    for t in range(3, 9):
        assert not any(f"User action {t}" in c for c in contents)
        assert not any(f"Assistant narrative {t}" in c for c in contents)

    # Recent turns 9, 10, 11 present
    assert any("User action 9" in c for c in contents)
    assert any("Assistant narrative 9" in c for c in contents)
    assert any("User action 10" in c for c in contents)
    assert any("Assistant narrative 10" in c for c in contents)

    # Final message is user message with dynamic directive and summary
    last_user_msg = captured_openai_messages[-1]
    assert last_user_msg["role"] == "user"
    assert "Current action 11" in last_user_msg["content"]
    assert "[RPG DIRECTIVE & GAME STATE" in last_user_msg["content"]
    assert "This is the summary of turns 1 through 8." in last_user_msg["content"]


def test_filter_outgoing_messages_six_messages_no_middle_duplicates():
    """Verify that when there are only 6 messages, initial 4 and last 4 do not duplicate the middle 2 messages."""
    openai_msgs = [
        {"role": "user", "content": "Turn 1: User"},
        {"role": "assistant", "content": "Turn 1: Asst"},
        {"role": "user", "content": "Turn 2: User"},
        {"role": "assistant", "content": "Turn 2: Asst"},
        {"role": "user", "content": "Turn 3: User"},
        {"role": "assistant", "content": "Turn 3: Asst"},
    ]

    filtered = _filter_outgoing_messages_with_summary(
        openai_msgs,
        last_summary_turn=1,
        initial_num_msgs_to_include=4,
        last_num_msgs_to_include=4,
    )

    # Exactly 6 messages preserved, strictly in order
    assert len(filtered) == 6
    contents = [m["content"] for m in filtered]
    assert contents == [
        "Turn 1: User",
        "Turn 1: Asst",
        "Turn 2: User",
        "Turn 2: Asst",
        "Turn 3: User",
        "Turn 3: Asst",
    ]
    # Verify the middle 2 messages appear exactly once (no duplicates)
    assert contents.count("Turn 2: User") == 1
    assert contents.count("Turn 2: Asst") == 1


def test_filter_outgoing_messages_system_plus_six_messages_no_duplicates():
    """Verify with 1 system card + 6 non-system messages, the middle 2 are not duplicated."""
    openai_msgs = [
        {"role": "system", "content": "Character Card"},
        {"role": "user", "content": "Turn 1: User"},
        {"role": "assistant", "content": "Turn 1: Asst"},
        {"role": "user", "content": "Turn 2: User"},
        {"role": "assistant", "content": "Turn 2: Asst"},
        {"role": "user", "content": "Turn 3: User"},
        {"role": "assistant", "content": "Turn 3: Asst"},
    ]

    filtered = _filter_outgoing_messages_with_summary(
        openai_msgs,
        last_summary_turn=1,
        initial_num_msgs_to_include=4,
        last_num_msgs_to_include=4,
    )

    assert len(filtered) == 7
    assert filtered[0]["content"] == "Character Card"
    contents = [m["content"] for m in filtered]
    assert contents.count("Turn 2: User") == 1
    assert contents.count("Turn 2: Asst") == 1


def test_filter_outgoing_messages_prunes_middle_when_more_than_initial_plus_last():
    """Verify that when history is longer than initial + last, the middle is pruned."""
    openai_msgs = [
        {"role": "system", "content": "Card"},
    ]
    for t in range(1, 6):  # 5 turns = 10 messages
        openai_msgs.append({"role": "user", "content": f"Turn {t}: User"})
        openai_msgs.append({"role": "assistant", "content": f"Turn {t}: Asst"})

    # initial=4 (Turn 1 & 2), last=4 (Turn 4 & 5), last_summary_turn=3 (Turn 3 Asst)
    filtered = _filter_outgoing_messages_with_summary(
        openai_msgs,
        last_summary_turn=3,
        initial_num_msgs_to_include=4,
        last_num_msgs_to_include=4,
    )

    # Total should be 1 (Card) + 4 (Initial) + 4 (Last) = 9 messages
    # Turn 3 messages (User and Asst) should be omitted
    assert len(filtered) == 9
    contents = [m["content"] for m in filtered]
    assert "Turn 1: User" in contents
    assert "Turn 2: Asst" in contents
    assert "Turn 3: User" not in contents
    assert "Turn 3: Asst" not in contents
    assert "Turn 4: User" in contents
    assert "Turn 5: Asst" in contents

