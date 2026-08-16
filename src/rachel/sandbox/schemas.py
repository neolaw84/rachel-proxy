"""Tool Schemas for OpenRouter direct function calling."""

from typing import Any

END_TURN_TOOL: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "end_turn",
        "description": "Signal that you have completed narrating your story response for the current turn to pass agency back to the user.",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
}

SUBMIT_PLAN_TOOL: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "submit_plan",
        "description": "Submit the updated checklist of story goals and NPC plans as a structured array.",
        "parameters": {
            "type": "object",
            "properties": {
                "items": {
                    "type": "array",
                    "description": "List of plan items",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {"type": ["integer", "string"], "description": "Unique identifier"},
                            "description": {"type": "string", "description": "Goal description"},
                            "status": {
                                "type": "string",
                                "enum": ["to-do", "in-progress", "completed", "failed"],
                                "description": "Current status",
                            },
                            "remark": {"type": "string", "description": "Optional notes or remarks"},
                        },
                        "required": ["id", "description", "status"],
                    },
                }
            },
            "required": ["items"],
        },
    },
}

SUBMIT_SUMMARY_TOOL: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "submit_summary",
        "description": "Submit the narrative summary block describing developments.",
        "parameters": {
            "type": "object",
            "properties": {
                "summary": {
                    "type": "string",
                    "description": "Concise narrative summary block.",
                }
            },
            "required": ["summary"],
        },
    },
}

SUBMIT_CLEANUP_TOOL: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "submit_cleanup",
        "description": "Submit code snippet to clean up state and hidden_state variables.",
        "parameters": {
            "type": "object",
            "properties": {
                "code": {
                    "type": "string",
                    "description": "Code snippet to execute in sandbox.",
                }
            },
            "required": ["code"],
        },
    },
}

def get_execute_code_sandbox_schema(engine_name: str = "v8") -> dict[str, Any]:
    """Return the execute_code_sandbox tool schema based on engine name."""
    if engine_name == "v8":
        sandbox_desc = (
            "Execute a JavaScript code snippet to read or modify the current RPG state. "
            "The global variable `state` (an object) is available for reading and updating. "
            "Use console.log(...) to print outputs. Returns the log output."
        )
        code_desc = "The JavaScript code snippet to run."
    else:
        sandbox_desc = (
            "Execute a Python code snippet to read or modify the current RPG state. "
            "The variable `state` (a dict) is available for reading and updating. "
            "Available libraries: math, random, json, time, datetime, collections, itertools, functools, re, string. "
            "Nothing outside of these libraries is available. Returns the stdout of the code execution."
        )
        code_desc = "The Python code snippet to run."

    return {
        "type": "function",
        "function": {
            "name": "execute_code_sandbox",
            "description": sandbox_desc,
            "parameters": {
                "type": "object",
                "properties": {
                    "code": {
                        "type": "string",
                        "description": code_desc,
                    }
                },
                "required": ["code"],
            },
        },
    }

def get_all_tools_schema(engine_name: str = "v8") -> list[dict[str, Any]]:
    """Return the unified static array of all 5 tool schemas for prompt prefix alignment."""
    return [
        get_execute_code_sandbox_schema(engine_name),
        END_TURN_TOOL,
        SUBMIT_PLAN_TOOL,
        SUBMIT_SUMMARY_TOOL,
        SUBMIT_CLEANUP_TOOL,
    ]

def get_tools_schema(engine_name: str = "v8") -> list[dict[str, Any]]:
    """Return the master tool schema array (alias for get_all_tools_schema)."""
    return get_all_tools_schema(engine_name)

TOOLS_SCHEMA = get_tools_schema("v8")


