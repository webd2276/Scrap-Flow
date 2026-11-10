#!/usr/bin/env python3
"""Assemble the ScrapeFlow deck from the source fragments.

The slide source is split across ``src/*.html`` so each part stays editable.
This script concatenates them in order and injects the per-slide closing
"in short" strip, keyed by page number, so the layout stays consistent.

Usage:
    python3 docs/presentation/build.py
"""

from __future__ import annotations

from pathlib import Path

HERE = Path(__file__).resolve().parent
SRC = HERE / "src"
OUT = HERE / "presentation.html"

PARTS = [
    "00-head.html",
    "01-cover.html",
    "02-architecture.html",
    "03-backend.html",
    "04-frontend.html",
    "05-demo.html",
    "06-closing.html",
]

# Page number -> one-line takeaway shown above the footer.
TAKEAWAYS: dict[int, str] = {
    2: "The deck follows the order of a code review: what it does, how it is wired, which library does what, then the evidence.",
    3: "The hard part is never the HTTP fetch — it is isolation, durability, safety and accounting around it.",
    5: "Every capability on this slide maps to a module path, so a claim can be checked against code in one step.",
    7: "The API only validates, records and enqueues. Everything slow and failure-prone happens outside the request.",
    8: "One row per layer. If a library is not on this slide, it is not in the runtime dependency list.",
    9: "Two application languages, one rule: typed at the boundary, tested at the edge.",
    10: "Lockfiles are committed. A fresh clone resolves to the exact versions that passed the gates.",
    11: "Eight groups, one responsibility each — no library is present for decoration.",
    13: "PostgreSQL is the record of what happened. Redis may lose data without rewriting history.",
    15: "Two engines, one contract: the caller gets the same result shape whether or not JavaScript was required.",
    16: "The database stores metadata, object storage stores bytes, and the API stores neither.",
    17: "Compromise one layer and the next still holds: hashed credentials, scoped tokens, validated egress.",
    18: "Pricing lives in code, usage lives in rows, and limits are enforced before work starts.",
    19: "If a job cannot be explained from logs, metrics and events, it is not operable.",
    20: "Three runtime packages. Every other name on this slide is a build-time tool.",
    21: "The browser never holds a long-lived credential — and never needs a CORS configuration.",
    23: "Fast unit tests for logic, one real browser journey for the wiring, a production build for the boundary.",
    26: "Schedules, keys and billing are first-class screens, not settings hidden in a menu.",
    29: "The schema is generated from the implementation, so documentation cannot silently drift.",
    30: "Eleven services, one network, three volumes. Reset is safe because all state is named.",
    31: "Production changes the edge, not the application: same images, Caddy in front, no dev ports.",
    32: "The platform is a first-class target, not a footnote in the README.",
    33: "Every skip is documented with a reason. A green run without that context would be misleading.",
    34: "The left column is evidence. The right column is a to-do list that needs external services.",
    35: "The next milestone is not more features — it is proving the external paths and the capacity curve.",
}


def build() -> None:
    html = "".join((SRC / part).read_text(encoding="utf-8") for part in PARTS)

    chunks = html.split('<div class="footer">')
    if len(chunks) != 37:
        raise SystemExit(f"expected 36 slides, found {len(chunks) - 1} footers")

    assembled = [chunks[0]]
    for index, chunk in enumerate(chunks[1:], start=1):
        text = TAKEAWAYS.get(index)
        if text:
            assembled.append(
                '<div class="takeaway"><span class="lbl">In short</span>'
                f"<p>{text}</p></div>\n  "
            )
        assembled.append('<div class="footer">')
        assembled.append(chunk)

    OUT.write_text("".join(assembled), encoding="utf-8")
    print(f"wrote {OUT} ({OUT.stat().st_size:,} bytes, {len(chunks) - 1} slides)")


if __name__ == "__main__":
    build()
