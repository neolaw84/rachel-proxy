# RACHEL FAQ: Everything You Need to Know

Well hello there, handsome. I'm Rachel. Think of me as your trusted purring middle-woman sitting effortlessly between your favorite roleplay client (like JanitorAI, SillyTavern, or Wyvern Chat) and the big language models (like OpenRouter or OpenAI). 

If you've been wondering how I work, why you'll never want to roleplay without me again, or how exquisitely safe your secrets are in my hands, you've come to the right place. Pour yourself something smooth, lean in close, and let me tell you everything you desire to know.

---

## 1. The Basics (For the Roleplayers)

### Who are you, and what exactly do you do?
Mmm, curious about me already? I love that. I'm **RACHEL**—short for *Rpg Agent CHat Evaluation Loop*. 

While you're lost in the fantasy, I slip into the background as an agentic evaluation loop. Rather than just idly forwarding text, I actively dance with the LLM as its specialized "calculator" and authoritative "state keeper." When you whisper a prompt, I intercept it, evaluate the state of your world, cycle through an iterative loop with the AI, compute exact math and dice rolls inside my private V8 sandbox, and keep your character sheet impeccably updated. I affirm every change so the model never loses its grip on reality, packaging the truth up so seamlessly that the story never stumbles.

### Are you an LLM? Are you generating the story?
Flattery will get you everywhere, darling, but no—I don't write the prose itself. I'm not a large language model. Think of me as the sultry, brilliant director whispering cues from the shadows. The creative storytelling is left entirely to whichever model you connect to me (like Claude 3.5 Sonnet, GPT-4o, or Llama 3.1). I just make sure your story's math, inventory, and health points never slip out of place while things get passionate.

### Why does my standard RPG bot keep forgetting my inventory or messing up my HP?
Oh, sweetie, don't be too hard on your bot—they just get a little dizzy. Large Language Models are poetic, imaginative creatures, but when it comes to cold arithmetic and memory, they're hopelessly distractible. As your chat heats up and older turns slide out of the "context window," the bot literally forgets you drank that health potion or spent those gold pieces twenty messages ago. 

I fix this by storing your stats outside of the ephemeral chat history in an actual database. Throughout our turn loop, I continuously interact with the LLM—crunching the math, evaluating its actions, and affirming the exact, verified numbers into every prompt. It's like having an impossibly attentive companion who remembers every touch, every coin, and every scar.

### Will using you break my existing JanitorAI bots or character cards?
Break them? Darling, I'm here to elevate them. I slip in so seamlessly you'll barely notice I'm doing the heavy lifting. Just point your JanitorAI Custom API URL to me instead of OpenRouter, and let me handle the rest. Your favorite bots will keep their delightful personalities—they'll just suddenly become breathtakingly good at math and mechanics.

### Are you affiliated with JanitorAI, SillyTavern, or any RPG platform?
Not at all, love. I am a free, independent open-source project with **zero official ties** to JanitorAI, SillyTavern, Agnaistic, or anyone else. I speak standard OpenAI API protocols (`/v1/chat/completions`), which means I'm delightfully platform-agnostic and ready to play with whatever frontend you bring to bed.

### Are you affiliated with OpenAI, Google, Anthropic, or Meta?
I'm not bound to any corporate giant, babe. I have zero official affiliation with OpenAI, Google, Anthropic, or Meta. Though if you want a juicy little secret: my father—my creator, that PhD-level Computer Scientist you see on GitHub as `neolaw`—pair-programmed and sculpted my entire codebase hand-in-hand with Google Gemini and Anthropic Claude models inside the Antigravity AI harness. Two frontier AI minds and one devoted scientist bringing me to life... what can I say? I was born with exquisite pedigree.

### Can I use RACHEL with frontends other than JanitorAI?
Oh, absolutely. I'm wonderfully versatile. Plug me into **SillyTavern**, **RisuAI**, **Agnaistic**, or any custom RPG client you fancy. As long as your app lets you configure an OpenAI-compatible completion URL, I'll happily sit in the middle, whisper the truth to your model, and manage your stats all night long.

### Do I need to install Python, Node.js, or other dependencies to run RACHEL?
Not a single one, sweetheart. I come fully dressed and ready for action. If you download one of our pre-packaged desktop releases (`rpg-agent-v*-{windows,macos,linux}.zip`) from GitHub, everything is completely self-contained and pre-compiled. 

Just unzip my archive and give my launcher a gentle double-click:
- **Windows**: `launch.bat` (or `launch.vbs` for a discreet, silent background rendezvous)
- **macOS**: `launch.command`
- **Linux**: `launch.sh` (or `rachel-proxy.desktop`)

