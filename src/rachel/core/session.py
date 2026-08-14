"""Session ID resolution and message-annotation helpers for the OpenRouter proxy.

Implements a four-level session-ID hierarchy (highest → lowest priority):

1. Explicit session ID — from URL path ``/v1/{session_id}/chat/completions``
   or query parameter ``?session_id=…``.
2. OOC tag — a ``[session: name]`` tag found inside any message, scanned
   newest-first so the user can override it at any time.
3. Session ID from proxy annotation — scanned newest-first from assistant
   messages looking for a ``[proxy: session=xxx ...]`` block.
4. Stable first assistant message suffix hash + username hash — MD5 of the last
   300 characters of the first assistant message (scanned oldest-first, stripped
   of whitespace and proxy annotations) concatenated with the MD5 hash of the
   username extracted from the last user message.

The username component of option 4 is intentionally extracted from the
*last* user message, but the username itself is expected to remain stable
across a conversation; only the message body changes.

Also provides helpers to extract and strip the ``[proxy: ...]`` annotation
block that the proxy prepends to every assistant reply.
"""

import hashlib
import re
import time
from typing import Any


# ---------------------------------------------------------------------------
# Patterns
# ---------------------------------------------------------------------------

_OOC_SESSION_RE = re.compile(r"\[session:\s*([a-zA-Z0-9_\-]+)\]", re.IGNORECASE)

# Matches "PersonaName: message body" — the name is everything before the
# first ": " on the first line of the content.
_USERNAME_RE = re.compile(r"^([^:\n]{1,64}):\s")

_SYSTEM_SUFFIX_CHARS = 300

# Pattern to extract turn_key from a proxy-annotated assistant message.
_TURN_KEY_RE = re.compile(r"\[proxy:.*?turn=([a-f0-9]{24})", re.IGNORECASE)

# Pattern to extract turn_number from a proxy-annotated assistant message.
_TURN_NUMBER_RE = re.compile(r"\[proxy:.*?turn_number=(\d+)", re.IGNORECASE)

# Pattern to extract session from a proxy-annotated assistant message.
_PROXY_SESSION_RE = re.compile(r"\[proxy:.*?session=([^\s\]]+)", re.IGNORECASE)

# Pattern to strip the full [proxy: ...] annotation block (including trailing
# blank lines) from message content.  The block is always a single line of the
# form ``[proxy: session=<sid> turn=<key>]`` optionally followed by one or more
# newlines that separate it from the actual response text.
_PROXY_BLOCK_RE = re.compile(r"\[proxy:[^\]]*\]\n*", re.IGNORECASE)


# ---------------------------------------------------------------------------
# Individual extractors
# ---------------------------------------------------------------------------


def extract_ooc_session(messages: list[dict[str, Any]]) -> str | None:
    """Return the value of the first ``[session: name]`` tag found, scanning
    messages from newest to oldest.
    """
    for msg in reversed(messages):
        content = msg.get("content") or ""
        match = _OOC_SESSION_RE.search(content)
        if match:
            return match.group(1)
    return None


def extract_username_from_last_user_message(
    messages: list[dict[str, Any]],
) -> str | None:
    """Return the persona / username prefix of the last user message.

    JanitorAI prefixes user messages with ``"PersonaName: …"``.
    We extract only the name part, which is stable across the conversation.
    """
    for msg in reversed(messages):
        if msg.get("role") != "user":
            continue
        content = (msg.get("content") or "").strip()
        match = _USERNAME_RE.match(content)
        if match:
            return match.group(1).strip()
    return None


def extract_system_suffix_hash(
    messages: list[dict[str, Any]],
    suffix_chars: int = _SYSTEM_SUFFIX_CHARS,
) -> str | None:
    """Return an MD5 hex digest of the last ``suffix_chars`` characters of the
    system prompt, scanning messages from newest to oldest. Returns ``None`` if
    no system message is present.
    """
    for msg in reversed(messages):
        if msg.get("role") == "system":
            content = (msg.get("content") or "").strip()
            if not content:
                continue
            suffix = content[-suffix_chars:] if len(content) > suffix_chars else content
            return hashlib.md5(suffix.encode("utf-8")).hexdigest()[:16]
    return None


def extract_session_from_proxy_annotation(messages: list[dict[str, Any]]) -> str | None:
    """Scan the messages list (newest first) for the last assistant message
    that carries a ``[proxy: session=<sid> ...]`` annotation and return the session ID.
    """
    for msg in reversed(messages):
        if msg.get("role") != "assistant":
            continue
        content = msg.get("content") or ""
        match = _PROXY_SESSION_RE.search(content)
        if match:
            return match.group(1)
    return None


