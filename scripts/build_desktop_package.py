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


def run_pyinstaller(platform_name, output_dir):
    """Compile standalone binary using PyInstaller."""
    print("Step 2: Compiling standalone binary with PyInstaller...")
    proxy_entry = REPO_ROOT / "src" / "rachel" / "proxy.py"
    
    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--onedir",
        "--name",
        "rachel-proxy",
        "--clean",
        "--collect-all",
        "py_mini_racer",
        "--collect-all",
        "uvicorn",
        "--collect-all",
        "langgraph",
        "--collect-all",
        "langchain_openai",
        "--collect-all",
        "cryptography",
        "--collect-all",
        "psycopg2",
        "--add-data",
        f"{STATIC_DIR}{os.pathsep}rachel/static",
    ]

    # Explicitly add py_mini_racer native binaries to bundle root (.) to satisfy legacy and modern MEIPASS lookups
    try:
        import py_mini_racer
        pmr_dir = Path(py_mini_racer.__file__).parent
        for pattern in ("*.dll", "*.so", "*.dylib"):
            for lib_path in pmr_dir.glob(pattern):
                cmd.extend(["--add-binary", f"{lib_path}{os.pathsep}."])
    except Exception as e:
        print(f"Notice: Could not inspect py_mini_racer directory for explicit binary mapping: {e}")

    cmd.extend([
        "--distpath",
        str(output_dir / "bin"),
        str(proxy_entry),
    ])
    
    print(f"Running PyInstaller: {' '.join(cmd)}")
    res = subprocess.run(cmd, cwd=REPO_ROOT)
    if res.returncode != 0:
        print("Warning: PyInstaller compilation failed or exited non-zero.", file=sys.stderr)
        return False

    # Post-build check: Ensure native library symmetry between _internal root and _internal/py_mini_racer
    bin_app_dir = output_dir / "bin" / "rachel-proxy"
    internal_dir = bin_app_dir / "_internal"
    target_dirs = [internal_dir, bin_app_dir] if internal_dir.exists() else [bin_app_dir]

    for base_dir in target_dirs:
        pmr_sub = base_dir / "py_mini_racer"
        for pattern in ("*.dll", "*.so", "*.dylib"):
            # If in package subdir but not in base dir, copy to base dir
            if pmr_sub.exists():
                for f in pmr_sub.glob(pattern):
                    dest = base_dir / f.name
                    if not dest.exists():
                        shutil.copy2(f, dest)
                        print(f"Synced {f.name} to {base_dir}")
            # If in base dir but not in package subdir, copy to package subdir
            for f in base_dir.glob(pattern):
                pmr_sub.mkdir(parents=True, exist_ok=True)
                dest = pmr_sub / f.name
                if not dest.exists():
                    shutil.copy2(f, dest)
                    print(f"Synced {f.name} to {pmr_sub}")

    return True


def build_package(platform_name, skip_frontend=False, skip_pyinstaller=False):
    version = get_version()
    package_name = f"rpg-agent-v{version}-{platform_name}"
    target_zip = DIST_DIR / f"{package_name}.zip"

    print(f"==================================================")
    print(f"Building desktop package: {package_name}")
    print(f"==================================================")

    # 1. Compile frontend local target
    if not skip_frontend:
        print("Step 1: Compiling local frontend bundle...")
        cmd_build = [sys.executable, str(REPO_ROOT / "scripts" / "build_frontend.py"), "--target", "local"]
        res = subprocess.run(cmd_build, cwd=REPO_ROOT)
        if res.returncode != 0:
            print("Error: Frontend build failed.", file=sys.stderr)
            sys.exit(res.returncode)
    else:
        print("Step 1: Skipping frontend compilation (skip_frontend=True)...")

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

    # Copy src/ (including compiled static assets) for fallback / inspectability
    shutil.copytree(REPO_ROOT / "src", build_staging / "src")

    # 3. Build standalone binary if PyInstaller is enabled
    bin_dir = build_staging / "bin" / "rachel-proxy"
    if not skip_pyinstaller:
        try:
            import PyInstaller  # noqa: F401
            has_pyinstaller = True
        except ImportError:
            has_pyinstaller = False

        if has_pyinstaller:
            run_pyinstaller(platform_name, build_staging)
        else:
            print("PyInstaller not installed. Creating placeholder bin structure...")
            bin_dir.mkdir(parents=True, exist_ok=True)
            dummy_bin = bin_dir / ("rachel-proxy.exe" if platform_name == "windows" else "rachel-proxy")
            dummy_bin.write_text("#!/bin/sh\necho 'RACHEL Desktop Bundle'\n", encoding="utf-8")
            dummy_bin.chmod(0o755)
    else:
        print("Skipping PyInstaller compilation (skip_pyinstaller=True). Creating placeholder bin structure...")
        bin_dir.mkdir(parents=True, exist_ok=True)
        dummy_bin = bin_dir / ("rachel-proxy.exe" if platform_name == "windows" else "rachel-proxy")
        dummy_bin.write_text("#!/bin/sh\necho 'RACHEL Desktop Bundle'\n", encoding="utf-8")
        dummy_bin.chmod(0o755)

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
            if (launcher_src / "rachel-proxy.desktop").exists():
                shutil.copy(launcher_src / "rachel-proxy.desktop", build_staging / "rachel-proxy.desktop")

    # 4. Create zip archive
    print(f"Step 4: Creating zip archive at {target_zip}...")
    DIST_DIR.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(target_zip, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(build_staging):
            for file in files:
                abs_path = Path(root) / file
                rel_path = abs_path.relative_to(build_staging)
                zinfo = zipfile.ZipInfo.from_file(abs_path, arcname=str(rel_path))
                st = abs_path.stat()
                # Ensure executable bit (0o755) is preserved for shell scripts and binaries
                if file.endswith((".sh", ".command", ".desktop")) or "bin" in rel_path.parts:
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
    parser.add_argument(
        "--skip-frontend",
        action="store_true",
        help="Skip rebuilding frontend assets before packaging.",
    )
    parser.add_argument(
        "--skip-pyinstaller",
        action="store_true",
        help="Skip PyInstaller standalone compilation.",
    )
    args = parser.parse_args()

    platform_map = {"win": "windows", "mac": "macos", "linux": "linux"}

    if args.platform == "all":
        for p in ["windows", "macos", "linux"]:
            build_package(p, skip_frontend=args.skip_frontend, skip_pyinstaller=args.skip_pyinstaller)
    else:
        build_package(platform_map[args.platform], skip_frontend=args.skip_frontend, skip_pyinstaller=args.skip_pyinstaller)


if __name__ == "__main__":
    main()

