from __future__ import annotations

from datetime import UTC, datetime

import pytest
from packages.core.schedules import (
    MISSING,
    ScheduleValidationError,
    compute_changes,
    extract_path,
    extract_values,
    next_run_after,
    normalize_watched_fields,
    parse_field_path,
    validate_cron,
    validate_timezone,
)


def test_validate_cron_accepts_five_field_expressions() -> None:
    assert validate_cron("*/5 * * * *") == "*/5 * * * *"
    assert validate_cron("  0 9 * * 1-5  ") == "0 9 * * 1-5"


@pytest.mark.parametrize(
    "expression",
    [
        "",
        "* * * *",
        "* * * * * *",
        "not a cron at all",
        "x * * * *",
    ],
)
def test_validate_cron_rejects_invalid_expressions(expression: str) -> None:
    with pytest.raises(ScheduleValidationError):
        validate_cron(expression)


def test_validate_cron_rejects_oversized_expressions() -> None:
    with pytest.raises(ScheduleValidationError):
        validate_cron("1" * 121 + " * * * *")


def test_validate_timezone_accepts_iana_names() -> None:
    assert validate_timezone("UTC") == "UTC"
    assert validate_timezone("Europe/Berlin") == "Europe/Berlin"


@pytest.mark.parametrize("name", ["", "  ", "Mars/Olympus_Mons", "x" * 65])
def test_validate_timezone_rejects_unknown_names(name: str) -> None:
    with pytest.raises(ScheduleValidationError):
        validate_timezone(name)


def test_next_run_after_is_strictly_in_the_future() -> None:
    base = datetime(2026, 1, 1, 0, 0, tzinfo=UTC)
    assert next_run_after("0 9 * * *", "UTC", base) == datetime(2026, 1, 1, 9, 0, tzinfo=UTC)

    at_occurrence = datetime(2026, 1, 1, 9, 0, tzinfo=UTC)
    assert next_run_after("0 9 * * *", "UTC", at_occurrence) == datetime(
        2026, 1, 2, 9, 0, tzinfo=UTC
    )


def test_next_run_after_uses_the_schedule_timezone() -> None:
    base = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    result = next_run_after("0 9 * * *", "America/New_York", base)
    assert result == datetime(2026, 1, 1, 14, 0, tzinfo=UTC)


def test_next_run_after_tracks_dst_transitions() -> None:
    # US DST starts at 02:00 local on 2026-03-08; 09:00 local moves from
    # UTC-5 to UTC-4, so consecutive occurrences are 23 hours apart.
    first = next_run_after(
        "0 9 * * *",
        "America/New_York",
        datetime(2026, 3, 7, 15, 0, tzinfo=UTC),
    )
    assert first == datetime(2026, 3, 8, 13, 0, tzinfo=UTC)
    second = next_run_after("0 9 * * *", "America/New_York", first)
    assert second == datetime(2026, 3, 9, 13, 0, tzinfo=UTC)


def test_parse_field_path_handles_dots_and_indexes() -> None:
    assert parse_field_path("title") == ("title",)
    assert parse_field_path("a.b[0].c") == ("a", "b", 0, "c")
    assert parse_field_path("items[2][0]") == ("items", 2, 0)
    assert parse_field_path("_a-b.c_1") == ("_a-b", "c_1")


@pytest.mark.parametrize(
    "path",
    ["", ".a", "a.", "a..b", "a[", "a[-1]", "a[x]", "a b", "1abc", "a[b]", "a" * 129],
)
def test_parse_field_path_rejects_invalid_paths(path: str) -> None:
    with pytest.raises(ScheduleValidationError):
        parse_field_path(path)


def test_normalize_watched_fields_rejects_duplicates_and_excess() -> None:
    assert normalize_watched_fields(["a", "b[0]"]) == ["a", "b[0]"]
    with pytest.raises(ScheduleValidationError):
        normalize_watched_fields(["a", "a"])
    with pytest.raises(ScheduleValidationError):
        normalize_watched_fields([f"f{i}" for i in range(51)])


def test_extract_path_returns_missing_for_absent_values() -> None:
    data = {"a": {"b": [1, {"c": 2}]}, "none": None}
    assert extract_path(data, "a.b[1].c") == 2
    assert extract_path(data, "none") is None
    assert extract_path(data, "a.b[2]") is MISSING
    assert extract_path(data, "a.b.c") is MISSING
    assert extract_path(data, "a.missing") is MISSING
    assert extract_path([], "a") is MISSING


def test_extract_values_serialises_non_scalar_values() -> None:
    values = extract_values(
        {
            "title": "Hello",
            "tags": ["a", 1, True],
            "meta": {"x": 1},
            "missing": MISSING,
            "raw": object(),
        },
        ["title", "tags", "meta", "missing", "raw"],
    )
    assert values["title"] == "Hello"
    assert values["tags"] == ["a", 1, True]
    assert values["meta"] == {"x": 1}
    assert values["missing"] is None
    assert isinstance(values["raw"], str)


def test_compute_changes_treats_first_snapshot_as_baseline() -> None:
    assert compute_changes(None, {"title": "A"}) == []


def test_compute_changes_reports_appeared_disappeared_and_changed() -> None:
    changes = compute_changes(
        {"same": 1, "old": "x", "gone": "y", "new": None},
        {"same": 1, "old": "z", "gone": None, "new": "n"},
    )
    by_field = {item["field"]: item for item in changes}
    assert set(by_field) == {"old", "gone", "new"}
    assert by_field["old"] == {"field": "old", "type": "changed", "previous": "x", "current": "z"}
    assert by_field["gone"] == {"field": "gone", "type": "disappeared", "previous": "y"}
    assert by_field["new"] == {"field": "new", "type": "appeared", "current": "n"}


def test_compute_changes_ignores_unchanged_and_null_to_null() -> None:
    assert compute_changes({"a": 1, "b": None}, {"a": 1, "b": None}) == []
