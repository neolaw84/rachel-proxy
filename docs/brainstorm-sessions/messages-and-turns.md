# Brainstorming session on "Messages" and "Turns"

## Definitions

* **Rachel:** We will call `rachel-proxy` (this repo/this system) "Rachel".
* **Incoming Messages:** The list of messages sent by the client to Rachel (in the API call's payload).
* **Turn:** A pair of two messages - user message followed by an assistant message (often the last response from Rachel) - in the Incoming Messages. 
  - Notes: By extension, if the last message in the Incoming Messages is not user message, it is not a new Turn. 
* **Outgoing Messages:** The list of messages Rachel sends to the LLM provider (in the API call's payload).
* **Session:** A role-play session/campaign. It includes multiple turns (stored in session cache by Rachel). 
* **Turn Number:** An integer (starting from 0) to identify how far the story gets from start of the Session.
* **Turn Key:** A Unique ID to identify an instance of the session cache.
  - Notes: A Turn Number may have many Turn Keys (if user retry/redo a turn; User can retry any turn in history --- not necessarily the last one).

## Problems and Rationales

### Meta Data

Current session cache entries just have before and after, each of which has 4 sub-entries - `state`, `hidden-state`, `plan` and `summary`. These are meant for constructing instructions to guide the LLM. Rachel should not store her own meta data (turn number, session-id etc.) in them. 

### Turn Number

Many clients of Rachel-Proxy often middle-out the Incoming Messages they send (as part of the API call payload) to Rachel. Often, they also allow their user to continue the AI-generated narration (detected by the last entry in the Incoming Messages is not a user message). This makes the current way of tracking turn numbers unreliable. 

Notes: 
* Session cache is limited (it is an LRU cache with Turn Key as identifier). So we cannot rely on session cache only to track turn numbers. Session cache (when hit) will have priority but, when it misses, we need a secondary mechanism to fall back.
* Middleout is less likely at the start of a Session (incoming message is less than 10). 

### Confused LLM

Some LLMs (Google's Gemini, Anthropic's Claude, and Xiaomi's Mimo 2.5 ranges) understands the structure/nature of `rachel-proxy` while others (Deepseek V3 and V4 ranges etc.) do not. The latter is using up all tool-call budget while pumping up narrations in each LLM calls. That means, if `langgraph.max_iteration` is 6, it pumps up narations 6 times. This carries the adventure/role-play story too far without giving the user a chance to think/speak/act/react to the narration. 

### Complexities for Long-horizon Goals

The long-horizon aim of `rachel-proxy` is to have provider (in the case of local mode, it's user) determines the loop structure (the composition pattern). Letting LLM determines what to do with plan/summary/clean-up mechanisms in main LLM call (via batching) is a hindrance to this aim. 

Another long-horizon aim of `rachel-proxy` is to have provider (in the case of local mode, it's user) introduces additional tools. Given the state of the character AI, role-play and AI-enabled RPG landscape, there are far more javascript expertise among the provider than python expertise. Furthermore, maintaining pure python option is dragging the development of `rachel-proxy`.

## Proposed Changes

### Meta Data

Rachel should store her own meta data as `meta-data` (same level as `before` and `after`) as follow:

```json
{
  "1234567890": { // turn key id
    "meta-data": {
      "session_id": "1a2b_3c4d", // session id
      "prompt_cache_key": "1a2b_3c4d",
      "user": "user-1a2b__3c4d",
      "turn_number": 3,
      // ...
    },
    "before": {
      "state": {},
      "plan": [],
      "summary": "",
      "hidden_state": {}
    },
    "after": {
      "state": {},
      "plan": [],
      "summary": "",
      "hidden_state": {}
    }
  },
  // ... 
}
```

### Turn Number

We decide to keep Turn Number in two places. In addition to store Turn Number in the session cache (as `meta-data.turn_number`), we also add it in the session/turn-key in the Rachel's response. 

Therefore the hierarchy to restore the latest Turn Number is:

* First, search the Turn Key in session cache. If found, use the Turn Number stored in it (i.e. `meta-data.turn_number`). 
* Otherwise, look at the last entry in Incoming Messages and take the Turn Number found there.
* In edge cases where the Turn Number is not found in either place (i.e. the start of a session), we use the count of user message as the number of turn (the first user message is turn 1).
* In either case:
  - If the last entry in Incoming Messages is a user message, we can safely say this is a new turn, so the turn number is "last entry's Turn Number + 1".
  - If it is not a user message, this is a retry/redo of the last turn, so the turn number is the same as the last entry's Turn Number.

This Turn Number should be applied to derive Turn Number for all the messages in the received Incoming Messages:
* For all messages except the first `num_messages_with_unmutable_turn_number=4` messages (Make `num_messages_with_unmutable_turn_number` configurable), starting with the last entry, iterate backward and assign the turn number for each entry using the following mechanism: 
  - For non-user messages, use the aforementioned mechanism to get the Turn Number (cache entry first; cache misses will just use the one found with the message session id; if not found, derive from count of user message)
  - For user messages, use the Turn Number assigned to their immediate next non-user message (for user message at index `k`, use the Turn Number of `k+1`).
* For first `num_messages_with_unmutable_turn_number=4` messages, the turn number is derived using the first user message (often at index 1 using C-style array indexing). The first user message is Turn 1. All messages before it (such as the system message at index 0) do not have Turn Number. The subsequent non-user messages are all Turn 1 until the next user message (which is Turn 2).  

Notes: 
- The derived turn number should be regarded as canon and used for the followings:
  * The plan/summary/cleanup operations
  * The outgoing message formatting

### Outgoing Messages

Using the derived Turn Number, prefix the content of the Outgoing Messages with "Turn X: " where X is the Turn Number. 

The LLM outputs should be checked and stripped out of accidental "Turn X: " prefixes (in all cases and all markdown formatting).

The LLM calls (from `llm_action` node) should be a user message. I will give an example to illustrate it:

* **Incoming Messages:** Here is the 10 messages [system, user, assistant, user, assistant, user, ..., assistant, user]. 
* **Outgoing Messages:** Rachel's instruction should be the 11th message. So, [system (no turn), user (turn 1), assistant (turn 1), user (turn 2), assistant (turn 2), user (turn 3), ... assistant (turn 4), user (turn 5), user (Rachel's instruction on how to respond turn 5)]. 

Notes:
- Rachel's instruction on how to respond turn 5 is the current (or evolved form of) "[Agent System Instruction]" found in `SYSTEM_INSTRUCTION_TEMPLATE` constant in src/rachel/agent/prompt_constants.py`. 

### ### Complexities for Long-horizon Goals

We are aiming to reduce complexity of Rachel through:

* Simplifying the graph by:
    - Making the plan, summary and clean-up only available as optional graph nodes (periodic) or none at all (disabled). There will be no more batching them together in the main LLM call. 
    - Introducing the (new) `_route_end` node that perform house-keeping items for Rachel internal processings.
* Simplifying the tool calls by allowing only the code sandbox execution tool and the (new) end turn tool for the `llm_action` node:
    - The (new) contest tool, the dice roll and update plan status will be available inside the code sandbox execution tool only
    - The update plan and append summary tools will not be bound to LLM in `llm_action` node; instead, these tools will be available only in plan/summary/clean-up nodes.
* Simplifying the sandbox by removing the pure python option; Only V8-isolate remains the sole sandbox.

Notes:
* The contest tool's signature is as follow:
  - Inputs include party 1's dice roll (x1, y1 for xdy roll), party 2's dice roll (x2, y2 for xdy roll), party 1's modifiers (`m1` - dictionary with name keys to numeric values), party 2's modifiers (`m2` - dictionary with name keys to numeric values), and how to interpret the result, party 1 roll + modifier values - (part 2 roll + modifier values) for all possible values (in the same fashion as the current dice roll function).
  - Outputs will be `console.log` out for all the computation and 
  - The textual description of outcome will be returned. 