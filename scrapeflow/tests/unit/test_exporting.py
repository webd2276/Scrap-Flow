from __future__ import annotations

import json

import pytest
from packages.core.exporting import (
    content_disposition,
    csv_chunk,
    escape_csv_value,
    flatten_mapping,
    iter_csv,
    iter_json,
)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, ""),
        (True, "true"),
        (False, "false"),
        (12, "12"),
        (-1, "-1"),
        (1.5, "1.5"),
        ("plain", "plain"),
        ("=SUM(A1:A2)", "'=SUM(A1:A2)"),
        ("+cmd", "'+cmd"),
        ("-cmd", "'-cmd"),
        ("@cmd", "'@cmd"),
        ("\tcmd", "'\tcmd"),
        ("\rcmd", "'\rcmd"),
        ("  =cmd", "'  =cmd"),
        ("safe = formula", "safe = formula"),
    ],
)
def test_escape_csv_value_neutralises_formulas(value: object, expected: str) -> None:
    assert escape_csv_value(value) == expected


def test_flatten_mapping_is_deterministic_and_nested() -> None:
    flattened = flatten_mapping(
        {"z": [1, {"a": 2}], "a": {"b": True}, "empty": {}},
        "result",
    )
    assert flattened == {
        "result.a.b": True,
        "result.z[0]": 1,
        "result.z[1].a": 2,
    }
    assert list(flatten_mapping({"b": 1, "a": 2})) == ["a", "b"]


def test_flatten_mapping_scalar_and_empty() -> None:
    assert flatten_mapping("value") == {"value": "value"}
    assert flatten_mapping({}) == {}
    assert flatten_mapping([], "items") == {}


def test_csv_chunk_quotes_special_characters() -> None:
    chunk = csv_chunk(["a,b", 'say "hi"', "line\nbreak", "=cmd"])
    assert chunk == b'"a,b","say ""hi""","line\nbreak",\'=cmd\r\n'


def test_iter_csv_yields_header_then_rows() -> None:
    chunks = list(iter_csv(["name", "value"], [["alpha", 1], ["beta", "=2"]]))
    assert chunks == [
        b"name,value\r\n",
        b"alpha,1\r\n",
        b"beta,'=2\r\n",
    ]


def test_iter_json_preserves_unicode_and_compact_separators() -> None:
    payload = {"message": "héllo", "values": [1, 2]}
    encoded = b"".join(iter_json(payload))
    assert encoded.decode("utf-8") == '{"message":"héllo","values":[1,2]}'
    assert json.loads(encoded) == payload


def test_content_disposition_strips_unsafe_characters() -> None:
    assert content_disposition("job-1.csv") == 'attachment; filename="job-1.csv"'
    assert content_disposition('../../evil"\r\n.csv') == 'attachment; filename="....evil.csv"'
    assert content_disposition("") == 'attachment; filename="export"'