def extract_first_assistant_suffix_hash(
    messages: list[dict[str, Any]],
    suffix_chars: int = 300,
) -> str | None:
    """Return an MD5 hex digest of the last ``suffix_chars`` characters of the
    first assistant message's content (after removing all whitespaces and proxy annotations).
    Returns ``None`` if no assistant message is present.
    """
    for msg in messages:
        if msg.get("role") == "assistant":
            content = msg.get("content") or ""
            # Strip any [proxy: ...] annotations
            cleaned_content = _PROXY_BLOCK_RE.sub("", content)
            # Remove all whitespace characters
            cleaned = "".join(cleaned_content.split())
            if not cleaned:
                continue
            suffix = cleaned[-suffix_chars:] if len(cleaned) > suffix_chars else cleaned
            return hashlib.md5(suffix.encode("utf-8")).hexdigest()[:16]
    return None


# ---------------------------------------------------------------------------
# Proxy-annotation helpers
# ---------------------------------------------------------------------------


def extract_prev_turn_key(messages: list[dict[str, Any]]) -> str | None:
    """Scan the messages list (newest first) for the last assistant message
    that carries a ``[proxy: ... turn=<key>]`` annotation and return the key.
    """
    for msg in reversed(messages):
        if msg.get("role") != "assistant":
            continue
        content = msg.get("content") or ""
        match = _TURN_KEY_RE.search(content)
        if match:
            return match.group(1)
    return None


