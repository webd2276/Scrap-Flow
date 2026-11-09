"""Cross-platform runner entry-point guards."""

from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"
COMMANDS = (
    "fix-db-password",
    "logs",
    "reset",
    "seed",
    "status",
    "stop",
)


def _read(name: str) -> str:
    return (SCRIPTS / name).read_text(encoding="utf-8")


@pytest.mark.parametrize("name", ["run.sh", "run-macos.sh"])
def test_bash_entry_points_are_self_contained(name: str) -> None:
    text = _read(name)
    assert text.startswith("#!/usr/bin/env bash\n")
    assert "set -euo pipefail" in text


def test_shared_bash_runner_exposes_every_command() -> None:
    text = _read("run.sh")
    for command in COMMANDS:
        assert command in text
    assert "adobe/s3mock" in text
    assert "pull_minio_image" in text


def test_macos_runner_delegates_to_the_shared_runner() -> None:
    text = _read("run-macos.sh")
    assert 'exec bash "$SELF_DIR/run.sh" "$@"' in text
    # The wrapper must not fork its own copy of the stack logic.
    assert "docker compose" not in text


def test_windows_runner_has_no_posix_dependency() -> None:
    text = _read("run.ps1")
    assert "#requires -Version 5.1" in text
    for command in COMMANDS:
        assert command in text
    assert "adobe/s3mock" in text
    assert "PowerShell" in text
    assert "bash" not in text.lower()


def test_windows_cmd_launcher_uses_powershell_runner() -> None:
    text = _read("run.cmd")
    assert "run.ps1" in text
    assert "-ExecutionPolicy Bypass" in text
