from __future__ import annotations

import pytest
from apps.api.schemas.scrape import ExtractOptions, SelectorSpec
from apps.worker.extract import extract_page, find_next_url
from packages.core.errors import AppError, ErrorCode

HTML = """
<!doctype html>
<html>
  <head>
    <title>  Example   Page </title>
    <meta name="description" content="A demo page">
    <meta property="og:title" content="OG title">
    <style>.hidden { display: none }</style>
    <script>window.secret = "not text";</script>
  </head>
  <body>
    <h1 class="title">Hello <span>world</span></h1>
    <p class="body">First paragraph.</p>
    <p class="body">Second paragraph.</p>
    <a href="/one">One</a>
    <a href="https://other.example/two">Two</a>
    <a href="/one">Duplicate</a>
    <a class="next" href="/page/2">Next</a>
    <noscript>Ignore me</noscript>
  </body>
</html>
"""


def test_extract_title_text_links_and_meta() -> None:
    result = extract_page(
        HTML,
        base_url="https://example.com/base/",
        options=ExtractOptions(links=True, meta=True),
        selectors={},
    )
    assert result["title"] == "Example Page"
    assert "Hello world" in result["text"]
    assert "First paragraph." in result["text"]
    assert "window.secret" not in result["text"]
    assert ".hidden" not in result["text"]
    assert result["links"] == [
        "https://example.com/one",
        "https://other.example/two",
        "https://example.com/page/2",
    ]
    assert result["meta"]["description"] == "A demo page"
    assert result["meta"]["og:title"] == "OG title"


def test_css_xpath_attr_all_and_limits() -> None:
    selectors = {
        "heading": SelectorSpec(css="h1.title"),
        "paragraphs": SelectorSpec(css="p.body", all=True, limit=2),
        "first_link": SelectorSpec(css="a", attr="href"),
        "xpath_links": SelectorSpec(xpath="//a/@href", all=True, limit=2),
        "missing": SelectorSpec(css=".does-not-exist"),
        "missing_all": SelectorSpec(css=".does-not-exist", all=True),
    }
    result = extract_page(
        HTML,
        base_url="https://example.com/",
        options=ExtractOptions(title=False, text=False),
        selectors=selectors,
    )
    chosen = result["selectors"]
    assert chosen["heading"] == "Hello world"
    assert chosen["paragraphs"] == ["First paragraph.", "Second paragraph."]
    assert chosen["first_link"] == "/one"
    assert chosen["xpath_links"] == ["/one", "https://other.example/two"]
    assert chosen["missing"] is None
    assert chosen["missing_all"] == []


def test_text_length_is_capped() -> None:
    result = extract_page(
        HTML,
        base_url="https://example.com/",
        options=ExtractOptions(text=True, max_text_chars=10),
        selectors={},
    )
    assert len(result["text"]) == 10


def test_invalid_selector_is_a_typed_error() -> None:
    with pytest.raises(AppError) as exc:
        extract_page(
            HTML,
            base_url="https://example.com/",
            options=ExtractOptions(),
            selectors={"broken": SelectorSpec(css="a[")},
        )
    assert exc.value.status_code == 422
    assert exc.value.code == ErrorCode.VALIDATION_ERROR


def test_find_next_url() -> None:
    assert (
        find_next_url(
            HTML,
            base_url="https://example.com/list/",
            spec=SelectorSpec(css="a.next", attr="href"),
        )
        == "https://example.com/page/2"
    )
    assert (
        find_next_url(
            HTML,
            base_url="https://example.com/list/",
            spec=SelectorSpec(css="a.missing", attr="href"),
        )
        is None
    )
