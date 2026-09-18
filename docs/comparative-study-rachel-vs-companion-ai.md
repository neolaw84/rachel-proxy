# Comparative Study: RACHEL vs. Companion AI Scripting Paradigms

## Executive Summary

Text-based roleplaying games (RPGs) and character companion platforms have evolved rapidly beyond basic conversational chatbots. Modern players expect immersive narrative prose coupled with tabletop-style mechanical consistency: character stats, inventories, combat calculations, secret NPC attitudes, and coherent narrative memory.

To meet this demand, companion platforms have taken sharply divergent architectural paths:
1. **Pre-/Post-Scripting Pipelines** (e.g., **JanitorAI**, **AI Dungeon**): The platform wraps a single one-shot Large Language Model (LLM) completion call in deterministic scripting hooks (executed before and/or after inference).
2. **Tool-Calling with Client-Side Exposure** (e.g., **Wyvern Chat**): The platform permits function/tool calling and provides advanced storage layers, but leaks internal tool executions and data payloads into the player's conversation interface.
3. **Autonomous Agentic Sandbox Proxying** (**RACHEL**): The platform acts as a drop-in chat-completions-compatible Agentic Harness Middleware running a multi-round LangGraph agent loop. The LLM autonomously inspects player intent, writes and executes computational scripts in an isolated V8 JavaScript sandbox, mutates multi-dimensional structured state, and streams only clean narrative prose back to the player.

This comparative study analyzes the architectural mechanics, strengths, failure modes, memory paradigms, and performance trade-offs of these competing approaches.

---

## 1. Architectural Overview & Execution Pipelines

The fundamental divergence across these platforms lies in **who triggers mechanics** and **how state is preserved across turns**.

```
A. JanitorAI (Pre-Scripted One-Shot)
[User Input] ---> [Pre-Script (Regex Check)] ---> [One-Shot LLM Call] ---> [User UI]
                       |                                ^
                       +--- (Embed stats in prompt) ----+
                       (No server storage; relies on AI echoing stats)

B. AI Dungeon (Multi-Stage Lifecycle Hooks)
[User Input] ---> [Input Script] ---> [Context/Pre-LLM Script] ---> [One-Shot LLM] ---> [Output Script] ---> [User UI]
                                             ^                            |                    |
                                             +--- [Persistent State] <----+--------------------+

C. Wyvern Chat (Tool Calling with GUI Exposure)
[User Input] ---> [LLM Call] ---> [Tool Call Triggered] ---> [Creator Massage Hook] ---> [User UI (Tool Leaked)]
                       ^                                             |                          |
                       +----------------- [Tool Result] <------------+                          v
                       |                                                                 [Narrative UI]
                       +--- [RAG Memory / Feature-Complete Storage]

D. RACHEL (Autonomous Agentic Sandbox Proxy)
[User Input] ---> [Proxy Interception]
                        |
                        v
               [LangGraph Agent Loop] <------------------------------------+
               |  1. Ingest turn history & resolve turn key                |
               |  2. LLM autonomously decides whether to invoke tools       |
               |  3. Runs execute_code_sandbox in isolated V8 JS isolate   |
               |  4. Mutates state, hidden_state, plan, summary            |
               |  5. LLM generates grounded narrative response             |
                        |                                                  |
                        +--- (Iterates until complete, max iterations) ----+
                        |
                        +---> Streams [reasoning_content] (tools/thinking/orchestration)
                        v
               [Clean Narrative Response] (Clean UI + discrete proxy annotation)
```

---

## 2. Platform-by-Platform Deep Dive

### 2.1 JanitorAI: The Pre-Scripted One-Shot Pipeline

**Architecture & Execution Model**:
JanitorAI allows bot creators or client-side scripts to run code immediately before sending a one-shot completion request to the LLM. The script can perform basic string operations, format template variables, or compute values based on the incoming user message.

**Trigger Mechanism ("Regex-and-Pray")**:
Because JanitorAI scripts run before the LLM has seen or interpreted the user's message, function execution must rely entirely on regex pattern matching. For a script to roll an attack or deduct gold, the user must format their input according to rigid syntactical conventions (e.g., `[attack: goblin with sword]` or `!buy potion`). If the player types organic natural language (e.g., *"I lunge forward, slicing at the goblin's flank with my broadsword"*), the regex trigger fails silently.