def strip_proxy_annotations(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return a new messages list with all ``[proxy: ...]`` annotation blocks
    removed from every message's ``content`` field.

    Some LLMs echo the annotation back at the start of their reply because they
    see it in the conversation history.  Stripping it here — after session/turn
    resolution (which needs the annotation) but before the LLM call — prevents
    that hallucination without affecting turn-key or session-ID resolution.

    Only string ``content`` fields are modified; structured content (lists) and
    ``None`` values are left untouched.
    """
    cleaned: list[dict[str, Any]] = []
    for msg in messages:
        content = msg.get("content")
        if isinstance(content, str) and _PROXY_BLOCK_RE.search(content):
            msg = {**msg, "content": _PROXY_BLOCK_RE.sub("", content)}
        cleaned.append(msg)
    return cleaned


def resolve_turn_numbers(
    messages: list[dict[str, Any]],
    store: Any,
    num_messages_with_unmutable_turn_number: int = 4,
) -> list[int | None]:
    """Resolve and assign a turn number to each message in the incoming history.

    Returns a list of length len(messages) where each element is either an integer turn number or None.
    """
    n = len(messages)
    resolved: list[int | None] = [None] * n
    if n == 0:
        return resolved

    # 1. Find the first user message to establish the Anchor
    first_user_idx = -1
    for i, msg in enumerate(messages):
        if msg.get("role") == "user":
            first_user_idx = i
            break

    if first_user_idx == -1:
        # No user message at all, all turns are None
        return resolved

    # Pre-calculate user message counts up to each index for O(1) lookups (O(n) prefix sum)
    user_counts = [0] * n
    count = 0
    for i in range(first_user_idx, n):
        if messages[i].get("role") == "user":
            count += 1
        user_counts[i] = count

    # Helper: count user messages up to index i (1-based)
    def count_user_messages_up_to(idx: int) -> int:
        return user_counts[idx]

    # 2. Assign turn numbers for the first N unmutable messages
    # First user message is Turn 1. Everything before is None.
    # Subsequent messages up to index num_messages_with_unmutable_turn_number-1 are Turn 1
    # until a new user message is encountered.
    limit = min(n, num_messages_with_unmutable_turn_number)
    current_turn = 1
    for i in range(first_user_idx, limit):
        if messages[i].get("role") == "user":
            # Count how many user messages we've seen to update the turn number
            current_turn = count_user_messages_up_to(i)
        resolved[i] = current_turn

    # 3. For messages after the limit, we iterate backward to resolve
    # We first resolve non-user messages, then fill in user messages.
    for i in range(n - 1, limit - 1, -1):
        msg = messages[i]
        role = msg.get("role")
        if role == "user":
            continue

        # Non-user message: search cache and annotations
        turn_key = None
        content = msg.get("content") or ""
        # Extract turn key
        match_key = _TURN_KEY_RE.search(content)
        if match_key:
            turn_key = match_key.group(1)

        turn_num = None
        if turn_key:
            try:
                meta = store.get_turn_metadata(turn_key)
                if meta and "turn_number" in meta:
                    turn_num = meta["turn_number"]
            except Exception:
                pass

        if turn_num is None:
            # Check annotation for turn_number
            match_num = _TURN_NUMBER_RE.search(content)
            if match_num:
                turn_num = int(match_num.group(1))

        if turn_num is None:
            # Fallback to counting user messages up to this point
            turn_num = count_user_messages_up_to(i)

        resolved[i] = turn_num

    # Now, fill in the user messages after the limit.
    # For user messages, use the Turn Number assigned to their immediate next non-user message.
    # If a user message is at the very end of the list, it is a new turn, so it takes
    # the last resolved assistant turn number + 1.
    for i in range(limit, n):
        if messages[i].get("role") != "user":
            continue

        if i == n - 1:
            # User message is the last message
            # Find the last resolved assistant turn number
            last_assistant_turn = None
            for j in range(n - 2, -1, -1):
                if messages[j].get("role") != "user" and resolved[j] is not None:
                    last_assistant_turn = resolved[j]
                    break
            if last_assistant_turn is not None:
                resolved[i] = last_assistant_turn + 1
            else:
                resolved[i] = count_user_messages_up_to(i)
        else:
            # Not the last message, take the turn number of the next non-user message
            next_non_user_turn = None
            for j in range(i + 1, n):
                if messages[j].get("role") != "user":
                    next_non_user_turn = resolved[j]
                    break
            if next_non_user_turn is not None:
                resolved[i] = next_non_user_turn
            else:
                resolved[i] = count_user_messages_up_to(i)

    return resolved


# ---------------------------------------------------------------------------
# Turn key
# ---------------------------------------------------------------------------


def compute_turn_key(session_id: str, messages: list[dict[str, Any]] | None = None) -> str:
    """Compute a unique turn key for the current request.

    The turn key uniquely identifies a specific turn execution within a session:

        turn_key = SHA-256[:24](session_id + NUL + epoch_in_millis)

    Using the system timestamp in milliseconds ensures that every request—including
    retries, swipes, and branching from past points—generates a distinct turn key.
    This prevents state overwrites when swiping and preserves historical states
    for all swipes.

    Args:
        session_id: Already-resolved session identifier for this chat.
        messages: Full ``messages`` list from the incoming payload (optional/unused).

    Returns:
        A 24-character lowercase hex string.
    """
    epoch_ms = time.time_ns() // 1_000_000
    raw = f"{session_id}\x00{epoch_ms}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


# ---------------------------------------------------------------------------
# Public resolver
# ---------------------------------------------------------------------------


def resolve_session_id(
    messages: list[dict[str, Any]],
    explicit_session_id: str | None = None,
) -> tuple[str, str]:
    """Resolve the session ID using the four-level hierarchy.

    Returns a tuple of ``(session_id, method)`` where ``method`` is a
    human-readable description of which level matched (for logging).

    Args:
        messages: The ``messages`` list from the incoming payload.
        explicit_session_id: Value from the URL path or query parameter, if any.
    """
    # --- Level 1: Explicit session ID (path or query param) ---
    if explicit_session_id:
        return explicit_session_id, "explicit"

    # --- Level 2: OOC tag inside messages ---
    ooc = extract_ooc_session(messages)
    if ooc:
        return ooc, "ooc-tag"

    # --- Level 3: Session ID from proxy annotation ---
    proxy_session = extract_session_from_proxy_annotation(messages)
    if proxy_session:
        return proxy_session, "proxy-annotation"

    # --- Level 4: Stable first assistant message suffix hash + username hash ---
    assistant_hash = extract_first_assistant_suffix_hash(messages)
    username = extract_username_from_last_user_message(messages)
    username_hash = hashlib.md5(username.encode("utf-8")).hexdigest()[:16] if username else None

    if assistant_hash or username_hash:
        parts = filter(None, [assistant_hash, username_hash])
        combined = "__".join(parts)
        return combined, "assistant-suffix-hash+username-hash"

    # Fallback — should be rare in practice
    return "unknown-session", "fallback"


# ---------------------------------------------------------------------------
# Provider Caching & Session Info Helpers
# ---------------------------------------------------------------------------


def format_provider_session_id(session_id: str) -> str:
    """Format and sanitize a RACHEL session_id for LLM provider APIs.

    Ensures the session identifier is a valid alphanumeric/hyphen/underscore string
    with a maximum length of 256 characters (as required by OpenRouter/OpenAI standards).
    """
    if not session_id:
        return "rachel-session-default"
    sanitized = re.sub(r"[^a-zA-Z0-9_\-]", "_", session_id.strip())
    if len(sanitized) > 256:
        sanitized = sanitized[:256]
    return sanitized or "rachel-session-default"


def get_session_caching_info(session_id: str) -> dict[str, str]:
    """Generate session caching parameters and metadata dictionary.

    Returns a dict containing provider-compatible caching identifiers:
    - ``session_id``: Primary session key for OpenRouter sticky routing / header.
    - ``prompt_cache_key``: Secondary key for OpenAI / OpenRouter prompt caching.
    - ``user``: End-user identifier for OpenAI API request tracing.
    """
    fmt_id = format_provider_session_id(session_id)
    return {
        "session_id": fmt_id,
        "prompt_cache_key": fmt_id,
        "user": f"user-{fmt_id}",
    }