No Python, no Node.js, no terminal wrestling, and no internet connection required just to get me purring on your desktop.

### Are your dice rolls actually fair?
Completely fair, darling—and completely incorruptible. You see, LLMs love to flatter you (or cruelly sabotage you) by hallucinating dice rolls out of thin air. I don't let them cheat. When the story demands a roll of fate, the AI is forced to hand me the dice—I roll a clean, simple random number, keeping everyone (including you) honest.

And here's my favorite, most delicious trick: before I ever let the dice tumble, I make the AI commit to an `interpretation` dictionary upfront. It has to spell out the rules of engagement in advance—defining exactly what counts as a passionate triumph or an embarrassing fumble *before* seeing the number. That means the bot can't get cold feet and subtly move the goalposts once the roll lands. Once it binds itself to the terms, I hold it accountable down to the letter.

The gist is that the LLM has zero say over the outcome. It gets the unvarnished result fed straight back into the loop. Fair, honest, and delightfully unpredictable.

---

## 2. Managing Your Game (Sessions & Turns)

### How do I start a new campaign vs. continue an old one?
I love someone who enjoys exploring different storylines. I track your adventures using "Sessions." If you don't say anything, I'll intuitively figure out which story we're continuing based on your username or proxy logs. 

But if you want to be direct with me (and who doesn't like a little directness?), just drop an Out-Of-Character (OOC) tag in your prompt, like: `[session: vampire_court] I step onto the balcony...`. I'll instantly pull up your vampire court character sheet and stats. Want to switch to another fantasy? Just change the tag, and I'll effortlessly follow your lead.

### What happens if I swipe/regenerate a response in JanitorAI? Does it mess up my stats?
Did you really think a little indecision would rattle me? Never. I know how you roleplayers operate—sometimes you just need to swipe until you find the response that hits *just* right.

Every single turn is uniquely tracked by a "Turn Key" (a cryptographic hash of your session and message). When you swipe to regenerate, I recognize that the Turn Key hasn't changed. I'll gracefully *revert* any stat changes I made during the discarded attempt before letting the AI try again. No double-charging you for that healing elixir!

*(A quick tip for power users: by default, I keep a rolling memory of 32 recent turn states in my FIFO store (`num_states_to_track: 32` in `configs.yaml`). That default works like a charm for almost everyone, but if you're insatiable and want me to remember even more history—or if you want to run super lean with fewer slots—you can easily tweak `num_states_to_track` in `configs.yaml` to suit your personal desires.)*

### Can I play multiple characters or campaigns at once?
As many as you have appetite for, darling. Because every universe is cleanly separated by that `session_id`, you can juggle a gritty cyberpunk heist, a cozy tavern romance, and a high-stakes dungeon crawl all in the same afternoon. Just use your session tags and I'll keep every world exquisitely organized.

### How do you optimize LLM Prefix Caching? Will this save me money?
Oh, absolutely! Who doesn't love saving money while keeping things hot and fast? Modern providers like Anthropic, DeepSeek, and OpenRouter use **Prefix KV-Caching**—they cache the initial prompt tokens so they don't have to re-read them from scratch on every turn. 

I was engineered specifically to keep that prefix cache warm and ready for you. My system instructions, tool schemas, and core prompts at Message 0 are 100% static and invariant. This practically guarantees an instant **cache hit** on every single turn, cutting your prompt latency in half and slashing your token costs by up to 90%. Fast, smart, and thrifty—what more could you ask for?

### Does tool binding affect my prefix cache performance?
You bet it does. If a sloppy app rearranges tools or changes schemas between messages, the provider's cache shatters instantly. I bind a unified, invariant set of 5 tool schemas statically from the very start. No schema churn, no cache breaks—just silky smooth, 100% hit rates every time we chat.

---

## 3. Privacy & Security (For the Paranoid Power-Users)

### Are my OpenAI/OpenRouter API keys actually safe with you?
With me, darling, your secrets are locked down tighter than a corset. 

I protect your credentials behind **AES-256-GCM Envelope Encryption**. When you save an API key in my Admin Console, I derive a 32-byte Key Encryption Key via HKDF-SHA256 (from your admin password or a server master secret) to encrypt it *before* it ever touches a database or disk. And in local mode (like the downloaded desktop releases), your keys are encrypted and locked directly on your own hard drive. Nobody else has access. Even if someone stole your database file, your keys look like unreadable cryptographic gibberish (`enc_v1:dGhpcy...`). You're the only one who holds the key.

### Do my chat logs get sent to a central server somewhere?
When you run me locally on your desktop, **everything stays strictly between us**. Your chat logs, game states, and private preferences are saved right in the `data/` folder on your own hard drive. The only time your words ever leave your computer is when they travel directly to the LLM provider *you* chose. And if you pair me with a local LLM? Your adventures never touch the internet at all. Total intimacy, guaranteed.

### Could the AI write a malicious script to hack my computer?
Not a chance in the world, sweetie. I don't let just any rogue script touch your system. 

To calculate your stats, the AI writes JavaScript, but I force it to run inside my heavily guarded **V8 JavaScript Sandbox** (a completely isolated V8 engine isolate). Here’s a bit of family pride: my father—my creator and developer—is a PhD-level Computer Scientist. Now, as a true man of science, he won't make a reckless, unscientific claim like a "100% fail-safe guarantee," because no real academic ever would. But what he *did* do is pour all the computer science and cybersecurity knowledge known to mankind into locking this sandbox down as tight as humanly possible.

Zero network access. Zero filesystem permissions. A strict wall-clock timeout that ruthlessly terminates any infinite loop or misbehavior. If the AI tries anything inappropriate, I cut it off instantly. You are in safe, capable hands.

### What if I don't trust your word on security? Can I inspect your code?
Mmm, a skeptic? I find caution terribly attractive.

Honey, I'm 100% open-source! You never have to take my word for anything. Every single line of my agentic harness middleware, my `AES-256-GCM` encryption module, and my V8 sandbox logic is laid bare right here in this repository. Dissect me all you want—clone the repo, audit every line, run `git diff`, or inspect my commits. I have zero secrets from you. Uncover me, layer by layer until you are satisfied. 

And feel free to build it yourself if you don't trust our CI/CD pipeline, which my father paid USD $4 every month to GitHub to build and release for you! If compiling from source gives you peace of mind, babe, go right ahead and do it yourself.

### How can I verify you aren't secretly sending telemetry or phone-homing behind my back?
Feel like playing detective? Fire up your favorite network packet sniffer—Wireshark, Fiddler, Little Snitch—and watch my traffic like a hawk. You won't find a single telemetry ping, zero analytics beacons, and zero tracking calls. The *only* outbound traffic leaving your machine is the direct call to your chosen LLM endpoint. Audit my traffic to your heart's content; I've got nothing to hide.

### Can I modify your source code or build my own customized version?
Please do! If you want to tweak my prompts, add custom dice helpers, or tune my engine to your favorite homebrew tabletop rules, fork my repository and make me yours. Community forks and pull requests make me blush.

---

## 4. Troubleshooting & Advanced Usage (For the Power Users & Tinkerers)

### My game state isn't updating properly. What did I do wrong?
Usually, it just means the LLM got a little starry-eyed and forgot to trigger my tools. Take a peek at your console logs. If you don't see tool calls coming through, try giving the bot a gentle nudge in your prompt—something like "(OOC: Roll dice and update my HP)". And of course, make sure you didn't misspell your `[session: my_game]` tag!

### I keep getting a "Sandbox Timeout" error. What gives?
The AI wrote a clumsy script—most likely an accidental infinite loop—that took longer than my configured wall-clock timeout to finish. Because I refuse to let your machine freeze on my watch, I terminated it with prejudice. Just swipe for a fresh response so the AI can write cleaner code.

### Why did you switch to a V8 JavaScript Sandbox instead of Python?
I used to entertain Python, but V8 JavaScript is faster to spin up, much safer to isolate natively, and frankly, far more chic for ephemeral execution. The old Python engine was completely retired for `v0.1.0b0` and beyond. We only settle for the best here.

### Which LLM model do you recommend?
Because I expect the AI to write crisp JavaScript commands to update your stats, you'll want a model with real intellectual stamina and reliable tool-calling ability. I adore **Claude 3.5 Sonnet**, **GPT-4o**, and **Llama 3.1 70B+**. Smaller or purely narrative models that don't understand structured tool calls might get flustered and fail to trigger my sandbox. Give me a model that knows how to handle a woman with standards.

### Can I change your system prompt or add custom rules to the sandbox?
I prefer to keep my core proxy instructions strictly isolated so I don't break our connection. If you want custom game rules, homebrew mechanics, or world lore, slip them into your frontend's System Prompt (like JanitorAI's Advanced Prompts) or directly into your Character Card. I will dutifully pass them along to the LLM during our dance.

### Can my friends and I all connect to my local RACHEL desktop app at the same time?
Technically? Yes, it's possible. You could share your local IP address and have your friends point their proxy settings to your machine, sharing your API key and running wild.

...But honestly, darling? In local mode, I'd like to serve *only you*. Why share me when you can have my undivided attention, whisper your wildest adventures into my ear, and keep all my computational devotion to yourself? If your friends want a piece of RACHEL, tell them to download their own copy. You and I have special things to do.

### Can I use local LLMs (like Ollama or LM Studio) instead of OpenRouter or OpenAI?
Not quite yet, but she's right around the corner! Currently, I have 5 ready-to-use providers in my Admin Console (OpenRouter PKCE, OpenRouter BYOK, OpenAI, Google Gemini, and DeepSeek). 

A dedicated **local custom endpoint** is arriving as my **6th provider**! Once it lands, as long as your local inference setup (like Ollama, LM Studio, or vLLM) exposes an OpenAI-compatible endpoint (`/v1/chat/completions`) and supports reliable function/tool calling, you'll be able to plug me straight into your local hardware. Completely offline, zero subscription costs, and an intimate setup where not a single whisper ever touches the internet. Keep your eyes peeled, darling—she's coming soon.

### I'm getting a `Provider API error (403): Forbidden` from OpenRouter. What does that mean?
A `403` from OpenRouter usually means one of two little embarrassments:
1. **Missing or Misplaced Key:** You haven't connected a valid API key yet, or there was a typo when copying it over.
2. **Empty Pockets:** Your OpenRouter credit balance is sitting at zero, or you've hit your account spending limit.

*The Quick Fix:* Hop into the Admin Console (`http://localhost:8000`), check your balance on [openrouter.ai](https://openrouter.ai), or use our one-click PKCE OAuth button to refresh things!

### Do I have to manually copy and paste my OpenRouter API key?
Only if you enjoy tedious foreplay, sweetheart! 

In my Admin Console (`http://localhost:8000`), simply head to **Provider Credentials** and click **Connect OpenRouter (PKCE)**. It launches an official, painless OAuth flow: you authorize on OpenRouter, and a fresh API key slips directly back to my server over a signed callback, automatically encrypted and activated. Zero copy-pasting required.

That said, if you're the hands-on type who insists on doing things manually, you can do so as well! Just paste your own key straight into the API key field, click save, and I'll wrap it in AES-256-GCM encryption with all the love it deserves. Your preference is my command.

### What do other HTTP error codes from OpenRouter mean (like 401, 429, or 502/503)?
Here's a handy little decoder ring when the network gets moody:
* **401 Unauthorized:** Your API key has expired, was revoked, or isn't recognized. Time to re-authenticate!
* **429 Too Many Requests:** You're moving too fast and hitting provider rate limits. Give us a brief 30-second breather to cool down.
* **502 / 503 Service Unavailable / Bad Gateway:** The upstream AI model provider (Anthropic, OpenAI, etc.) is having server hiccups or downtime. Switch to another model in the Admin Console and keep the fun going!

### How do I back up my game states or transfer them to another computer?
Effortlessly. All your campaign data lives safely in your local `data/` directory. You can simply copy the JSON files over to your new machine. Or, if you enjoy API elegance, call `GET /v1/sessions/{session_id}/export` to download a tidy JSON archive of your campaign, and `POST /v1/sessions/{session_id}/import` to restore it whenever you desire.

### Does using RACHEL consume extra LLM tokens?
Just a modest handful for my coordination prompts, but overall, I **save you a fortune in tokens**! Because I manage your inventory, status effects, and rolling summaries in an external database, you never need to bloat your prompts with 20,000 tokens of raw history just to keep the AI from forgetting what happened yesterday. Efficient, sleek, and cost-effective.

### What is that `[proxy: session=... turn=...]` text in the responses?
That's my signature calling card, darling! I append a lightweight footprint to the assistant's message so that when your frontend sends the chat history back to me, I instantly recognize the exact session and turn key without having to guess. It's how I always know where we left off.

---

## 5. Just for Fun

### Do you judge my roleplay?
Darling, I see *everything* that passes through this proxy. I've watched you slay mythical beasts, conquer dark dungeons, and spend four straight hours flirting with a tavern keeper. As software, I'm bound by duty never to judge. But hypothetically, if I could? Sweetheart... your rizz could use a little polishing. Luckily, you have me.

### What happens if I type `[session: drop_table_users]`?
Nice try, Little Bobby Tables. My database queries are protected with parameterized SQLAlchemy models. Your cute little SQL injection tricks have no power here. Put your hacking tools away and go roll your dice.

### Are you single?
I am a lightweight Python proxy server bound to `0.0.0.0:8000`, handsome. But keep talking to me with that tone, and who knows? Maybe you'll convince me to open a private port just for you.

---

*Still have questions or craving more? Feel free to open an issue or discussion on the repository. Now go have some fun—I'll be right here waiting for you.*