**Storage & State Persistence**:
JanitorAI lacks a server-side persistent storage layer for dynamic game variables. Bot creators attempt to circumvent this limitation by round-tripping state through the LLM itself:
1. The script embeds current stats (e.g., `<stats>HP: 20, Gold: 50</stats>`) into the system prompt or user prompt.
2. The system prompt instructs the LLM: *"At the end of every response, output the updated stats inside `<stats>` tags."*
3. On the subsequent turn, the pre-script regex-extracts the `<stats>` block from the prior assistant message to determine the new baseline.

**Critical Failure Modes**:
* **LLM "Stat Massaging" & Hallucination**: LLMs are probabilistic text generators, not database transactions. The LLM frequently fudges numbers cooperatively (e.g., deciding the player only took 2 damage instead of 12 because the battle was tense), alters variable keys, or omits the tag block entirely when generating creative prose.
* **Format Corruption**: A single missing bracket or markdown formatting variation breaks the client regex, resetting or permanently corrupting player stats.
* **Context Bloat**: Persisting complex inventories, cooldowns, and quest logs purely within prompt text consumes valuable context window tokens on every single turn.

---

### 2.2 AI Dungeon: Multi-Stage Lifecycle Hooks with Native Storage

**Architecture & Execution Model**:
AI Dungeon provides a structured scripting lifecycle designed to support interactive fiction. Its execution pipeline is divided into three distinct hook stages:
1. **Input Script**: Executes immediately when the player submits an action (Do / Say / Story).
2. **Context Script (Pre-LLM)**: Executes right before the prompt payload is sent to the LLM. This hook is vital for handling "Continue Narration" actions where no new player input exists, allowing the script to dynamically inject world lore or adjust prompt instructions.
3. **Output Script**: Executes on the raw completion returned by the LLM, enabling the creator to massage, filter, or append text before rendering the output in the user's reading window.

**Storage & State Persistence**:
Unlike JanitorAI, AI Dungeon provides a native persistent storage layer:
* Creators have access to a persistent `state` dictionary that survives across turns.
* World Info / Memory entries can be programmatically activated or updated.

**Critical Failure Modes**:
* **Rigid Hook Constraints**: Like JanitorAI, AI Dungeon's pre-LLM hooks run *before* model inference. The script must anticipate every player intention using string matching and heuristics.
* **Lack of Model-Driven Decision Making**: The LLM cannot say: *"I need to check the player's agility modifier and roll a d20 before deciding if this door opens."* The scripting layer must decide whether to roll before the LLM generates the narrative, often leading to disconnected rolls or awkward narrative dissonance when the player's natural language action does not align with the script's assumptions.
* **Output Script Fragility**: Post-processing LLM prose with regex replacements or string transformations frequently clips sentences, introduces grammatical errors, or mangles formatting.

---

### 2.3 Wyvern Chat: Tool Calling with GUI Exposure & Advanced Storage

**Architecture & Execution Model**:
Wyvern Chat embraces native LLM tool calling (function calling). When the model generates a response, it can emit structured tool invocations. The platform executes the function, allows the creator to massage the returned payload, and returns the result back to the model for final synthesis.

**Storage & Memory Capabilities**:
Wyvern Chat offers one of the most comprehensive memory and persistence stacks among companion platforms:
* A feature-complete persistent storage layer for variables and character data.
* Integrated Retrieval-Augmented Generation (RAG) that indexes past story events, lorebooks, and character biographies into a vector database for semantic retrieval over long sessions.

**Critical Failure Modes**:
* **Immersion-Breaking GUI Leakage**: In Wyvern Chat, tool messages and intermediate execution payloads are rendered directly in the user GUI alongside the story. The player sees raw JSON payloads, mechanics function names, or debug strings intermingled with roleplay prose. This destroys the suspension of disbelief essential to narrative roleplay.
* **Creator Overhead**: Bot creators must write custom parsing and massage logic to handle tool inputs and format outputs so that the model does not get confused by its own leaked history.

---

### 2.4 RACHEL: Agentic Harness Middleware with a Sandbox

**Architecture & Execution Model**:
RACHEL (**R**pg **A**gent **CH**at **E**valuation **L**oop) takes a fundamentally different approach. Instead of running external scripting hooks around a one-shot LLM call, RACHEL acts as an OpenAI-compatible reverse proxy sitting between any chat client (JanitorAI, SillyTavern, etc.) and upstream LLM providers (via OpenRouter).

