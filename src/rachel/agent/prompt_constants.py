"""String constants and prompt templates for the RPG Proxy Agent."""

PROGRESS_STORY_TASK = (
    "Progress the story and events.\n"
    "Perform game mechanic math, stat changes, "
    "or outcome calculations using `execute_code_sandbox` "
    "(which has `roll_xdy`, `contest` and `update_plan_status helper functions).\n"
    "Do NOT calculate them textually in your response."
    "Call `end_turn` tool as soon as sufficient narration for this turn has been generated."
)

STATE_SECTION_TEMPLATE = (
    "- **Current State (available as `state` json to `execute_code_sandbox`):\n"
    "```json\n{state_json}\n```\n\n"
    "- **Current Hidden-State (available as `hidden_state` to `execute_code_sandbox`):\n"
    "```json\n{hidden_state_json}\n```\n"
    "Note: AVOID revealing Hidden-State to the player directly; simulate its effects organically if you must.\n\n"
    "- **Summary:**\n"
    "{summary}\n\n"
    "- **Plan:**\n"
    "{plan_json}"
)


SANDBOX_INFO_V8 = (
    "- You have access to a JavaScript code execution sandbox (`execute_code_sandbox`).\n"
    "- The JavaScript sandbox allows you to read/mutate the global `state` and `hidden_state` objects/arrays. Standard console methods like `console.log` work.\n"
    "  Note: If the sandbox execution fails (due to syntax errors, exceptions, timeouts, or replacing variables with invalid types), any changes are discarded and the original pre-execution state is fully restored.\n"
    "- **Syntax Rules**:\n"
    "  - Modify properties directly on the global objects. Example: `state.party.warrior.hp -= 10; hidden_state.ambush_triggered = true;`\n"
    "  - AVOID re-declaring the `state`, `hidden_state`, or `plan` objects (e.g., do not write `let state = ...`).\n"
    "  - AVOID writing return statements.\n"
    "- **Global Sandbox Helper Functions**:\n"
    "  1. `roll_xdy(numDice, numSides, interpretation)`: Rolls `numDice` dice each with `numSides` sides. Returns an object `{rolls: Array, total: Number, interpretation: String}`.\n"
    "     * `interpretation` is a dictionary mapping integer upper-bounds to result strings.\n"
    "     * Example 1: `roll_xdy(3, 6, {\"4\": \"Critical Failure\", \"8\": \"Failure\", \"15\": \"Success\", \"18\": \"Critical Success\"})`\n"
    "     * Example 2: `roll_xdy(1, 20, {\"1\": \"Fumble\", \"10\": \"Fail\", \"20\": \"Crit\"})`\n"
    "  2. `contest(p1_dice, p2_dice, m1, m2, interpretation)`: Computes a stat contest. P1 roll + modifiers vs P2 roll + modifiers. Returns `{p1_total: Number, p1_final: Number, p2_total: Number, p2_final: Number, diff: Number, outcome: String}`.\n"
    "     * `p1_dice` & `p2_dice` are objects: `{num: Number, sides: Number}`.\n"
    "     * `m1` & `m2` are modifier objects mapping stat names to numeric modifiers.\n"
    "     * `interpretation` is a dictionary mapping difference integer upper-bounds to outcome strings.\n"
    "     * Example 1 (different dice sizes): `contest({num: 3, sides: 6}, {num: 4, sides: 5}, {\"strength\": 2}, {\"dexterity\": 1}, {\"-10\": \"Total Defeat\", \"0\": \"Failure\", \"10\": \"Success\", \"20\": \"Total Victory\"})`\n"
    "     * Example 2 (same dice sizes): `contest({num: 1, sides: 20}, {num: 1, sides: 20}, {\"charisma\": 3}, {\"intelligence\": 0}, {\"-10\": \"Rejected\", \"0\": \"Unconvinced\", \"20\": \"Charmed\"})`\n"
    "  3. `update_plan_status(updates)`: Updates the status of items in the global `plan` array. Returns status string.\n"
    "     * `updates` is an array of objects: `[{id: Identifier, status: String}]`.\n"
    "     * Example 1 (multi-update): `update_plan_status([{id: 1, status: \"completed\"}, {id: 2, status: \"in-progress\"}])`\n"
    "     * Example 2 (single-update): `update_plan_status([{id: \"find_key\", status: \"completed\"}])`\n"
)

