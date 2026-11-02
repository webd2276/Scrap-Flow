"""HTML extraction with parsel."""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urljoin

from packages.core.errors import AppError, ErrorCode
from parsel import Selector

from apps.api.schemas.scrape import ExtractOptions, SelectorSpec

_WHITESPACE = re.compile(r"\s+")
_MAX_META = 100


def normalise_text(value: str) -> str:
    return _WHITESPACE.sub(" ", value).strip()


def _text_of(node: Any) -> str:
    try:
        value = node.xpath("string(.)").get()
    except (AttributeError, TypeError):
        value = None
    if value is None:
        value = getattr(node, "root", "")
    if isinstance(value, bytes):
        value = value.decode("utf-8", "replace")
    return normalise_text(str(value))


def _select_values(selector: Selector, spec: SelectorSpec) -> list[str]:
    try:
        nodes = selector.css(spec.css) if spec.css else selector.xpath(spec.xpath or "")
    except Exception as exc:
        raise AppError(
            422,
            ErrorCode.VALIDATION_ERROR,
            f"Invalid selector: {exc}",
        ) from exc
    values: list[str] = []
    for node in nodes:
        if spec.attr:
            attributes = getattr(node, "attrib", {})
            value = attributes.get(spec.attr) if isinstance(attributes, dict) else None
            if value is None:
                continue
            values.append(normalise_text(str(value)))
        else:
            value = _text_of(node)
            if value:
                values.append(value)
    return values


def extract_page(
    html: str,
    *,
    base_url: str,
    options: ExtractOptions,
    selectors: dict[str, SelectorSpec],
) -> dict[str, Any]:
    selector = Selector(text=html, base_url=base_url)
    result: dict[str, Any] = {}

    if options.title:
        title = selector.css("title::text").get() or selector.xpath("//title/text()").get()
        result["title"] = normalise_text(title or "")

    if options.text:
        body = selector.xpath("//body")
        root = body[0] if body else selector
        texts = root.xpath(
            ".//text()[not(ancestor::script) and not(ancestor::style) "
            "and not(ancestor::noscript) and not(ancestor::template)]"
        ).getall()
        result["text"] = normalise_text(" ".join(texts))[: options.max_text_chars]

    if options.links:
        seen: set[str] = set()
        links: list[str] = []
        for href in selector.xpath("//a/@href").getall():
            absolute = urljoin(base_url, href.strip())
            if absolute and absolute not in seen:
                seen.add(absolute)
                links.append(absolute)
                if len(links) >= options.max_links:
                    break
        result["links"] = links

    if options.meta:
        meta: dict[str, str] = {}
        for node in selector.xpath("//meta")[:_MAX_META]:
            key = node.attrib.get("name") or node.attrib.get("property")
            content = node.attrib.get("content")
            if key and content:
                meta[key] = normalise_text(content)
        result["meta"] = meta

    result["selectors"] = {name: _selected(selector, spec) for name, spec in selectors.items()}
    return result


def _selected(selector: Selector, spec: SelectorSpec) -> str | list[str] | None:
    values = _select_values(selector, spec)
    if spec.all:
        return values[: spec.limit]
    return values[0] if values else None


def find_next_url(
    html: str,
    *,
    base_url: str,
    spec: SelectorSpec,
) -> str | None:
    selector = Selector(text=html, base_url=base_url)
    values = _select_values(selector, spec)
    if not values:
        return None
    return urljoin(base_url, values[0])
