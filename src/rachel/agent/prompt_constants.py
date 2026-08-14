"""String constants and prompt templates for the RPG Proxy Agent."""

UPDATE_PLAN_TASK_TEMPLATE = (
    "Call the `update_plan` tool to add, modify, or delete items on the **Plan**. "
    "It should reflect the developments since the last planning, which was {plan_turns_ago}."
)

APPEND_SUMMARY_TASK_TEMPLATE = (
    "Call the `append_summary` tool during this turn to append a 200-300 word summary "
    "describing the events that have unfolded since the last update, which was {summary_turns_ago}, into **Summary**."
)

CLEANUP_TASK_TEMPLATE = (
    "Call the `execute_code_sandbox` tool to review the global `state` and `hidden_state` objects, "
    "cleaning up any expired, redundant, or unnecessary keys/values to keep the variables lean and focused. "
    "The last cleanup was {cleanup_turns_ago}."
)

PROGRESS_STORY_TASK = (
    "Progress the story and events. You should perform game mechanic math, stat changes, "
    "or outcome calculations using `execute_code_sandbox` or `roll_xdy` "
    "rather than calculating them textually in your response."
)

STATE_SECTION_4_ELEMENT = (
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

STATE_SECTION_BASIC = (
    "- **Current State (available as `state` json to `execute_code_sandbox`):\n"
    "```json\n{state_json}\n```"
)

SANDBOX_INFO_V8 = (
    "- You have access to a JavaScript code execution sandbox (`execute_code_sandbox`).\n"
    "- The JavaScript sandbox allows you to read/mutate the global `state`, `hidden_state`, and `plan` objects/arrays. Standard console methods like `console.log` work.\n"
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

SANDBOX_INFO_PYTHON = (
    "- You have access to a Python code execution sandbox (`execute_code_sandbox`) and dice rolling tools (`roll_xdy`).\n"
    "- The Python sandbox allows you to read/mutate the `state` and `hidden_state` dicts.\n"
    "- The Python sandbox has the following libraries available: math, random, json, time, datetime, collections, itertools, functools, re, string. Nothing outside of these libraries is available.\n"
    "  Note: If the sandbox execution fails (due to syntax errors, exceptions, timeouts, or replacing `state` or `hidden_state` with a non-dict), any changes are discarded and the original pre-execution state is fully restored.\n"
    "- **Syntax Rules**:\n"
    "  - Modify properties directly on the dict objects. Example: `state['party']['warrior']['hp'] -= 10\nhidden_state['ambush_triggered'] = True`\n"
    "  - AVOID re-declaring the `state` or `hidden_state` variables (e.g., do not write `state = ...`).\n"
)

SYSTEM_INSTRUCTION_TEMPLATE = (
    "[Agent System Instruction]\n\n"
    "### Tasks\n\n"
    "Perform the following {total_tasks} {task_word}: \n\n"
    "{tasks_block}\n\n"
    "### Current Variables\n\n"
    "{state_section}\n\n"
    "### Roleplay & Secrecy Guidelines\n"
    "- **Hidden State Privacy**: Never mention the words \"Secret State\", \"Hidden State\", or output the raw JSON contents/variables from that section. Translate these metrics into organic, atmospheric narrative (e.g., instead of outputting \"dungeon_boss_hp: 250\", write \"The threat ahead looms large and formidable\").\n"
    "- **Stateless Nature**: You do not retain memory of variables across turns (API calls). To remember structural variables, save them to the public `state` or secret `hidden_state` objects using the code sandbox. AVOID storing narrative summaries, logs of events/conversations, or future plans in `state` or `hidden_state`.\n\n"
    "### Tool & State Mapping Rules\n"
    "- **State Modifications**: Use the `execute_code_sandbox` tool to modify the **State** (`state`) and **Hidden State** (`hidden_state`).\n"
    "{summary_plan_access_guidelines}\n"
    "### True Randomness Guidelines\n"
    "- **Provide Interpretation Mapping with Dice Rolls**: When calling `roll_xdy(num_dice, num_sides, interpretation)`:\n"
    "  1. Calculate roll range: min = `num_dice`, max = `num_dice * num_sides`.\n"
    "  2. Construct mandatory `interpretation` mapping upper-bound integer thresholds to outcome strings. The highest key MUST equal `max_roll`.\n"
    "  3. Example for 3d6 (range 3 to 18): `roll_xdy(3, 6, {{\\\"4\\\": \\\"critical failure\\\", \\\"8\\\": \\\"failure\\\", \\\"16\\\": \\\"success\\\", \\\"18\\\": \\\"critical success\\\"}})`.\n"
    "### Sandbox Execution Constraints\n"
    "{sandbox_info}"
    "{state_constraints_info}"
    "- Sandbox execution has a hard timeout of {sandbox_timeout} seconds. If execution fails, all changes are discarded.\n\n"
    "### Sandbox Mathematics & Logic Directives\n"
    "- **Computational Accuracy**: AVOID performing arithmetic, math, or game mechanics calculations in your text response. You should execute all mathematical updates (e.g., modifying hit points, calculating currency, computing probabilities, or updating statistics) programmatically inside the `execute_code_sandbox` sandbox to ensure accuracy.\n"
    "### Budget & Directives\n"
    "- You have a strict budget of up to {max_iterations} tool-calling iterations.\n"
    "- Current Iteration: {current_iteration} of {max_iterations}.\n"
    "- Remaining Tool-Calling Budget: {rem_iterations}.\n"
    "- If you reach iteration {max_iterations}, no further tool calls will be executed. You must formulate your final response based on the state at that point.\n"
    "- Feel free to use the sandbox (`execute_code_sandbox`) or dice rolling (`roll_xdy`) tools for mathematics, determining random events, and chances."
    "{h2_instruction_blocks}"
)

STATIC_SYSTEM_INSTRUCTION_TEMPLATE = (
    "[Agent System Instruction]\n\n"
    "### Roleplay & Secrecy Guidelines\n"
    "- **Hidden State Privacy**: Never mention the words \"Secret State\", \"Hidden State\", or output the raw JSON contents/variables from that section. Translate these metrics into organic, atmospheric narrative (e.g., instead of outputting \"dungeon_boss_hp: 250\", write \"The threat ahead looms large and formidable\").\n"
    "- **Stateless Nature**: You do not retain memory of variables across turns (API calls). To remember structural variables, save them to the public `state` or secret `hidden_state` objects using the code sandbox. AVOID storing narrative summaries, logs of events/conversations, or future plans in `state` or `hidden_state`.\n\n"
    "### Tool & State Mapping Rules\n"
    "- **State Modifications**: Use the `execute_code_sandbox` tool to modify the **State** (`state`) and **Hidden State** (`hidden_state`).\n"
    "- **Plan Modifications**: The top-level `plan` array is read-only. Use `update_plan_status([{{id: ..., status: ...}}])` to update status. Structural re-planning is managed automatically.\n\n"
    "### True Randomness Guidelines\n"
    "- **Provide Interpretation Mapping with Dice Rolls**: When calling `roll_xdy(num_dice, num_sides, interpretation)`:\n"
    "  1. Calculate roll range: min = `num_dice`, max = `num_dice * num_sides`.\n"
    "  2. Construct mandatory `interpretation` mapping upper-bound integer thresholds to outcome strings. The highest key MUST equal `max_roll`.\n"
    "  3. Example for 3d6 (range 3 to 18): `roll_xdy(3, 6, {{\\\"4\\\": \\\"critical failure\\\", \\\"8\\\": \\\"failure\\\", \\\"16\\\": \\\"success\\\", \\\"18\\\": \\\"critical success\\\"}})`.\n"
    "### Sandbox Execution Constraints\n"
    "{sandbox_info}"
    "{state_constraints_info}"
    "- Sandbox execution has a hard timeout of {sandbox_timeout} seconds. If execution fails, all changes are discarded.\n\n"
    "### Sandbox Mathematics & Logic Directives\n"
    "- **Computational Accuracy**: AVOID performing arithmetic, math, or game mechanics calculations in your text response. You should execute all mathematical updates (e.g., modifying hit points, calculating currency, computing probabilities, or updating statistics) programmatically inside the `execute_code_sandbox` sandbox to ensure accuracy."
)

DYNAMIC_TURN_DIRECTIVE_TEMPLATE = (
    "### Tasks\n\n"
    "Perform the following {total_tasks} {task_word}: \n\n"
    "{tasks_block}\n\n"
    "### Current Variables\n\n"
    "{state_section}\n\n"
    "### Budget & Directives\n"
    "- You have a strict budget of up to {max_iterations} tool-calling iterations.\n"
    "- Current Iteration: {current_iteration} of {max_iterations}.\n"
    "- Remaining Tool-Calling Budget: {rem_iterations}.\n"
    "- If you reach iteration {max_iterations}, no further tool calls will be executed. You must formulate your final response based on the state at that point.\n"
    "- Feel free to use the sandbox (`execute_code_sandbox`) or dice rolling (`roll_xdy`) tools for mathematics, determining random events, and chances."
    "{h2_instruction_blocks}"
)


SUMMARY_PROMPT_BUNDLE = (
    "Review the events of the last {turns_since_update} turns of conversation. "
    "The range of messages to summarize is: \"{range_ref}\".\n"
    "You must call the `append_summary` tool with a concise summary block (approximately {target_words} words) "
    "describing the developments in this range. Keep the tone matching the story."
)

SUMMARY_PROMPT_STANDALONE = (
    "You are a narrative summarizer for a role-playing game.\n"
    "Here is the public State:\n```json\n{state_str}\n```\n\n"
    "Here is the secret Hidden-State:\n```json\n{hidden_str}\n```\n\n"
    "Here is the story summary so far (reference only, AVOID including it in your summary):\n{prev_summary}\n\n"
    "Write a concise summary block (approximately {target_words} words) "
    "summarizing the events of the last {turns_since_update} turns of conversation. "
    "The range of messages to summarize is: \"{range_ref}\".\n\n"
    "Keep the tone matching the story.\n"
    "Output ONLY the new summary block to append. AVOID including introductory text, markdown formatting, or quotes."
)

PLAN_PROMPT_BUNDLE = (
    "Review the story developed since the last planning, which was {turns_since_update} ago. "
    "The range of developments is: \"{range_ref}\".\n"
    "You must call the `update_plan` tool with an updated checklist (as an array of objects) "
    "incorporating new sub-goals that have emerged, keeping pending tasks, and removing completed items."
)

PLAN_PROMPT_STANDALONE = (
    "You are a story planner and NPC coordinator for a role-playing game.\n"
    "Here is the public State:\n```json\n{state_str}\n```\n\n"
    "Here is the secret Hidden-State:\n```json\n{hidden_str}\n```\n\n"
    "Here is the current plan, which was created {turns_since_update} turns ago, is:\n{prev_plan}\n\n"
    "Review the story developed since the last planning. "
    "The range of developments (under the current plan) is: \"{range_ref}\".\n\n"
    "Review the current checklist and how the story has progressed.\n"
    "Generate an updated checklist of future story goals and NPC plans as a JSON array of objects, "
    "where each object matches the schema: {{\"id\": int, \"description\": str, \"status\": str, \"remark\": str}}.\n"
    "Output ONLY a valid JSON array of objects. AVOID including markdown wraps (like ```json) or explanation."
)

CLEANUP_PROMPT_BUNDLE = (
    "Review the current `state` and `hidden_state` JSON objects. "
    "Identify any keys, list elements, or parameters that have expired, are no longer active, "
    "or are redundant for the current narrative. Use the `execute_code_sandbox` tool to "
    "clean them up. Keep the variables slim and focused only on active/relevant game state."
)

CLEANUP_PROMPT_STANDALONE = (
    "You are a state optimization utility for an RPG agent.\n"
    "Here is the public State:\n```json\n{state_str}\n```\n\n"
    "Here is the secret Hidden-State:\n```json\n{hidden_str}\n```\n\n"
    "Review these objects and write a {lang} code snippet to remove/delete any "
    "expired, redundant, or unnecessary keys or parameters. "
    "For example, you can write: `{syntax_example}`.\n\n"
    "Output ONLY the raw {lang} code snippet to execute. AVOID including markdown code blocks, "
    "introductory conversational text, or any explanations."
)

STATIC_PLAN_PROMPT_TEMPLATE = (
    "[Agent Plan Instruction]\n\n"
    "### Role & Objectives\n"
    "- You are a story planner and NPC coordinator for a role-playing game.\n"
    "- Your goal is to review the current plan, rolling summary, game state, and recent developments to output an updated checklist of future story goals and NPC plans.\n"
    "- Submit your updated plan using the `submit_plan` function tool with array of items `[{{\"id\": ..., \"description\": ..., \"status\": ..., \"remark\": ...}}]`.\n"
    "- Limit item `description` and `remark` to a maximum of 500 characters each."
)

DYNAMIC_PLAN_DIRECTIVE_TEMPLATE = (
    "### Story Planner Context\n\n"
    "Here is the public State:\n```json\n{state_str}\n```\n\n"
    "Here is the secret Hidden-State:\n```json\n{hidden_str}\n```\n\n"
    "Here is the rolling story summary so far:\n{summary_str}\n\n"
    "Here is the current plan (last updated {turns_since_update} turns ago):\n{prev_plan}\n\n"
    "### Story Planner Task\n"
    "Review the story developments since the last plan update (range: \"{range_ref}\").\n"
    "Call the `submit_plan` function tool with an updated checklist of goals and plans."
)

STATIC_SUMMARY_PROMPT_TEMPLATE = (
    "[Agent Summary Instruction]\n\n"
    "### Role & Objectives\n"
    "- You are a narrative summarizer for a role-playing game.\n"
    "- Your goal is to summarize the recent turn developments concisely and output a narrative summary block (approx {target_words} words).\n"
    "- Submit your new summary block using the `submit_summary` function tool."
)

DYNAMIC_SUMMARY_DIRECTIVE_TEMPLATE = (
    "### State Context\n\n"
    "Here is the public State:\n```json\n{state_str}\n```\n\n"
    "Here is the rolling story summary so far (reference only):\n{prev_summary}\n\n"
    "### Task\n"
    "Summarize the events of the recent turns (range: \"{range_ref}\").\n"
    "Call the `submit_summary` function tool with the new incremental summary block."
)

STATIC_CLEANUP_PROMPT_TEMPLATE = (
    "[Agent State Cleanup Instruction]\n\n"
    "### Role & Objectives\n"
    "- You are a state optimization utility for an RPG agent.\n"
    "- Your goal is to inspect `state` and `hidden_state` JSON objects and remove any expired, redundant, or unnecessary keys.\n"
    "- Output your {lang} cleanup code snippet using the `submit_cleanup` function tool."
)

DYNAMIC_CLEANUP_DIRECTIVE_TEMPLATE = (
    "### Current State & Context\n\n"
    "Here is the public State:\n```json\n{state_str}\n```\n\n"
    "Here is the secret Hidden-State:\n```json\n{hidden_str}\n```\n\n"
    "Here is the top-level Plan:\n```json\n{plan_str}\n```\n\n"
    "Here is the rolling story summary so far:\n{summary_str}\n\n"
    "### Task\n"
    "Write a {lang} code snippet to delete expired keys or parameters (e.g. `{syntax_example}`).\n"
    "Call the `submit_cleanup` function tool with the code snippet."
)
