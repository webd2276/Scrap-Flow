#!/usr/bin/env python3
"""Create a local .env with strong random secrets. Refuses to overwrite."""

from __future__ import annotations

import secrets
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / ".env"
EXAMPLE = ROOT / ".env.example"


def main() -> int:
    if TARGET.exists():
        print(f"{TARGET} already exists; refusing to overwrite")
        return 1

    db_password = secrets.token_urlsafe(24)
    replacements = {
        "CHANGE_ME_32_PLUS_RANDOM_CHARACTERS": lambda: secrets.token_urlsafe(48),
        "CHANGE_ME": lambda: db_password,
    }

    lines: list[str] = []
    for line in EXAMPLE.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("#") or "=" not in line:
            lines.append(line)
            continue
        key, value = line.split("=", 1)
        for marker, factory in replacements.items():
            if marker in value:
                value = value.replace(marker, factory())
        lines.append(f"{key}={value}")

    TARGET.write_text("\n".join(lines) + "\n", encoding="utf-8")
    TARGET.chmod(0o600)
    print(f"wrote {TARGET}; review it before starting compose")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
