"""OpenRouter Chat Completion Proxy — backward-compatible entrypoint module.

Re-exports ``app`` from ``rachel.entrypoints.desktop`` and provides CLI ``main()``.
"""

from __future__ import annotations

import multiprocessing
import os

from rachel.entrypoints.desktop import app, create_desktop_app


def main():
    # MUST be the first statement in main(): In PyInstaller frozen bundles, child worker
    # processes spawned by the V8 sandbox (via multiprocessing spawn method) invoke the
    # compiled binary with internal flags like `--multiprocessing-fork`. Calling freeze_support()
    # intercepts worker execution, runs the target worker task, and exits immediately.
    # Without this, the child process falls through to argparse and exits with error code 2.
    multiprocessing.freeze_support()

    # Defer CLI and server imports inside main():
    # 1. Keeps spawned sandbox worker processes lightweight by avoiding loading Uvicorn machinery.
    # 2. Avoids CLI side-effects when external ASGI runners import `app` at the top level.
    import argparse
    import uvicorn

    default_port = int(os.environ.get("PORT", 8000))

    parser = argparse.ArgumentParser(description="RACHEL (Rpg Agent CHat Evaluation Loop) Proxy")
    parser.add_argument("--host", default="0.0.0.0", help="Binding host")
    parser.add_argument("--port", type=int, default=default_port, help="Binding port")
    parser.add_argument("--reload", action="store_true", help="Enable uvicorn reload")

    args = parser.parse_args()

    if args.reload:
        uvicorn.run("rachel.entrypoints.desktop:app", host=args.host, port=args.port, reload=True)
    else:
        uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