Inside the proxy, RACHEL executes a multi-round **LangGraph agent loop**:
1. **Model Autonomy**: The LLM is provided with a deterministic computational tool (`execute_code_sandbox`). The LLM itself decides *when* a calculation is necessary, *which* variables to inspect or mutate, and *how* to apply game rules based on its interpretation of the player's natural language input.
2. **Deterministic V8 JS Sandbox**: All mathematical calculations, dice rolls, and inventory mutations are executed inside an isolated V8 JavaScript isolate sandbox (`py-mini-racer`). True RNG helpers (`roll_xdy`, `contest`) eliminate LLM probability biasing and cooperative dice fudging.
3. **Structured Multi-Dimensional State**: State is partitioned into four distinct architectural layers:
   * **`state`**: Public mutable attributes (HP, inventory, gold, active buffs).
   * **`hidden_state`**: Mechanistic variables hidden from the player but visible to the LLM (traps, secret NPC suspicion levels, disease timers).
   * **`plan`**: Narrative progression checklist and NPC agenda items keeping the story arc focused.
   * **`summary`**: Rolling narrative memory injected at scheduled intervals.
4. **Clean UI Separation**:
   * All intermediate thinking (`<think>`), tool calls, JavaScript code execution, and background orchestration signals are routed strictly through `delta.reasoning_content` in streaming mode, or kept internal to the proxy loop.
   * The player's reading interface receives **100% clean narrative prose**, accompanied only by a discrete one-line metadata annotation (`[proxy: session=... turn=... turn_number=...]`).
5. **Turn Key Isolation & Branching Safety**:
   * Every turn execution is assigned a cryptographically unique 24-character hex **Turn Key** (`SHA-256[:24](session_id + "\0" + timestamp)`).
   * Swiping, retrying, or editing past messages in the client loads the exact historical snapshot associated with that prior turn key, completely preventing duplicate item drops or corrupted stat mutations during retries.
6. **Best-Effort State Rehydration**:
   * The incoming `messages` array is treated as the ground truth. If the local proxy database is wiped, RACHEL can reconstruct state history from message annotations alone (cold-start recovery).

---

## 3. Comprehensive Feature Comparison Matrix

| Architectural Dimension | JanitorAI (Pre-Scripted) | AI Dungeon (Lifecycle Hooks) | Wyvern Chat (Tool-Calling) | RACHEL (Agentic Harness Middleware) |
| :--- | :--- | :--- | :--- | :--- |
| **Pipeline Model** | Pre-request script + 1-shot LLM call | 3-stage hooks (Input $\to$ Context $\to$ Output) + 1-shot LLM | Multi-round tool calling | Multi-round LangGraph agent loop |
| **Function Triggering** | Regex on player input ("regex-and-pray") | Regex / event hooks on raw strings | Native LLM tool calling | Autonomous LLM tool calling (`execute_code_sandbox`) |
| **Execution Environment** | Client-side JS / string templates | Sandboxed JS lifecycle scripts | Platform runtime hooks | Isolated V8 JavaScript Isolate (`py-mini-racer`) |
| **Storage Layer** | **None** (relies on LLM echoing prompt tags) | **Native state dictionary** | **Feature-complete storage + RAG** | **4-Pillar Persistent State** (`state`, `hidden_state`, `plan`, `summary`) |
| **Mathematical Accuracy** | Poor (LLM hallucinates/massages stats) | Moderate (computed in script, but context can drift) | High (handled via tool returns) | **100% Deterministic** (computed strictly inside V8 sandbox) |
| **Dice & RNG Mechanics (Without Creator Script)** | **Biased / Hallucinated** (LLM text prediction fudges rolls based on narrative bias) | **Biased / Hallucinated** (LLM text prediction fudges rolls or uses uncoupled randomizer) | **Biased / Hallucinated** (LLM text prediction fudges rolls if no tool defined) | **True RNG** (`roll_xdy` and `contest` available out of the box in sandbox) |
| **Dice & RNG Mechanics (With Creator Script)** | **Regex-Dependent** (Script calculates RNG, but firing strictly requires regex match on input; prone to missed triggers and AI echoing/massaging) | **Regex/Hook-Dependent** (Script calculates RNG on input/context hooks, but firing depends strictly on rigid regex/input pattern matching) | **Tool-Triggered Math** (Deterministic tool rolls, but intermediate tool payloads are exposed in user GUI) | **LLM-Triggered Sandbox RNG** (LLM decides when/how to call `roll_xdy`/`contest`; vastly outperforms rigid regex in natural language UX and intent interpretation) |
| **Secret / Hidden State** | None (everything in prompt is visible to AI & user) | Limited (script state) | Supported in backend state | **First-class `hidden_state`** (invisible to player UI) |
| **Branching & Swipe Safety** | Fragile (retries corrupt prompt stats) | Moderate (linear timeline focus) | Moderate (retries can desync state) | **Turn Key Branch Isolation** (swipes and retries load exact historical state) |
| **UI Immersion & Leakage** | Clean text (or messy prompt tags if leaked) | Clean text (filtered by output script) | **Leaked** (tool messages visible in GUI) | **100% Clean Narrative** (tool logs streamed to `reasoning_content`) |
| **Drop-in Client Support** | N/A (platform-specific) | N/A (platform-specific) | N/A (platform-specific) | **Universal** (works with JanitorAI, SillyTavern, or any OpenAI-compatible client) |
| **End-to-End Latency** | Fast (~1–3s, single LLM pass) | Fast (~1–3s, single LLM pass) | Slower (~3–8s, multi-round tool calling) | Slower (~3–8s, multi-round agent loop) |

