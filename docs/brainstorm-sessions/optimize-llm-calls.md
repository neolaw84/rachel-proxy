# Brainstorming Session on Optimizing LLM Calls

## 1. Plan/Summary/Clean-up Nodes

Currently, I note that plan node expects a json response from LLM. However, response from LLM is not pure json. 

We need to figure out a fool-proof way to make it always return pure JSON.

There are two ways to do it (we will do both):

1. Tweak the prompt
2. Either use a structured output or force a tool call (to receive the plan as proper json string)

Brainstorm how to make sure it works across LLM providers.

After that, we need to repeat the same for summary and clean-up (not literal copy/paste; spritual adaptation accordingly). 

## 2. Session ID Mechanics for All Providers

Tell me what the session id mechanics is for all providers (in scope). Are they properly implemented for each?

If not, try to implement the missing parts.

## 3. Removing Direct RW Access to `plan`

The main LLM call has a read-write access to `plan` defeating the whole purpose of separate plan node. 

Brainstorm a few options (while still providing option to update status of the plan element). 

## 4. Streamlining System and User Messages

Currently the latest Rachel's instructions are appended as the last user message. It is because Rachel's instructions include changing (dynamic) elements such as `plan`, `summary`, `state` and `hidden-state` etc. 

My idea is to streamline the prompt of Rachel's instructions so the static parts are appended to the system message (the Outgoing Message at index 0) and the dynamic parts (and the surrounding prompts of them) are appended after the last user message (the last user message in the Outgoing Message). 

Then, double check if this approach works with most (if not all) providers' prefix cache. 