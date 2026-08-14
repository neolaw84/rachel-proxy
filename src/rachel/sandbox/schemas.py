"""Tool Schemas for OpenRouter direct function calling."""

from typing import Any

def get_tools_schema(
    engine_name: str = "v8",
    include_plan: bool = False,
    include_summary: bool = False,
) -> list[dict[str, Any]]:
    """Return the tools schema for OpenRouter completions based on engine name."""
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

    return [
        {
            "type": "function",
            "function": {
                "name": "execute_code_sandbox",
                "description": sandbox_desc,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "code": {
                            "type": "string",
                            "description": code_desc
                        }
                    },
                    "required": ["code"]
                }
            }
        }
    ]


TOOLS_SCHEMA = get_tools_schema("python")