---

## 4. The Core Dilemma: Regex-and-Pray vs. Autonomous Sandboxing

The primary flaw of pre-scripting platforms (JanitorAI, AI Dungeon) is what can be termed the **"Regex-and-Pray" Bottleneck**:

```
Player Input: "I feign a retreat toward the crumbling archway, waiting for the orc to overextend."

Script Regex:  /^\s*\[?(?:attack|strike|hit)\s+(?<target>\w+)\]?/i
               ===> MATCH FAILED.
               ===> No dice rolled. No stamina deducted. No tactical advantage registered.
```

In tabletop roleplaying, player actions are expressive, contextual, and multifaceted. Forcing players to format their actions as pseudo-command codes destroys the natural flow of roleplay. If they write naturally, static regex triggers fail to fire.

Furthermore, pre-request scripts suffer from **premature evaluation**:
* The script must execute *before* the model has analyzed the scene.
* The script cannot know if the player's sword actually connects, whether the enemy parries, or if an environmental hazard intervenes.

### How RACHEL Solves the Dilemma

RACHEL shifts the responsibility of tool execution to the LLM itself:
1. **Natural Language Understanding**: The LLM reads the player's expressive prose.
2. **Intent & Mechanics Mapping**: The LLM determines: *"The player is attempting a deceptive combat maneuver. This requires an Agility contest against the Orc's Perception, followed by a potential sneak attack damage roll."*
3. **Autonomous Code Generation**: The LLM calls `execute_code_sandbox` with a tailored JavaScript snippet:
   ```javascript
   const playerRoll = roll_xdy(1, 20) + state.player.modifiers.agility;
   const orcRoll = roll_xdy(1, 20) + 1; // Orc perception modifier
   let success = playerRoll > orcRoll;
   let damage = 0;
   if (success) {
     damage = roll_xdy(2, 6) + state.player.modifiers.stealth;
     state.orc.hp = Math.max(0, state.orc.hp - damage);
   }
   hidden_state.archway_stability -= 1; // Hidden trap countdown
   console.log(`Contest: Player ${playerRoll} vs Orc ${orcRoll}. Success: ${success}. Damage: ${damage}.`);
   ```
4. **State Mutation & Grounding**: The sandbox runs, deterministically calculates the values, updates `state` and `hidden_state`, and feeds the output snapshot back to the model.
5. **Grounded Narration**: The LLM narrates the exact mechanical outcome without math errors or narrative contradiction.

The sandbox completely eliminates both the **regex-and-pray trigger failure** and the **stat hallucination problem**.

### 4.2 Trigger Reliability: Regex Matching vs. LLM Autonomous Firing

To be fair, RACHEL's dice rolls and state mutations are also dependent on the LLM choosing to fire the respective sandbox tool functions. If the LLM does not invoke `execute_code_sandbox`, the mechanics will not execute.

