"""Standalone Echo / Payload Inspector Server.

Captures and prints all incoming HTTP requests (headers, query params, raw/JSON payloads)
on any path or HTTP method, with permissive CORS and mock chat completion responses.

Usage:
    python src/echo_server.py
    # or
    PYTHONPATH=src uvicorn echo_server:app --reload --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from typing import Any

import uvicorn
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("echo_server")

app = FastAPI(
    title="RACHEL Payload Inspector",
    description="Inspects incoming requests from any client on any path.",
)

# Open CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


async def _stream_mock_response(model: str = "echo"):
    """Yield mock SSE stream response for streaming chat completion requests."""
    chunks = [
        "Echo server connected. ",
        "Received payload successfully!",
    ]
    for chunk in chunks:
        payload = {
            "id": f"echo-{int(time.time())}",
            "object": "chat.completion.chunk",
            "created": int(time.time()),
            "model": model,
            "choices": [
                {
                    "index": 0,
                    "delta": {"content": chunk},
                    "finish_reason": None,
                }
            ],
        }
        yield f"data: {json.dumps(payload)}\n\n".encode("utf-8")
        time.sleep(0.05)

    final_payload = {
        "id": f"echo-{int(time.time())}",
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "model": model,
        "choices": [
            {
                "index": 0,
                "delta": {},
                "finish_reason": "stop",
            }
        ],
    }
    yield f"data: {json.dumps(final_payload)}\n\n".encode("utf-8")
    yield b"data: [DONE]\n\n"


@app.api_route(
    "/{full_path:path}",
    methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"],
)
async def catch_all(request: Request, full_path: str) -> Any:
    raw_body = await request.body()

    # Try parsing body as JSON
    parsed_json: Any = None
    if raw_body:
        try:
            parsed_json = json.loads(raw_body.decode("utf-8"))
        except Exception:
            try:
                parsed_json = raw_body.decode("utf-8")
            except Exception:
                parsed_json = f"<binary body: {len(raw_body)} bytes>"

    # Format inspection banner
    sep = "=" * 70
    headers_formatted = json.dumps(dict(request.headers), indent=2)
    
    body_formatted: str
    if isinstance(parsed_json, (dict, list)):
        body_formatted = json.dumps(parsed_json, indent=2, ensure_ascii=False)
    else:
        body_formatted = str(parsed_json) if parsed_json is not None else "<empty body>"

    client_host = request.client.host if request.client else "unknown"
    client_port = request.client.port if request.client else "unknown"

    print(
        f"\n{sep}\n"
        f"INCOMING REQUEST:\n"
        f"  Method:       {request.method}\n"
        f"  URL:          {request.url}\n"
        f"  Path:         /{full_path}\n"
        f"  Query Params: {dict(request.query_params)}\n"
        f"  Client:       {client_host}:{client_port}\n"
        f"\n--- HEADERS ---\n"
        f"{headers_formatted}\n"
        f"\n--- PAYLOAD / BODY ---\n"
        f"{body_formatted}\n"
        f"{sep}\n",
        flush=True,
    )

    # If stream request is requested, return mock streaming response
    if isinstance(parsed_json, dict) and parsed_json.get("stream") is True:
        model = parsed_json.get("model", "echo-model")
        return StreamingResponse(_stream_mock_response(model=model), media_type="text/event-stream")

    # Standard mock OpenAI response
    mock_resp = {
        "id": f"echo-{int(time.time())}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": parsed_json.get("model", "echo-model") if isinstance(parsed_json, dict) else "echo-model",
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": "Echo server received payload successfully!",
                },
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": 10,
            "completion_tokens": 10,
            "total_tokens": 20,
        },
    }
    return JSONResponse(mock_resp)


def main():
    parser = argparse.ArgumentParser(description="Echo / Payload Inspector Server")
    parser.add_argument("--host", default="0.0.0.0", help="Binding host (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=8000, help="Binding port (default: 8000)")
    parser.add_argument("--reload", action="store_true", help="Enable auto-reload")
    args = parser.parse_args()

    print(
        "\n" + "=" * 60 + "\n"
        f"  Echo / Payload Inspector running at http://{args.host}:{args.port}\n"
        f"  Listening on all routes (e.g. http://localhost:{args.port}/v1/chat/completions)\n"
        + "=" * 60 + "\n",
        flush=True,
    )

    if args.reload:
        uvicorn.run("echo_server:app", host=args.host, port=args.port, reload=True)
    else:
        uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
