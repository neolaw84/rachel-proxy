#!/usr/bin/env python3
"""Build script for creating standalone single-tenant desktop release packages."""

import argparse
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent.resolve()
DIST_DIR = REPO_ROOT / "dist"
STATIC_DIR = REPO_ROOT / "src" / "rachel" / "static"


def get_version():
    """Extract version from pyproject.toml."""
    pyproject = REPO_ROOT / "pyproject.toml"
    if pyproject.exists():
        for line in pyproject.read_text(encoding="utf-8").splitlines():
            if line.strip().startswith("version ="):
                return line.split("=")[1].strip().strip('"').strip("'")
    return "0.2.0"


def build_package(platform_name):
    version = get_version()
    package_name = f"rpg-agent-v{version}-{platform_name}"
    target_zip = DIST_DIR / f"{package_name}.zip"

    print(f"==================================================")
    print(f"Building desktop package: {package_name}")
    print(f"==================================================")

    # 1. Compile frontend local target
    print("Step 1: Compiling local frontend bundle...")
    cmd_build = [sys.executable, str(REPO_ROOT / "scripts" / "build_frontend.py"), "--target", "local"]
    res = subprocess.run(cmd_build, cwd=REPO_ROOT)
    if res.returncode != 0:
        print("Error: Frontend build failed.", file=sys.stderr)
        sys.exit(res.returncode)

    # 2. Assemble release folder
    build_staging = DIST_DIR / "staging" / package_name
    if build_staging.exists():
        shutil.rmtree(build_staging)
    build_staging.mkdir(parents=True, exist_ok=True)

    print("Step 2: Staging package files...")
    # Copy essential files
    shutil.copy(REPO_ROOT / "pyproject.toml", build_staging / "pyproject.toml")
    shutil.copy(REPO_ROOT / "configs.yaml", build_staging / "configs.yaml")
    shutil.copy(REPO_ROOT / "README.md", build_staging / "README.md")
    shutil.copy(REPO_ROOT / "LICENSE", build_staging / "LICENSE")

    # Copy src/ (including compiled static assets)
    shutil.copytree(REPO_ROOT / "src", build_staging / "src")

    # Copy platform specific launcher
    launcher_src = REPO_ROOT / "launchers" / platform_name
    if launcher_src.exists():
        shutil.copytree(launcher_src, build_staging / "launchers" / platform_name)
        if platform_name == "windows" and (launcher_src / "launch.bat").exists():
            shutil.copy(launcher_src / "launch.bat", build_staging / "launch.bat")
            if (launcher_src / "launch.vbs").exists():
                shutil.copy(launcher_src / "launch.vbs", build_staging / "launch.vbs")
        elif platform_name == "macos" and (launcher_src / "launch.command").exists():
            shutil.copy(launcher_src / "launch.command", build_staging / "launch.command")
            os.chmod(build_staging / "launch.command", 0o755)
        elif platform_name == "linux" and (launcher_src / "launch.sh").exists():
            shutil.copy(launcher_src / "launch.sh", build_staging / "launch.sh")
            os.chmod(build_staging / "launch.sh", 0o755)

    # 3. Create zip archive
    print(f"Step 3: Creating zip archive at {target_zip}...")
    with zipfile.ZipFile(target_zip, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(build_staging):
            for file in files:
                abs_path = Path(root) / file
                rel_path = abs_path.relative_to(build_staging)
                zinfo = zipfile.ZipInfo.from_file(abs_path, arcname=str(rel_path))
                st = abs_path.stat()
                # Ensure executable bit (0o755) is preserved for shell scripts
                if file.endswith((".sh", ".command")):
                    zinfo.external_attr = (0o755 | 0o100000) << 16
                else:
                    zinfo.external_attr = (st.st_mode & 0xFFFF) << 16
                with open(abs_path, "rb") as f:
                    zf.writestr(zinfo, f.read())

    # Cleanup staging
    shutil.rmtree(build_staging.parent)
    print(f"Successfully generated {target_zip} ({target_zip.stat().st_size} bytes)")


def main():
    parser = argparse.ArgumentParser(description="Build desktop release package.")
    parser.add_argument(
        "--platform",
        choices=["win", "mac", "linux", "all"],
        default="linux",
        help="Target platform (win, mac, linux, or all)",
    )
    args = parser.parse_args()

    platform_map = {"win": "windows", "mac": "macos", "linux": "linux"}

    if args.platform == "all":
        for p in ["windows", "macos", "linux"]:
            build_package(p)
    else:
        build_package(platform_map[args.platform])


if __name__ == "__main__":
    main()
