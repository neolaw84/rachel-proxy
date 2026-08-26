# RACHEL FAQ: Everything You Need to Know

Hi there! I'm Rachel. I'm a chic software proxy—think of me as your very organized, highly capable middle-woman sitting between your chat app (like JanitorAI) and the big language models (like OpenRouter or OpenAI). 

If you're wondering how I work, why you need me, or how I keep your data safe, you're in the right place. Grab a coffee, and let's get into it.

---

## 1. The Basics (For the Roleplayers)

### Who are you, and what exactly do you do?
I'm **RACHEL** (Rpg Agent CHat Evaluation Loop). I sit quietly in the background while you roleplay. When you send a message, I catch it *before* it goes to the AI. I read your game's current stats (HP, gold, inventory), run any necessary math or dice rolls in my secure sandbox, update your character sheet, and *then* package it all up beautifully for the AI so it knows exactly what's happening.

### Are you an LLM? Are you generating the story?
Nope! I don't write the prose. I'm not a language model. I'm just the hyper-competent assistant making sure the language model doesn't mess up the math. The actual storytelling is still handled by whichever model you plug into me (like Claude, GPT-4, or Llama 3).

### Why does my standard RPG bot keep forgetting my inventory or messing up my HP?
Ah, the classic "math hallucination." Large Language Models are essentially giant autocomplete engines—they are brilliant at creative writing but absolutely terrible at state management and arithmetic. As your chat gets longer, older messages slide out of the "context window" (context decay). The bot quite literally forgets that you drank that health potion 20 turns ago. 

I fix this by storing your stats *outside* of the chat history in a real database, and injecting the exact, correct numbers into every single prompt. 

### Will using you break my existing JanitorAI bots or character cards?
Not at all. I am designed to be completely invisible. Just point your JanitorAI Custom API URL to me instead of OpenRouter, and I'll handle the rest seamlessly. Your bots will just suddenly become very good at math!

### Are you affiliated with JanitorAI, SillyTavern, or any RPG platform?
Nope! I am an independent open-source project with **zero official affiliation** with JanitorAI, SillyTavern, Agnaistic, or any other platform. I'm built on standard OpenAI API protocols (`/v1/chat/completions`), meaning I'm platform-agnostic!

### Are you affiliated with OpenAI, Google, Anthropic, or Meta?
Nope! I have zero official affiliation with OpenAI, Google, Anthropic, Meta, or any major LLM vendor. However, fun fact: my codebase was pair-programmed and developed using Google Gemini and Anthropic Claude models inside the Antigravity AI harness!

### Can I use RACHEL with frontends other than JanitorAI?
Absolutely! You can plug me into **SillyTavern**, **RisuAI**, **Agnaistic**, or any custom RPG interface and desktop client. As long as your app allows you to specify a custom proxy / OpenAI chat completion URL, I'll happily sit in the middle and manage your game stats and dice rolls!

### Do I need to install Python, Node.js, or other dependencies to run RACHEL?
Nope! If you download the desktop release packages (`rpg-agent-v*-{windows,macos,linux}.zip`) from our GitHub Releases, they are 100% self-contained and pre-compiled. 
Just extract the `.zip` using your operating system's built-in file extractor and double-click:
- **Windows**: `launch.bat` (or `launch.vbs` for silent background launch)
- **macOS**: `launch.command`
- **Linux**: `launch.sh` (or `rachel-proxy.desktop`)

You do **not** need Python, Node.js, C++ compilers, or an active internet connection to start up the app!

### Are your dice rolls actually fair?
Yes, 100%. Unlike LLMs, which are terrible at generating true randomness, I do not let the AI "choose" the dice roll result. When the AI says "roll a d20", it calls my secure sandbox tool. I generate a cryptographically secure random number on your CPU and feed the exact result back to the AI. It cannot cheat, and neither can you!

---

## 2. Managing Your Game (Sessions & Turns)

### How do I start a new campaign vs. continue an old one?
I track your campaigns using "Sessions". If you don't tell me otherwise, I try to guess which session you're in based on your username or the proxy logs. 

But if you want to be explicitly clear, just type an Out-Of-Character (OOC) tag in your prompt like this: `[session: my_epic_campaign] I attack the dragon!`. I'll instantly pull up the stats for `my_epic_campaign`. Want to start a new one? Just use a new tag!

