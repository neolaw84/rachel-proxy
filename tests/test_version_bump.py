import os
import subprocess
import sys
from pathlib import Path

import pytest

# Add scripts directory to path for direct import
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from bump_version import bump_version, resolve_bump_type, update_pyproject_version


def test_bump_version_major():
    assert bump_version("0.1.1b1", "major") == "1.0.0"
    assert bump_version("1.2.3", "major") == "2.0.0"


def test_bump_version_minor():
    assert bump_version("0.1.1b1", "minor") == "0.2.0"
    assert bump_version("1.2.3", "minor") == "1.3.0"


def test_bump_version_micro_and_patch():
    assert bump_version("0.1.1b1", "micro") == "0.1.2"
    assert bump_version("0.1.1b1", "patch") == "0.1.2"
    assert bump_version("1.2.3", "micro") == "1.2.4"


def test_bump_version_release():
    assert bump_version("0.1.1b1", "release") == "0.1.1"
    assert bump_version("1.2.3rc2", "release") == "1.2.3"
    assert bump_version("1.2.3", "release") == "1.2.3"


def test_bump_version_labels():
    # Alpha
    assert bump_version("0.1.1", "a") == "0.1.1a1"
    assert bump_version("0.1.1a1", "alpha") == "0.1.1a2"
    # Beta
    assert bump_version("0.1.1", "b") == "0.1.1b1"
    assert bump_version("0.1.1b1", "beta") == "0.1.1b2"
    assert bump_version("0.1.1b2", "b") == "0.1.1b3"
    # Release candidate
    assert bump_version("0.1.1", "rc") == "0.1.1rc1"
    assert bump_version("0.1.1rc1", "rc") == "0.1.1rc2"


def test_bump_version_after_label_number_and_default():
    assert bump_version("0.1.1b1", "num") == "0.1.1b2"
    assert bump_version("0.1.1b1", "after-label-number") == "0.1.1b2"
    assert bump_version("0.1.1b1", "build") == "0.1.1b2"
    assert bump_version("0.1.1b1", "default") == "0.1.1b2"
    assert bump_version("0.1.1", "default") == "0.1.2"


def test_bump_version_skip():
    assert bump_version("0.1.1b1", "skip") == "0.1.1b1"
    assert bump_version("0.1.1b1", "none") == "0.1.1b1"


def test_bump_version_invalid():
    with pytest.raises(ValueError):
        bump_version("0.1.1b1", "unknown_type")
    with pytest.raises(ValueError):
        bump_version("invalid_ver", "minor")


def test_resolve_bump_type(tmp_path, monkeypatch):
    # 1. Direct CLI type overrides everything
    assert resolve_bump_type(cli_type="major") == "major"

    # 2. Env variable
    monkeypatch.setenv("BUMP", "minor")
    assert resolve_bump_type() == "minor"
    monkeypatch.delenv("BUMP", raising=False)

    # 3. Commit message file with tag
    msg_file = tmp_path / "COMMIT_EDITMSG"
    msg_file.write_text("fix: resolve state sync bug [bump:micro]", encoding="utf-8")
    assert resolve_bump_type(str(msg_file)) == "micro"

    msg_file.write_text("feat: new database layer [bump:minor]", encoding="utf-8")
    assert resolve_bump_type(str(msg_file)) == "minor"

    msg_file.write_text("wip: update docs [bump:skip]", encoding="utf-8")
    assert resolve_bump_type(str(msg_file)) == "skip"

    # 4. Default fallback when no tag in message
    msg_file.write_text("regular commit message", encoding="utf-8")
    assert resolve_bump_type(str(msg_file)) == "default"


def test_update_pyproject_version(tmp_path):
    pyproj = tmp_path / "pyproject.toml"
    pyproj.write_text(
        '[build-system]\nrequires = ["hatchling"]\n\n[project]\nname = "rachel-proxy"\nversion = "0.1.1b1"\n',
        encoding="utf-8",
    )

    res = update_pyproject_version(pyproj, "minor")
    assert res == ("0.1.1b1", "0.2.0")
    assert 'version = "0.2.0"' in pyproj.read_text(encoding="utf-8")

    # Skip should not modify
    res_skip = update_pyproject_version(pyproj, "skip")
    assert res_skip is None
    assert 'version = "0.2.0"' in pyproj.read_text(encoding="utf-8")


def test_bump_script_cli_execution(tmp_path):
    pyproj = tmp_path / "pyproject.toml"
    pyproj.write_text(
        '[project]\nname = "test-pkg"\nversion = "1.0.0"\n',
        encoding="utf-8",
    )
    script_path = Path(__file__).resolve().parent.parent / "scripts" / "bump_version.py"

    proc = subprocess.run(
        [sys.executable, str(script_path), "--type", "patch", "--file", str(pyproj)],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0
    assert "1.0.0 -> 1.0.1" in proc.stdout
    assert 'version = "1.0.1"' in pyproj.read_text(encoding="utf-8")
