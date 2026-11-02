"""Cron scheduling, watched-field extraction, and change detection.

These helpers are shared by the API (validation) and the worker (dispatch and
post-run diffing). They deliberately contain no database or web framework code.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from croniter import CroniterBadCronError, croniter

_FIELD_PATH = re.compile(
    r"^[A-Za-z_][A-Za-z0-9_-]*"
    r"(?:\.(?:[A-Za-z_][A-Za-z0-9_-]*|[0-9]+)|\[[0-9]+\])*$"
)
_MAX_FIELD_PATH = 128
_MAX_WATCHED_FIELDS = 50
MISSING = object()


class ScheduleValidationError(ValueError):
    """A cron expression, timezone, or watched field is invalid."""


def validate_cron(expression: str) -> str:
    expression = expression.strip()
    if len(expression) > 120:
        raise ScheduleValidationError("cron expression is too long")
    if len(expression.split()) != 5:
        raise ScheduleValidationError("cron expression must have exactly 5 fields")
    try:
        if not croniter.is_valid(expression):
            raise ScheduleValidationError("cron expression is invalid")
    except (CroniterBadCronError, ValueError) as exc:
        raise ScheduleValidationError("cron expression is invalid") from exc
    return expression


def validate_timezone(name: str) -> str:
    name = name.strip()
    if not name or len(name) > 64:
        raise ScheduleValidationError("timezone is invalid")
    try:
        ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ScheduleValidationError(f"unknown timezone: {name}") from exc
    return name


def next_run_after(expression: str, timezone: str, base: datetime | None = None) -> datetime:
    """Return the first occurrence strictly after ``base``, in UTC."""
    moment = (base or datetime.now(UTC)).astimezone(UTC)
    zone = ZoneInfo(timezone)
    local = moment.astimezone(zone)
    iterator = croniter(expression, local)
    candidate: datetime = iterator.get_next(datetime)
    if candidate.tzinfo is None:
        candidate = candidate.replace(tzinfo=zone)
    return candidate.astimezone(UTC)


def parse_field_path(path: str) -> tuple[str | int, ...]:
    """Parse ``a.b[0].c`` into ``("a", "b", 0, "c")``."""
    if not path or len(path) > _MAX_FIELD_PATH or not _FIELD_PATH.fullmatch(path):
        raise ScheduleValidationError(f"invalid watched field path: {path!r}")
    tokens: list[str | int] = []
    for segment in re.split(r"\.", path):
        while segment:
            match = re.match(r"^([A-Za-z_][A-Za-z0-9_-]*)(.*)$", segment)
            if match is None:
                raise ScheduleValidationError(f"invalid watched field path: {path!r}")
            tokens.append(match.group(1))
            segment = match.group(2)
            while segment.startswith("["):
                end = segment.find("]")
                if end < 0:
                    raise ScheduleValidationError(f"invalid watched field path: {path!r}")
                index = segment[1:end]
                if not index.isdigit():
                    raise ScheduleValidationError(f"invalid watched field path: {path!r}")
                tokens.append(int(index))
                segment = segment[end + 1 :]
            if segment:
                raise ScheduleValidationError(f"invalid watched field path: {path!r}")
    return tuple(tokens)


def normalize_watched_fields(fields: list[str]) -> list[str]:
    if len(fields) > _MAX_WATCHED_FIELDS:
        raise ScheduleValidationError(f"at most {_MAX_WATCHED_FIELDS} watched fields are allowed")
    normalized: list[str] = []
    for field in fields:
        parse_field_path(field)
        if field in normalized:
            raise ScheduleValidationError(f"duplicate watched field: {field}")
        normalized.append(field)
    return normalized


def extract_path(data: Any, path: str) -> Any:
    """Return the value at ``path`` or :data:`MISSING`."""
    current = data
    for token in parse_field_path(path):
        if isinstance(token, int):
            if not isinstance(current, list) or token >= len(current):
                return MISSING
            current = current[token]
        else:
            if not isinstance(current, dict) or token not in current:
                return MISSING
            current = current[token]
    return current


def _jsonable(value: Any) -> Any:
    if value is MISSING:
        return None
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    return repr(value)


def extract_values(data: Any, fields: list[str]) -> dict[str, Any]:
    return {field: _jsonable(extract_path(data, field)) for field in fields}


def compute_changes(
    previous: dict[str, Any] | None,
    current: dict[str, Any],
) -> list[dict[str, Any]]:
    """Diff watched values. The first snapshot (``previous is None``) is a baseline."""
    if previous is None:
        return []
    changes: list[dict[str, Any]] = []
    for field, value in current.items():
        before_present = field in previous and previous[field] is not None
        after_present = value is not None
        if not before_present and after_present:
            changes.append({"field": field, "type": "appeared", "current": value})
        elif before_present and not after_present:
            changes.append({"field": field, "type": "disappeared", "previous": previous[field]})
        elif before_present and after_present and previous[field] != value:
            changes.append(
                {
                    "field": field,
                    "type": "changed",
                    "previous": previous[field],
                    "current": value,
                }
            )
    return changes