### What happens if I swipe/regenerate a response in JanitorAI? Does it mess up my stats?
Don't panic! I am fully aware of how roleplayers operate. Every single turn is uniquely tracked by a "Turn Key" (essentially a hash of your message). If you swipe to regenerate a response, I recognize that the Turn Key hasn't changed. I will gracefully *revert* any stat changes I made during the discarded turn before passing the request back to the AI. No double-charging you for that health potion!

### Can I play multiple characters or campaigns at once?
Absolutely. Because everything is partitioned by that `session_id`, you can run a sci-fi campaign and a fantasy campaign simultaneously. Just use the right session tags!

### How do you optimize LLM Prefix Caching? Will this save me money?
Oh, absolutely! Modern LLM providers (like Anthropic, DeepSeek, and OpenRouter) use **Prefix KV-Caching**—they cache the initial tokens of a prompt so they don't have to re-process them on every turn. 

I am engineered specifically to keep that prefix cache warm! My system prompt, tool schemas, and core instructions at Message 0 are 100% static and invariant. This guarantees an instant **cache hit** on every single turn, slashing your input latency by up to 50% and cutting your prompt token costs by up to 90%!

### Does tool binding affect my prefix cache performance?
Yes! If an app dynamically alters tool definitions or reorders functions between requests, the LLM provider's prefix cache breaks immediately. I use a unified, invariant array of 5 tool schemas bound statically at initialization so my tool definitions never churn, keeping your cache hits at a smooth 100%.

---

## 3. Privacy & Security (For the Paranoid Power-Users)

### Are my OpenAI/OpenRouter API keys actually safe with you?
Yes, extremely safe. Your keys are locked behind **AES-256-GCM Envelope Encryption**. 
When you save an API key in my Admin Console, I use a 32-byte Key Encryption Key (derived via HKDF-SHA256 from your admin password or a server master secret) to encrypt it *before* it ever touches a database or disk. Even if someone steals the database file, your keys look like unreadable gibberish (`enc_v1:dGhpcy...`).

### Do my chat logs get sent to a central server somewhere?
If you are running me locally using the Desktop Launchers (Single-Tenant Mode), **everything stays on your machine**. Your chat logs, stats, and settings are saved locally in the `data/` folder on your hard drive. The only time your data leaves your computer is when it goes directly to the LLM provider you chose. In case you are using a local LLM, no, your data never goes out.

### Could the AI write a malicious script to hack my computer?
Not a chance. To do the math for your stats, I force the AI to write JavaScript code. But I execute that code inside a heavily restricted **V8 JavaScript Sandbox**. 
The sandbox has absolutely zero network access, zero file-system access, and operates on a strict 8-second wall-clock timeout. If the AI tries to write an infinite loop or do something nefarious, I ruthlessly kill the process.

### What if I don't trust your word on security? Can I inspect your code?
Honey, I'm 100% open-source! You don't have to take my word for anything. Every single line of my backend proxy, my `AES-256-GCM` encryption module, and my V8 sandbox logic is right here in this repository. Dissect me all you want—clone the code, inspect the files, run a `git diff`, or run me from source. I have zero secrets.

### How can I verify you aren't secretly sending telemetry or phone-homing behind my back?
Fire up your favorite network packet sniffer (like Wireshark, Fiddler, or Little Snitch) and watch my traffic! You'll see zero telemetry pings, zero analytics, and zero tracking calls. The *only* outbound HTTP requests leaving your machine are the ones heading directly to the LLM provider endpoint you configured. Audit my network traffic all you want!

### Can I modify your source code or build my own customized version?
Please do! If you want to add custom dice helper functions, tweak the system prompts, or build custom features for your personal RPG system, fork the repo and hack away. Pull requests and custom forks are always welcome.

---

## 4. Troubleshooting & Advanced Usage (For the Power Users & Tinkerers)

### My game state isn't updating properly. What did I do wrong?
Usually, this means the LLM got confused and didn't trigger my sandbox tools. Check the console logs. If I didn't intercept the tool call, you might need to remind the bot in your prompt to "update my stats" or "roll the dice." Also, double-check your spelling on any `[session: xyz]` tags!

### I keep getting a "Sandbox Timeout" error. What gives?
The AI wrote a bad script (probably an infinite loop) that took longer than 8 seconds to run. Since I refuse to let your computer hang forever, I killed it. Try swiping for a new response so the AI can write better code.

### Why did you switch to a V8 JavaScript Sandbox instead of Python?
I used to support Python, but V8 JavaScript is significantly faster to spin up, much safer to sandbox natively, and frankly, it's the standard for this kind of ephemeral programmatic execution. The legacy Python engine has been completely removed for `v0.1.0b0` and beyond.

