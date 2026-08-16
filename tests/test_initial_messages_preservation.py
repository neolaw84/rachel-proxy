"""Unit tests for initial_num_msgs_to_include preservation and overlap deduplication in sub-node messages."""

import pytest
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from rachel.agent.nodes import _get_recent_turn_messages


def test_initial_messages_preservation_without_overlap():
    """Verify that the first N non-system messages are preserved when last_update_turn is far in the future."""
    # Build 10 turns (1 System + 20 User/Assistant messages)
    messages = [SystemMessage(content="Character Card")]
    for t in range(1, 11):
        messages.append(HumanMessage(content=f"User action turn {t}"))
        messages.append(AIMessage(content=f"Assistant narrative turn {t}"))

    # Extract for last_update_turn = 8 with initial_num_msgs_to_include = 4
    # Non-system messages: indices 1, 2, 3, 4 (Turn 1 & Turn 2)
    # Recent turn window (last_update_turn = 8): Turn 9 & Turn 10 (indices 17, 18, 19, 20)
    result = _get_recent_turn_messages(
        messages=messages,
        last_update_turn=8,
        include_dangling_user=True,
        initial_num_msgs_to_include=4,
    )

    # Total messages = 1 (System) + 4 (Initial) + 4 (Recent Turn 9 & 10) = 9 messages
    assert len(result) == 9
    assert result[0]["role"] == "system"
    # Initial 4 messages preserved
    assert "User action turn 1" in result[1]["content"]
    assert "Assistant narrative turn 1" in result[2]["content"]
    assert "User action turn 2" in result[3]["content"]
    assert "Assistant narrative turn 2" in result[4]["content"]
    # Recent 4 messages appended
    assert "User action turn 9" in result[5]["content"]
    assert "Assistant narrative turn 9" in result[6]["content"]
    assert "User action turn 10" in result[7]["content"]
    assert "Assistant narrative turn 10" in result[8]["content"]


def test_initial_messages_preservation_with_overlap_deduplication():
    """Verify that overlapping indices between initial messages and recent turn window are deduplicated."""
    messages = [SystemMessage(content="Character Card")]
    for t in range(1, 6):
        messages.append(HumanMessage(content=f"User action turn {t}"))
        messages.append(AIMessage(content=f"Assistant narrative turn {t}"))

    # Extract for last_update_turn = 1 with initial_num_msgs_to_include = 4
    # Initial non-system indices: 1, 2, 3, 4 (Turn 1 & Turn 2)
    # Recent turn window start_idx for last_update_turn = 1: index 3 (Turn 2 User) up to index 10 (Turn 5 Asst)
    # Overlap occurs at indices 3 & 4.
    result = _get_recent_turn_messages(
        messages=messages,
        last_update_turn=1,
        include_dangling_user=True,
        initial_num_msgs_to_include=4,
    )

    # Combined indices: sorted(set([1, 2, 3, 4]) | set([3, 4, 5, 6, 7, 8, 9, 10])) = 1..10
    # No duplicate messages!
    assert len(result) == 11  # 1 System + 10 non-system messages
    contents = [m["content"] for m in result]
    # Ensure every turn message occurs exactly once
    assert contents.count("Turn 1: User action turn 1") == 1
    assert contents.count("Turn 2: User action turn 2") == 1



def test_minimum_outgoing_messages_count():
    """Verify that when history has >= 5 messages, total outgoing messages is >= 5."""
    messages = [
        SystemMessage(content="Card"),
        HumanMessage(content="Msg 1"),
        AIMessage(content="Msg 2"),
        HumanMessage(content="Msg 3"),
        AIMessage(content="Msg 4"),
    ]

    result = _get_recent_turn_messages(
        messages=messages,
        last_update_turn=99,  # far future
        include_dangling_user=True,
        initial_num_msgs_to_include=4,
    )

    # Total = 1 System + 4 Initial = 5 messages
    assert len(result) == 5
