#!/usr/bin/env python3
"""Build helper script to compile frontend and populate src/rachel/static."""

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent.resolve()
STATIC_DIR = REPO_ROOT / "src" / "rachel" / "static"


def main():
    parser = argparse.ArgumentParser(description="Build frontend static assets for RACHEL.")
    parser.add_argument(
        "--target",
        choices=["local", "cloud"],
        default="local",
        help="Build target: 'local' (default) or 'cloud'",
    )
    args = parser.parse_args()

    mode_flag = "desktop" if args.target == "local" else "cloud"
    cmd = ["npm", "run", f"build:{args.target}"]
    print(f"Building frontend target '{args.target}' (npm mode '{mode_flag}')...")

    # On Windows, subprocess.run requires shell=True to find and execute batch/cmd scripts like npm
    result = subprocess.run(cmd, cwd=REPO_ROOT, shell=os.name == "nt")
    if result.returncode != 0:
        print(f"Error: Frontend build failed with exit code {result.returncode}", file=sys.stderr)
        sys.exit(result.returncode)

    dist_src = REPO_ROOT / "frontend" / "dist" / args.target
    if not dist_src.exists():
        print(f"Error: Expected dist output directory not found at {dist_src}", file=sys.stderr)
        sys.exit(1)

    print(f"Syncing compiled static files from {dist_src} to {STATIC_DIR}...")
    if STATIC_DIR.exists():
        shutil.rmtree(STATIC_DIR)
    shutil.copytree(dist_src, STATIC_DIR)

    print(f"Successfully populated {STATIC_DIR} with target '{args.target}'!")


if __name__ == "__main__":
    main()
