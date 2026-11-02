from __future__ import annotations

import pytest
from apps.api.schemas.scrape import (
    PaginationOptions,
    ScrapeRequest,
    SelectorSpec,
)
from pydantic import ValidationError


def test_selector_requires_exactly_one_query() -> None:
    with pytest.raises(ValidationError):
        SelectorSpec()
    with pytest.raises(ValidationError):
        SelectorSpec(css="h1", xpath="//h1")
    assert SelectorSpec(css="h1").css == "h1"
    assert SelectorSpec(xpath="//h1").xpath == "//h1"


def test_selector_all_and_limit() -> None:
    spec = SelectorSpec(css="a", all=True, limit=3)
    assert spec.all is True
    assert spec.limit == 3
    with pytest.raises(ValidationError):
        SelectorSpec(css="a", limit=0)
    with pytest.raises(ValidationError):
        SelectorSpec(css="a", limit=201)


def test_minimal_request_defaults() -> None:
    request = ScrapeRequest(url="https://example.com/")
    assert request.render_js is False
    assert request.extract.title is True
    assert request.extract.text is True
    assert request.extract.links is False
    assert request.selectors == {}


def test_screenshot_and_wait_for_need_browser() -> None:
    with pytest.raises(ValidationError):
        ScrapeRequest(url="https://example.com/", screenshot=True)
    with pytest.raises(ValidationError):
        ScrapeRequest(url="https://example.com/", wait_for="main")
    request = ScrapeRequest(
        url="https://example.com/", render_js=True, screenshot=True, wait_for="main"
    )
    assert request.render_js is True


def test_headers_are_restricted() -> None:
    with pytest.raises(ValidationError):
        ScrapeRequest(url="https://example.com/", headers={"Host": "evil"})
    with pytest.raises(ValidationError):
        ScrapeRequest(url="https://example.com/", headers={"X-Bad\n": "x"})
    with pytest.raises(ValidationError):
        ScrapeRequest(url="https://example.com/", headers={"X-Test": "a\r\nInjected: 1"})
    ok = ScrapeRequest(url="https://example.com/", headers={"X-Test": "value"})
    assert ok.headers == {"X-Test": "value"}


def test_url_must_have_host_and_no_control_characters() -> None:
    with pytest.raises(ValidationError):
        ScrapeRequest(url="https:///path")
    with pytest.raises(ValidationError):
        ScrapeRequest(url="https://example.com/a\nb")
    with pytest.raises(ValidationError):
        ScrapeRequest(url="https://example.com/", webhook_url="https://example.com/a\r\nb")


def test_proxy_country_is_upper_cased() -> None:
    request = ScrapeRequest(url="https://example.com/", proxy_country="de")
    assert request.proxy_country == "DE"


def test_pagination_defaults_next_attribute_to_href() -> None:
    pagination = PaginationOptions(next_selector=SelectorSpec(css="a.next"))
    assert pagination.next_selector.attr == "href"
    with pytest.raises(ValidationError):
        PaginationOptions(next_selector=SelectorSpec(css="a.next", all=True))
    with pytest.raises(ValidationError):
        PaginationOptions(next_selector=SelectorSpec(css="a.next"), max_pages=1)


def test_selector_names_and_count_are_bounded() -> None:
    with pytest.raises(ValidationError):
        ScrapeRequest(
            url="https://example.com/",
            selectors={"1bad": SelectorSpec(css="h1")},
        )
    too_many = {f"field_{index}": SelectorSpec(css="h1") for index in range(51)}
    with pytest.raises(ValidationError):
        ScrapeRequest(url="https://example.com/", selectors=too_many)