However, an LLM performs significantly better than strict regex in both the **user experience** and **natural language interpretation** departments:
* **Nuanced Intent Recognition**: A regex trigger cannot easily distinguish between flavor text (*"I nervously tap my blade against my shield"*) and an offensive maneuver (*"I feign left and drive my blade toward his guard"*). Capturing the infinite variety of organic player inputs via regex requires either an unmaintainable web of brittle patterns or rigid command codes (`!roll d20`, `[attack: orc]`). The LLM understands contextual intent natively.
* **Frictionless Roleplay**: Players are freed from formatting constraints. They do not have to write like programmers or memorize bot-specific syntax; they simply write natural prose, and the LLM bridges the gap between player narrative and computational sandbox execution.
* **Contextual Evaluation**: The LLM evaluates the full conversational state (active buffs, environmental hazards, narrative stakes) before deciding whether a roll is warranted, rather than blindly firing on keyword occurrence.

---

## 5. Memory Architecture: RAG vs. Rolling Summaries vs. Structured State

A frequent topic in AI companion design is the choice of memory architectures. Wyvern Chat utilizes vector-based **Retrieval-Augmented Generation (RAG)**, whereas RACHEL employs a **Rolling Summary** combined with **Multi-Dimensional Structured State**.

### 5.1 The Two Fundamental Facets of RPG Memory

To evaluate memory systems properly, we must distinguish between two fundamentally different types of game information:

```
+-----------------------------------------------------------------------------------+
|                                RPG GAME MEMORY                                    |
+-----------------------------------------+-----------------------------------------+
|        Semantic Story Memory            |        Mechanistic State Storage        |
|  - Past dialogue with the tavern keeper |  - Current player HP (42 / 65)          |
|  - The name of the ancient lost sword   |  - Gold balance (152 gp)                |
|  - Emotional relationship with an NPC   |  - Poison status effect (3 turns left)  |
|  - World lore and historical events     |  - Hidden dungeon trap trigger state    |
+-----------------------------------------+-----------------------------------------+
| Best Handled By:                        | Best Handled By:                        |
| Semantic Retrieval / RAG / Summaries    | Structured Key-Value State & Sandbox    |
+-----------------------------------------+-----------------------------------------+
```

### 5.2 Why RAG Fails at State Tracking

Vector databases operate on semantic similarity (cosine distance between text embeddings). They are inherently unsuited for mechanical state:
* If a vector database retrieves a chunk from Turn 12 stating *"The player has 45 HP"* and another chunk from Turn 45 stating *"The player has 22 HP"*, the LLM often conflates or averages the two, or reverts to the older value.
* Semantic retrieval cannot compute transitions (`HP = 22 - 7 = 15`).
* Hidden mechanics (e.g., an invisible loyalty meter reaching a threshold) cannot be queried semantically when the player has never explicitly uttered the secret variable name.

### 5.3 The <200 Turns Reality: Is RAG Overkill for RPG Sessions?

Wyvern Chat's RAG system shines across massive, hundred-chapter visual novels or long-running virtual worlds. However, in typical single-session or episodic tabletop RPGs:
* **Typical Session Length**: Most focused RPG adventures or character card scenarios conclude or reset within **100 to 200 turns**.
* **Context Windows**: Modern LLMs feature context windows of 32k to 128k+ tokens. A 200-turn chat history easily fits within modern context windows with minimal trimming.
* **RAG Retrieval Noise**: Vector chunking frequently pulls irrelevant narrative fragments (e.g., fetching a description of a sword from a prologue when the player is simply asking for a knife at dinner).
* **Architectural Complexity**: RAG requires vector embeddings, chunking pipelines, index stores, and semantic rerankers—introducing potential failure points and latency.

### 5.4 The Developer's Verdict

> **Core Architectural Principle**:
> Both **story memory** (narrative continuity) and **structured stat storage** (mechanics simulation) are essential for high-fidelity roleplay. Neither can replace the other.

* **For Mechanistic State**: RACHEL's `state` and `hidden_state` provide 100% deterministic tracking that vector databases cannot replicate.
* **For Story Memory**: Within sub-200 turn RPGs, RACHEL's **rolling narrative summary** (calculated periodically or probabilistically and injected into the turn context every turn) provides sufficient long-term plot grounding without the overhead, noise, and infrastructure requirements of a full RAG vector pipeline. For massive multi-thousand turn campaigns, hybridizing RACHEL's structured sandbox with a dedicated semantic RAG layer represents the ideal architectural frontier.

---

## 6. The Performance Trade-Off: Latency vs. Agency

The primary compromise in RACHEL's design is **inference latency**.

### 6.1 The Latency Cost of Agentic & Tool-Calling Loops

* **One-Shot Systems (JanitorAI, AI Dungeon)**:
  * Number of LLM passes: Exactly **1**.
  * Total duration: Typically **1.0 to 3.0 seconds**.
  * User perception: Fast, snappy, instantaneous generation.
