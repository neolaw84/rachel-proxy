# Brainstorming Session: LLM Communicating with Future Self (Narrator Notes / Scratchpad)

## 1. Context & Motivation

In RACHEL's orchestration, the LLM operates across dedicated modes:
- **Progress Mode**: Narrates the immediate turn, updates public character stats (`state`) and secret variables (`hidden_state`), rolls dice, and progresses the story.
- **Plan Mode**: Periodically formulates a multi-turn checklist roadmap (`plan`).
- **Summary Mode**: Periodically summarizes past narrative history (`summary`).
- **Cleanup Mode**: Periodically prunes expired variables from state.

### The Problem
During Progress mode, the LLM makes emergent narrative decisions, observes player behavior, and invents secret plot developments (e.g., *"The merchant noticed the party's stolen crest and will report them to the guard next morning"*). 

Currently, there is no channel for the LLM in Progress mode to pass these thoughts to:
1. **Future Progress Mode (Turn $N+1, N+2...$)**: Short-term episodic memory across sequential turns.
2. **Future Plan Mode (Turn $N+k$)**: Strategic feedback to explain *why* plan items were bypassed or abandoned, and what new story direction the party is pursuing.

Without this channel:
- `summary` cannot help because it is strictly backward-looking (summarizes past events, not future intentions).
- `plan` cannot help because structural re-planning is disabled in Progress mode (`submit_plan` is strictly prohibited during narration).
- `hidden_state` is constrained by strict schema limits (depth, width, string length) and is designed for game variables (flags, hit points, trap DCs), not semantic director notes.

---

## 2. Architectural Analysis: Responses API vs. Chat Completions

We considered whether to postpone this feature until uplifting RACHEL's outgoing provider calls from the Chat Completions standard (`/v1/chat/completions`) to the newer Responses API standard (`/v1/responses` as standardized by MLflow and implemented by OpenRouter).

### Evaluation & Decision:
1. **Provider Interoperability**: While OpenRouter supports `/api/v1/responses`, other upstream targets and local runners (Ollama, vLLM, LM Studio, direct Anthropic/DeepSeek/Groq endpoints) still strictly require `/v1/chat/completions`. Adopting `/v1/responses` creates provider lock-in.
2. **Streaming Text UX**: In Progress mode, the client (JanitorAI/SillyTavern) expects real-time streaming tokens of markdown prose. A structured Responses API requires JSON output on every turn (e.g. `{"narration": "...", "notes": "..."}`). Streaming JSON requires either waiting for full completion (ruining time-to-first-token) or fragile partial-JSON streaming parsers.
3. **Existing Structured Tool Reliability**: Background nodes (`plan`, `summary`, `cleanup`) already use function tool calling (`tool_choice={"type": "function", ...}`) with strict JSON schemas. They are already 100% structured and reliable.

**Conclusion**: Do not wait for the Responses API. Implement narrator notes cleanly within the existing, universal agent loop.

---

## 3. Cognitive Load on Low-Cost Coding Models

Models like **DeepSeek V4 Flash** or **Gemini Flash** are capable of writing JavaScript in the sandbox, but can become overwhelmed if asked to manage complex object hierarchies or fragile boilerplate.

### Architectural Decisions:
1. **Single Channel (V8 Sandbox Only)**: We do not introduce multi-channel in-stream tag parsing (no `<note>` XML streaming tags). Keep note-taking anchored to the deterministic V8 sandbox.
2. **Dead-Simple Ergonomics**: The model calls a simple helper:
   ```javascript
   append_to_notes("Player lied about their identity; town guards are suspicious.");
   ```
   No objects to instantiate, no arrays to format, no turn numbers to compute.
3. **Resilient & Fail-Safe (No Crashes)**:
   - If a note exceeds the character limit, the sandbox **auto-truncates** it (`slice(0, max_chars) + "..."`).
   - The sandbox **never** throws a validation error or aborts the turn's dice roll/HP changes just because a note was slightly too long.

---

## 4. Concrete Specification & Configurable Parameters

All parameters will be configured under `state.notes` in `configs.yaml` and loaded via `src/rachel/config.py`:

```yaml
state:
  engine: "file"
  num_states_to_track: 32
  storage_dir: "data/states"
  max_string_length: 128
  max_depth: 8
  max_width: 64
  # Guardrails for notes to future self (scratchpad)
  notes:
    max_calls_per_turn: 3
    max_chars_per_note: 300
    max_chars_per_turn: 500
    max_total_notes: 8
```

### Parameter Rationale:
- **`max_calls_per_turn` (default: 3)**: A GM rarely needs more than 1–3 thoughts per turn. Protects against infinite loops calling the helper repeatedly.
- **`max_chars_per_note` (default: 300)**: Enough for 2–3 concise sentences. Automatically truncated if exceeded.
- **`max_chars_per_turn` (default: 500)**: Caps combined note volume per turn.
- **`max_total_notes` (default: 8)**: Upper bound for the active notes buffer (~300–400 tokens total), ensuring minimal context window overhead.
- **FIFO Overflow Policy**: When the buffer reaches `max_total_notes`, adding a new note automatically drops the oldest note.

---

## 5. The Epistemic Lifecycle (Zero Permanent Bloat)

To avoid notes accumulating indefinitely across 50+ turns, the buffer follows a closed consolidation loop:

```
[Progress Mode Turn N] ──> append_to_notes("...") ──> rpg_state["notes"]
                                                            │
                                                            ├──> Injected into Future Progress Turns (N+1, N+2...)
                                                            │
[Plan Mode Turn N+k]   <────────────────────────────────────┘
   │
   ├── Reads all recent notes as narrative context
   ├── Updates multi-turn roadmap via `submit_plan`
   └── FLUSHES BUFFER: `rpg_state["notes"] = []`
```

1. **Progress Mode**: Notes are appended during code execution and automatically tagged with the current turn number.
2. **Next Progress Turns**: Active notes are formatted and displayed in the dynamic turn directive under `## Active Notes to Future Self`.
3. **Plan Mode**: All notes accumulated since the last plan update are passed into Plan mode under `## Narrator Observations from Recent Turns`.
4. **The Flush**: When `submit_plan` succeeds, `rpg_state["notes"]` is reset to `[]`. The notes have been distilled into the macro plan and are cleared from memory.

---

## 6. System-Wide Backward Compatibility

1. **State Migration (`src/rachel/core/state.py`)**:
   `_migrate_state` updates from 4-element (`state`, `plan`, `summary`, `hidden_state`) to 5-element (`+ notes`). Existing persisted sessions load with `notes: []` seamlessly without data loss or corruption.
2. **Inspection & Debugging**:
   Session inspector in the admin panel automatically displays `notes` within current state and turn diffs.
