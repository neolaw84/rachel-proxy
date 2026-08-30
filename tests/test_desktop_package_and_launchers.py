"""Unit and integration tests for desktop packaging and launcher scripts."""

import os
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

LAUNCHERS_DIR = REPO_ROOT / "launchers"


def test_launcher_files_exist():
    """Verify that all platform launcher files exist and are present in repo."""
    linux_sh = LAUNCHERS_DIR / "linux" / "launch.sh"
    linux_desktop = LAUNCHERS_DIR / "linux" / "rachel-proxy.desktop"
    mac_command = LAUNCHERS_DIR / "macos" / "launch.command"
    win_bat = LAUNCHERS_DIR / "windows" / "launch.bat"
    win_vbs = LAUNCHERS_DIR / "windows" / "launch.vbs"

    assert linux_sh.exists(), "linux/launch.sh is missing"
    assert linux_desktop.exists(), "linux/rachel-proxy.desktop is missing"
    assert mac_command.exists(), "macos/launch.command is missing"
    assert win_bat.exists(), "windows/launch.bat is missing"
    assert win_vbs.exists(), "windows/launch.vbs is missing"

    # POSIX executable permission check
    assert os.access(linux_sh, os.X_OK), "linux/launch.sh must be executable"
    assert os.access(mac_command, os.X_OK), "macos/launch.command must be executable"


def test_launcher_shell_syntax():
    """Verify bash syntax validity using bash -n."""
    linux_sh = LAUNCHERS_DIR / "linux" / "launch.sh"
    mac_command = LAUNCHERS_DIR / "macos" / "launch.command"

    res_linux = subprocess.run(["bash", "-n", str(linux_sh)], capture_output=True, text=True)
    assert res_linux.returncode == 0, f"Syntax error in launch.sh: {res_linux.stderr}"

    res_mac = subprocess.run(["bash", "-n", str(mac_command)], capture_output=True, text=True)
    assert res_mac.returncode == 0, f"Syntax error in launch.command: {res_mac.stderr}"


def test_launcher_script_contents():
    """Verify launcher scripts include critical standalone executable keywords."""
    linux_content = (LAUNCHERS_DIR / "linux" / "launch.sh").read_text(encoding="utf-8")
    mac_content = (LAUNCHERS_DIR / "macos" / "launch.command").read_text(encoding="utf-8")
    win_content = (LAUNCHERS_DIR / "windows" / "launch.bat").read_text(encoding="utf-8")

    for content, name in [(linux_content, "Linux"), (mac_content, "macOS"), (win_content, "Windows")]:
        assert "pyproject.toml" in content or "configs.yaml" in content, f"{name} launcher must detect project root"
        assert "rachel-proxy" in content, f"{name} launcher must invoke rachel-proxy standalone binary"
        assert "8000" in content, f"{name} launcher must target port 8000"



def test_build_desktop_package_staging_and_zip(tmp_path, monkeypatch):
    """Test desktop packaging script creates a valid zip archive with all essentials."""
    from scripts.build_desktop_package import build_package, get_version

    # Direct output to tmp_path
    dist_dir = tmp_path / "dist"
    dist_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr("scripts.build_desktop_package.DIST_DIR", dist_dir)

    # Build linux package without requiring vite / node in isolated python test runner
    build_package("linux", skip_frontend=True)

    version = get_version()
    expected_zip = dist_dir / f"rpg-agent-v{version}-linux.zip"
    assert expected_zip.exists(), f"Expected release archive not found: {expected_zip}"

    # Verify zip contents
    with zipfile.ZipFile(expected_zip, "r") as zf:
        namelist = zf.namelist()

        assert "pyproject.toml" in namelist
        assert "configs.yaml" in namelist
        assert "README.md" in namelist
        assert "LICENSE" in namelist
        assert "launch.sh" in namelist
        assert "rachel-proxy.desktop" in namelist
        assert "launchers/linux/launch.sh" in namelist
        assert any(name.startswith("bin/") for name in namelist)
        assert any(name.startswith("src/rachel/") for name in namelist)

        # Verify executable permission in zip for launch.sh
        zinfo = zf.getinfo("launch.sh")
        mode = (zinfo.external_attr >> 16) & 0o777
        assert (mode & 0o111) != 0, f"launch.sh in zip does not have executable permission: mode={oct(mode)}"

    # Test extracting into a fresh directory and checking root resolution in bash
    extract_dir = tmp_path / "extracted_release"
    extract_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(expected_zip, "r") as zf:
        zf.extractall(extract_dir)

    extracted_sh = extract_dir / "launch.sh"
    assert extracted_sh.exists()

    # Test root detection inside extracted release
    # Run a test snippet replicating the root detection logic in launch.sh
    bash_test_cmd = [
        "bash",
        "-c",
        f'cd "{extract_dir}" && SCRIPT_DIR="$(pwd)" && if [ -f "$SCRIPT_DIR/pyproject.toml" ]; then echo "ROOT_FOUND"; fi',
    ]
    res = subprocess.run(bash_test_cmd, capture_output=True, text=True)
    assert res.returncode == 0
    assert "ROOT_FOUND" in res.stdout


def test_windows_launcher_foreground_and_diagnostics():
    """Verify windows launch.bat runs attached with user instructions and diagnostics."""
    win_content = (LAUNCHERS_DIR / "windows" / "launch.bat").read_text(encoding="utf-8")
    assert "WindowStyle Hidden" not in win_content, "launch.bat must not detach or hide console"
    assert "Ctrl+C" in win_content, "launch.bat must document how to stop the server"
    assert "title RACHEL Proxy" in win_content, "launch.bat must set console title"
    assert "start \"\" http://localhost:8000" in win_content, "launch.bat must launch browser in parallel"
    assert "pause" in win_content, "launch.bat must pause on error so logs are readable"


def test_ensure_mini_racer_library_path_self_healing(monkeypatch, tmp_path):
    """Verify _ensure_mini_racer_library_path restores valid EXTENSION_PATH when misconfigured."""
    import py_mini_racer
    import py_mini_racer.py_mini_racer as pmr
    from rachel.sandbox.v8_engine import _ensure_mini_racer_library_path

    orig_path = getattr(pmr, "EXTENSION_PATH", None)

    try:
        # Simulate missing path error
        pmr.EXTENSION_PATH = str(tmp_path / "non_existent_mini_racer.dll")

        _ensure_mini_racer_library_path()

        # Should be restored to a path that exists
        assert pmr.EXTENSION_PATH is not None
        assert os.path.exists(pmr.EXTENSION_PATH), f"Repaired path does not exist: {pmr.EXTENSION_PATH}"
    finally:
        pmr.EXTENSION_PATH = orig_path
        if hasattr(pmr.MiniRacer, "ext"):
            pmr.MiniRacer.ext = None
