"""OpenRouter Chat Completion Proxy — backward-compatible entrypoint module.

Re-exports ``app`` from ``rachel.entrypoints.desktop`` and provides CLI ``main()``.
"""

from __future__ import annotations

import os

from rachel.entrypoints.desktop import app, create_desktop_app


def main():
    import argparse
    import uvicorn

    default_port = int(os.environ.get("PORT", 8000))

    parser = argparse.ArgumentParser(description="RACHEL (Rpg Agent CHat Evaluation Loop) Proxy")
    parser.add_argument("--host", default="0.0.0.0", help="Binding host")
    parser.add_argument("--port", type=int, default=default_port, help="Binding port")
    parser.add_argument("--reload", action="store_true", help="Enable uvicorn reload")

    args = parser.parse_args()

    uvicorn.run("rachel.entrypoints.desktop:app", host=args.host, port=args.port, reload=args.reload)


if __name__ == "__main__":
    main()