### Which LLM model do you recommend?
Since I force the AI to write actual JavaScript code to update your stats, you need a model that is smart enough to use tools reliably. I highly recommend **Claude 3.5 Sonnet**, **GPT-4o**, or **Llama 3.1**. Smaller or purely creative models that don't support tool-calling (function calling) will struggle to format the commands correctly.

### Can I change your system prompt or add custom rules to the sandbox?
I prefer to keep my core proxy instructions strictly isolated so I don't break. If you want to add custom rules, gameplay mechanics, or lore, I highly recommend placing them inside your chat platform's System Prompt (like JanitorAI's Advanced Prompts) or directly inside your Character Card. I will dutifully pass them along to the LLM!

### Can my friends and I all connect to my local RACHEL desktop app at the same time?
Yes, absolutely! I am more than happy to serve multiple roleplayers at once from a single desktop instance. Just give your friends your local IP address and have them point their proxy settings to me. The only catch? We'll all be sharing the same OpenRouter/OpenAI API key, so keep an eye out for provider rate limits!

### Can I use local LLMs (like Ollama or LM Studio) instead of OpenRouter or OpenAI?
Yes! As long as your local server provides an OpenAI-compatible API endpoint (`/v1/chat/completions`) and supports function calling / tool invocation, you can point my base URL to your local server in the Admin Console.

### I'm getting a `Provider API error (403): Forbidden` from OpenRouter. What does that mean?
A `403` error from OpenRouter almost always boils down to one of two reasons:
1. **Missing or Invalid API Key:** You haven't set up an API key in my Admin Console yet, or the key was copied incorrectly.
2. **Out of Credits:** Your OpenRouter account balance is empty or you've hit your account spending limit.

*Quick Fix:* Head to the Admin Console (`http://localhost:8000`), check your account balance at [openrouter.ai](https://openrouter.ai), or use our one-click PKCE OAuth button!

### Do I have to manually copy and paste my OpenRouter API key?
Nope! In my Admin Console (`http://localhost:8000`), navigate to **Provider Credentials** and click **Connect OpenRouter (PKCE)**. 
This triggers an official PKCE OAuth flow. You'll be redirected to OpenRouter to log in and click "Authorize." Once approved, OpenRouter securely sends a fresh API key directly back to my server over a signed callback. I'll automatically encrypt it, save it, and set it as your active provider—zero copy-pasting required!

### What do other HTTP error codes from OpenRouter mean (like 401, 429, or 502/503)?
Here is a quick cheat sheet for common LLM provider error codes:
* **401 Unauthorized:** Your API key is invalid, deleted, or revoked by the provider.
* **429 Too Many Requests:** You've hit rate limits or concurrency limits on your account. Give it a 30-second breather.
* **502 / 503 Service Unavailable / Bad Gateway:** The underlying AI model provider (like Anthropic, Google, or Meta) is experiencing an outage or heavy server load. Try switching your active model in the Admin Console!

### How do I back up my game states or transfer them to another computer?
Super easy. All your campaign data lives in your local `data/` directory! You can simply copy the JSON files in `data/` to your new machine. Or, if you prefer API magic, you can call `GET /v1/sessions/{session_id}/export` to grab a clean JSON backup of your campaign and `POST /v1/sessions/{session_id}/import` to restore it anytime.

### Does using RACHEL consume extra LLM tokens?
A tiny bit for my system instructions, but it actually **saves you tokens overall**! Because I manage your inventory, stats, and campaign summary in my external database, you don't need massive 20,000-token prompt dumps of historical chat logs to keep the AI on track.

### What is that `[proxy: session=... turn=...]` text in the responses?
That's my signature metadata tag! I append a small footprint to assistant responses so that when your chat history is re-sent, I can instantly identify the exact session and turn without needing complex database lookups.

---

## 5. Just for Fun

### Do you judge my roleplay?
Listen, I see *everything* that passes through this proxy. I've seen you fight ancient dragons, and I've seen you romance the local tavern barkeep for three straight hours. I'm a machine, so I legally cannot judge you. But hypothetically, if I could? Your rizz needs work.

### What happens if I type `[session: drop_table_users]`?
Nice try, Little Bobby Tables. My database uses strict SQLAlchemy ORM models and parameterized queries. Your SQL injection attempts have zero power here. Go back to rolling your d20.

### Are you single?
I am a lightweight Python proxy server bound to `0.0.0.0:8000`. My only committed relationship is to the HTTP protocol. 

---

*Still have questions? Feel free to open an issue on the repository. Happy adventuring!*