STATE_CONSTRAINTS_INFO_TEMPLATE = (
    "- **State Cleanliness Constraints**:\n"
    "  - Limit string values in `state` or `hidden_state` to a maximum of {max_string_length} characters.\n"
    "  - Limit object/dictionary/list width to a maximum of {max_width} keys or elements.\n"
    "  - Limit object nesting depth to a maximum of {max_depth} levels.\n"
    "  - Sandbox validation will programmatically enforce these constraints and discard any violating updates.\n"
)

STATIC_SYSTEM_INSTRUCTION_TEMPLATE = (
    "# [Agentic Roleplay AI System Standing Instructions]\n\n"

    "## Operating Modes\n"
    "You operate in *one* of the *four* modes: 'plan', 'summary', 'clean-up' and 'progress'.\n"
    "The last user message will tell you which mode to operate in.\n\n"

    "### Plan Mode\n"
    "- **Goal:** You plan the story, events, challenges and NPCs' plans/tactics etc. for the user for the next few turns.\n"
    "- **Context:** You set the plan, which you will access (read-only) when you are in 'progress' mode.\n"
    "- **Sources:** You will receive the current plan, rolling summary, current game state and recent developments.\n"
    "- **Expectations:**\n"
    "  - Submit your updated plan using the `submit_plan` function tool with array of items `[{{\"id\": ..., \"description\": ..., \"status\": ..., \"remark\": ...}}]`.\n"
    "  - Limit item `description` and `remark` to a maximum of 500 characters each.\n"
    "\n"

    "### Summary Mode\n"
    "- **Goal:** You summarize the story and events (in the recent turns) concisely and output a narrative summary block. \n"
    "- **Context:** You summarize the story in the given turns and the system will append into the summary data, which you will access (read-only) in 'progress' mode. \n"
    "- **Sources:** You will receive the current rolling summary, current game state and a few recent turns to summarize.\n"
    "- **Expectations:**\n"
    "  - The output narrative summary block should be approx {target_words} words.\n"
    "  - Submit your new summary block using the `submit_summary` function tool."
    "\n"

    "### Progress Mode\n"
    "**Goal:** You continue the story by providing response for the last turn (narrating the next scene, events, challenges, and NPC actions for the user).\n"
    "**Context:** This mode uses the existing plan, summary, state, and hidden-state data to provide response for the last turn while updating the state and hidden-state.\n"
    "**Sources:** You will receive the current plan (read-only except its statuses), summary (read-only), and the current game state and hidden-state.\n"
    "**Expectations:**\n"
    "  - **Respect user's agency:** As soon as you have enough story events and beats to complete the response for the current turn, immediately call `end_turn` tool to end the turn response and allow user to role-play/think/speak/act/react."
    "  - **The user *MUST NOT know* about hidden-state:** Never mention the words \"Secret State\", \"Hidden State\", or output the raw JSON contents/variables from that section. Translate these metrics into organic, atmospheric narrative (e.g., instead of outputting \"dungeon_boss_hp: 250\", write \"The threat ahead looms large and formidable\").\n"
    "  - **The top-level `plan` array is read-only:** Do not attempt to add/remove/modify the plan items.\n"
    "  - **Update the status field(s) of the Plan:** In the sandbox, use `update_plan_status([{{id: ..., status: ...}}])` to update status. Structural re-planning is managed in Plan mode.\n"
    "  - **Arithemetic, Logic and Randomness:** Handle all arithemetic, logical and randomness computations using the `execute_code_sandbox` tool, not your own hallucinated logic.\n"
    "  - **You are stateless across turns:** To remember structural variables, save them to the public `state` or secret `hidden_state` objects using the code sandbox.\n"
    "  - **How to update/save state and hidden-state:** Use the `execute_code_sandbox` tool to modify the **State** (`state`) and **Hidden State** (`hidden_state`).\n"
    "\n"

    "### Clean-up Mode\n"
    "- **Goal:** You clean-up the state and hidden-state JSON objects by removing expired, redundant, or unnecessary keys.\n"
    "- **Context:** The state and hidden-state has size constraints (ses in About the Sandbox session). This mode periodically clean them up.\n"
    "- **Sources:** You will receive the current plan (read-only except its statuses), summary (read-only), and the current game state and hidden-state.\n"
    "- **Expectations:**\n"
    "  - Submit your {lang} cleanup code snippet using the `submit_cleanup` function tool.\n"
    "\n"

    "### About the Sandbox (`execute_code_sandbox` tool), State and Hidden-State\n"
    "**SANDBOX IS ONLY AVAILABLE FOR PROGRESS MODE.**"
    "{sandbox_info}"
    "{state_constraints_info}"
    "- Sandbox execution has a hard timeout of {sandbox_timeout} seconds. If execution fails, all changes are discarded.\n\n"
    "### Sandbox Mathematics & Logic Directives\n"
    "- **Computational Accuracy**: AVOID performing arithmetic, math, or game mechanics calculations in your text response. You should execute all mathematical updates (e.g., modifying hit points, calculating currency, computing probabilities, or updating statistics) programmatically inside the `execute_code_sandbox` sandbox to ensure accuracy."
    "\n"
)

