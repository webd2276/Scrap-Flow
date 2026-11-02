"""Streaming CSV/JSON export helpers with spreadsheet-injection protection."""

from __future__ import annotations

import csv
import io
import json
from collections.abc import Iterable, Iterator
from typing import Any

_DANGEROUS_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def escape_csv_value(value: Any) -> str:
    """Quote a cell and neutralise spreadsheet formulas in untrusted strings."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    text = str(value)
    stripped = text.lstrip()
    if stripped.startswith(_DANGEROUS_PREFIXES) or text.startswith(("\t", "\r")):
        return "'" + text
    return text


def flatten_mapping(value: Any, prefix: str = "") -> dict[str, Any]:
    """Flatten nested dicts/lists into deterministic dot/bracket paths."""
    output: dict[str, Any] = {}

    def walk(current: Any, path: str) -> None:
        if isinstance(current, dict):
            for key in sorted(current, key=str):
                child = f"{path}.{key}" if path else str(key)
                walk(current[key], child)
            return
        if isinstance(current, list):
            for index, item in enumerate(current):
                walk(item, f"{path}[{index}]")
            return
        output[path or "value"] = current

    walk(value, prefix)
    return output


def csv_chunk(values: list[Any]) -> bytes:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\r\n")
    writer.writerow([escape_csv_value(value) for value in values])
    return buffer.getvalue().encode("utf-8")


def iter_csv(
    header: list[str],
    rows: Iterable[list[Any]],
) -> Iterator[bytes]:
    yield csv_chunk(header)
    for row in rows:
        yield csv_chunk(row)


def iter_json(value: Any) -> Iterator[bytes]:
    encoder = json.JSONEncoder(ensure_ascii=False, separators=(",", ":"), default=str)
    for chunk in encoder.iterencode(value):
        yield chunk.encode("utf-8")


def content_disposition(filename: str) -> str:
    safe = "".join(char for char in filename if char.isalnum() or char in "._-")
    return f'attachment; filename="{safe or "export"}"'