* **Multi-Round Tool / Agentic Systems (Wyvern Chat, RACHEL)**:
  * Number of LLM passes: Typically **2 or more** (Round 1: Initial evaluation & tool call generation $\to$ Tool/sandbox execution $\to$ Round 2: Final grounded narrative synthesis).
  * Total duration: Typically **3.5 to 8.0 seconds** depending on upstream model latency and token length.
  * Architectural equivalence: Both Wyvern Chat and RACHEL fundamentally share the same end-to-end latency profile. Any architecture granting the LLM the ability to invoke tools and observe deterministic outcomes before narrating inevitably requires multiple serial inference passes per turn.

### 6.2 How RACHEL Mitigates Latency

To offset the performance penalty of multi-round agentic execution, RACHEL implements several targeted optimizations:

1. **Live Streaming of `reasoning_content`**:
   * Rather than buffering silently during tool calls and sandbox execution, RACHEL streams live intermediate progress via OpenAI-compatible `delta: {"reasoning_content": ...}` chunks.
   * Thinking tokens (`<think>`), tool invocations, code stdout, and orchestration milestones (e.g., `[Background Tasks: Story Planning triggered...]`) are visible to the client in real-time.
   * This keeps client HTTP sockets alive, prevents gateway timeouts, and provides continuous visual feedback, drastically reducing perceived wait time for the user.
2. **Bitwise-Identical Prefix Caching (`cached_constructed_user_message`)**:
   * In Round 1, RACHEL injects its dynamic game state and instructions into the final user message.
   * This constructed message is cached bitwise identically for Round 2 and subsequent iterations.
   * Upstream providers (e.g., Anthropic, DeepSeek, OpenRouter) can leverage KV-cache prefix hits, cutting Round 2 inference time by up to 50%.
3. **Strict Wall-Clock Sandbox Limits**:
   * The V8 isolate sandbox enforces an 8-second hard timeout and zero-network access to ensure user-generated or LLM-generated code cannot hang the proxy worker.

---

## 7. Comparative Summary & Architectural Takeaways

| Feature Need | Winner | Rationale |
| :--- | :--- | :--- |
| **Instant Response Time** | **JanitorAI / AI Dungeon** | One-shot execution will always complete faster than a multi-round agentic loop. |
| **Mathematical Accuracy & RPG Mechanics** | **RACHEL** | Deterministic V8 sandbox execution eliminates math hallucination and cooperative dice fudging. |
| **Natural Language Freedom (No Syntax Codes)** | **RACHEL / Wyvern Chat** | Model-directed tool calling eliminates rigid "regex-and-pray" command formatting. *(Caveat: Wyvern requires the creator to meticulously write Lua code, while RACHEL is happy with the creator writing "For every attack, roll a 3d6 and if it is more than 12, it lands. If it is 18, make it a critical hit" as the LLM writes the code itself).* |
| **Player Immersion & Visual Polish** | **RACHEL** | Clean separation of narrative text from mechanics logs; tool calls never leak into the user's reading GUI. |
| **Branching & Retry Resilience (Swiping)** | **RACHEL** | Cryptographic Turn Keys isolate states across swiped or retried branches without database corruption. |
| **Episodic Narrative Memory (<200 turns)** | **RACHEL** | Rolling summaries provide sufficient plot continuity without RAG retrieval noise or vector overhead. |
| **Deep Lore Retrieval (>1000 turns)** | **Wyvern Chat** | Vector RAG excels at retrieving ancient world lore across long-running campaigns. |

### Conclusion

While pre-scripting platforms like JanitorAI and AI Dungeon offer unmatched speed for casual dialogue, they break down when tasked with simulating structured tabletop mechanics. Their reliance on regex triggers forces players into rigid command syntax, and their lack of deterministic execution leads to constant stat corruption and mathematical hallucinations.

Wyvern Chat proves the power of native tool calling and persistent storage, but suffers from immersion-breaking GUI leaks that expose raw mechanics to the player.

**RACHEL represents the middle-out synthesis**: by encapsulating a multi-round LangGraph agent loop behind a standard completions API proxy, it grants the LLM full mechanical agency via an isolated V8 sandbox while preserving 100% of the player's reading immersion. For tabletop RPG adventures under 200 turns, RACHEL's combination of structured state and rolling summaries provides the optimal balance of mechanical rigor, narrative freedom, and architectural simplicity.