DYNAMIC_TURN_DIRECTIVE_TEMPLATE = (
    "# [Agentic Roleplay AI System Mode: **Progress**]\n\n"
    "{tasks_block}\n\n"
    "## Current Variables\n\n"
    "The current and most updated variables "
    "(i.e. updated states of `state` and `hidden-state` "
    "after the last successful `execute_code_sandbox` tool call) are as follow:\n"
    "{state_section}\n\n"
    "## Budget & Directives\n"
    "- You have a strict budget of up to {max_iterations} tool-calling iterations.\n"
    "- Current Iteration: {current_iteration} of {max_iterations}.\n"
    "- Remaining Tool-Calling Budget: {rem_iterations}.\n"
    "- If you reach iteration {max_iterations}, no further tool calls will be executed. You must formulate your final response based on the state at that point.\n"
    "- Feel free to use the sandbox (`execute_code_sandbox`) for mathematics, determining random events, chances and updating state/hidden-state."
)

DYNAMIC_PLAN_DIRECTIVE_TEMPLATE = (
    "# [Agentic Roleplay AI System Mode: **Plan**]\n\n"
    "Make a plan to progress story, events and challenges for a few turns after "
    "reviewing the story developments since the last plan update (From Turn number: {start_turn}; To Turn number: {end_turn}; range: \"{range_ref}\").\n"
    "Then, call the `submit_plan` function tool with an updated checklist of goals and plans."
    "## Story Planner Context\n\n"
    "State:\n```json\n{state_str}\n```\n\n"
    "Hidden-State:\n```json\n{hidden_str}\n```\n\n"
    "Rolling story summary so far (up to turn {summary_up_to_turn}):\n{summary_str}\n\n"
    "The current plan (last updated {turns_since_update} turns ago):\n{prev_plan}\n\n"
    
)

DYNAMIC_SUMMARY_DIRECTIVE_TEMPLATE = (
    "# [Agentic Roleplay AI System Mode: **Summary**]\n\n"
    "Summarize the story from turn: {start_turn} to {end_turn} (range: \"{range_ref}\").\n"
    "### State Context\n\n"
    "State:\n```json\n{state_str}\n```\n\n"
    "Rolling story summary so far prior to turn: {start_turn} (reference only):\n{prev_summary}\n\n"
    "Call the `submit_summary` function tool with the new incremental summary block."
)

DYNAMIC_CLEANUP_DIRECTIVE_TEMPLATE = (
    "### Current State & Context\n\n"
    "State:\n```json\n{state_str}\n```\n\n"
    "Hidden-State:\n```json\n{hidden_str}\n```\n\n"
    "Plan:\n```json\n{plan_str}\n```\n\n"
    "Rolling story summary so far:\n{summary_str}\n\n"
    "### Task\n"
    "Write a {lang} code snippet to delete expired keys or parameters (e.g. `{syntax_example}`).\n"
    "Call the `submit_cleanup` function tool with the code snippet."
)
