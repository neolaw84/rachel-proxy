"""Tests for turn resolution and message slicing under head-trimmed and middle-out histories."""

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from rachel.agent.nodes import (
    _filter_outgoing_messages_with_summary,
    _get_recent_turn_messages,
    _resolve_current_turn,
)
from rachel.core.session import resolve_turn_numbers


def test_resolve_current_turn_prefers_state_container_with_fallback():
    state = {
        "messages": [
            SystemMessage(content="sys"),
            HumanMessage(content="u1"),
            AIMessage(content="a1"),
            HumanMessage(content="u2"),
        ]
    }
    assert _resolve_current_turn(state, {"current_turn": 129}) == 129
    assert _resolve_current_turn(state, {"current_turn": None}) == 2
    assert _resolve_current_turn(state, {}) == 2


def test_resolve_turn_numbers_head_trimmed():
    messages = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "u17"},
        {"role": "assistant", "content": "[proxy: session=s1 turn=aaaaaaaaaaaaaaaaaaaaaaaa turn_number=17]\n\na17"},
        {"role": "user", "content": "u18"},
        {"role": "assistant", "content": "[proxy: session=s1 turn=bbbbbbbbbbbbbbbbbbbbbbbb turn_number=18]\n\na18"},
        {"role": "user", "content": "u19"},
    ]
    assert resolve_turn_numbers(messages, store={}) == [None, 17, 17, 18, 18, 19]


def test_resolve_turn_numbers_middle_out():
    messages = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "u1"},
        {"role": "assistant", "content": "a1"},
        {"role": "user", "content": "u2"},
        {"role": "assistant", "content": "a2"},
        {"role": "user", "content": "u17"},
        {"role": "assistant", "content": "[proxy: session=s1 turn=aaaaaaaaaaaaaaaaaaaaaaaa turn_number=17]\n\na17"},
        {"role": "user", "content": "u18"},
        {"role": "assistant", "content": "[proxy: session=s1 turn=bbbbbbbbbbbbbbbbbbbbbbbb turn_number=18]\n\na18"},
        {"role": "user", "content": "u19"},
    ]
    assert resolve_turn_numbers(messages, store={}) == [None, 1, 1, 2, 2, 17, 17, 18, 18, 19]


def test_get_recent_turn_messages_head_trimmed():
    lc_msgs = [
        SystemMessage(content="sys"),
        HumanMessage(content="u17"),
        AIMessage(content="a17"),
        HumanMessage(content="u18"),
        AIMessage(content="a18"),
        HumanMessage(content="u19"),
        AIMessage(content="a19"),
        HumanMessage(content="u20"),
    ]
    turn_nums = [None, 17, 17, 18, 18, 19, 19, 20]

    res = _get_recent_turn_messages(
        lc_msgs,
        last_update_turn=18,
        include_dangling_user=False,
        turn_numbers=turn_nums,
        initial_num_msgs_to_include=0,
    )
    contents = [m["content"] for m in res]
    assert contents == ["sys", "Turn 19: u19", "Turn 19: a19"]


def test_get_recent_turn_messages_head_trimmed_past_last_update():
    lc_msgs = [
        SystemMessage(content="sys"),
        HumanMessage(content="u17"),
        AIMessage(content="a17"),
        HumanMessage(content="u18"),
    ]
    turn_nums = [None, 17, 17, 18]

    res = _get_recent_turn_messages(
        lc_msgs,
        last_update_turn=10,
        include_dangling_user=True,
        turn_numbers=turn_nums,
        initial_num_msgs_to_include=0,
    )
    contents = [m["content"] for m in res]
    assert contents == ["sys", "Turn 17: u17", "Turn 17: a17", "Turn 18: u18"]


def test_get_recent_turn_messages_middle_out():
    lc_msgs = [
        SystemMessage(content="sys"),
        HumanMessage(content="u1"),
        AIMessage(content="a1"),
        HumanMessage(content="u17"),
        AIMessage(content="a17"),
        HumanMessage(content="u18"),
        AIMessage(content="a18"),
        HumanMessage(content="u19"),
    ]
    turn_nums = [None, 1, 1, 17, 17, 18, 18, 19]

    res = _get_recent_turn_messages(
        lc_msgs,
        last_update_turn=17,
        include_dangling_user=True,
        turn_numbers=turn_nums,
        initial_num_msgs_to_include=2,
    )
    contents = [m["content"] for m in res]
    assert contents == [
        "sys",
        "Turn 1: u1",
        "Turn 1: a1",
        "Turn 18: u18",
        "Turn 18: a18",
        "Turn 19: u19",
    ]


def test_filter_outgoing_messages_with_summary_head_trimmed_and_middle_out():
    openai_msgs = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "Turn 1: u1"},
        {"role": "assistant", "content": "Turn 1: a1"},
        {"role": "user", "content": "Turn 17: u17"},
        {"role": "assistant", "content": "Turn 17: a17"},
        {"role": "user", "content": "Turn 18: u18"},
        {"role": "assistant", "content": "Turn 18: a18"},
        {"role": "user", "content": "Turn 19: u19"},
    ]
    turn_nums = [None, 1, 1, 17, 17, 18, 18, 19]

    filtered = _filter_outgoing_messages_with_summary(
        openai_msgs,
        last_summary_turn=17,
        initial_num_msgs_to_include=2,
        last_num_msgs_to_include=1,
        turn_numbers=turn_nums,
    )
    assert [m["content"] for m in filtered] == [
        "sys",
        "Turn 1: u1",
        "Turn 1: a1",
        "Turn 18: u18",
        "Turn 18: a18",
        "Turn 19: u19",
    ]
