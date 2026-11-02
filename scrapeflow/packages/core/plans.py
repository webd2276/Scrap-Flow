"""Plan catalog and credit weights.

Plans are configuration, not database rows: changing an allowance is a code
change with tests, so a customer can never be billed against a plan definition
that was edited in production by accident.

Credit weights (from the architecture plan):

* base job: 1
* browser execution: 1
* screenshot: 1
* proxy: 2
* every extra page: 1
* every started ten automation steps: 1
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from packages.core.models import OrgPlan


@dataclass(frozen=True, slots=True)
class Plan:
    code: OrgPlan
    name: str
    monthly_credits: int
    max_concurrency: int
    max_steps: int
    max_pages: int
    artifact_retention_days: int


PLANS: dict[OrgPlan, Plan] = {
    OrgPlan.FREE: Plan(
        code=OrgPlan.FREE,
        name="Free",
        monthly_credits=100,
        max_concurrency=1,
        max_steps=10,
        max_pages=5,
        artifact_retention_days=1,
    ),
    OrgPlan.STARTER: Plan(
        code=OrgPlan.STARTER,
        name="Starter",
        monthly_credits=5_000,
        max_concurrency=3,
        max_steps=50,
        max_pages=25,
        artifact_retention_days=7,
    ),
    OrgPlan.PRO: Plan(
        code=OrgPlan.PRO,
        name="Pro",
        monthly_credits=50_000,
        max_concurrency=10,
        max_steps=100,
        max_pages=100,
        artifact_retention_days=30,
    ),
    OrgPlan.BUSINESS: Plan(
        code=OrgPlan.BUSINESS,
        name="Business",
        monthly_credits=250_000,
        max_concurrency=25,
        max_steps=200,
        max_pages=500,
        artifact_retention_days=90,
    ),
}

BASE_COST = 1
BROWSER_COST = 1
SCREENSHOT_COST = 1
PROXY_COST = 2


def plan_for(value: str | OrgPlan) -> Plan:
    """Return the catalog entry for a stored plan value."""
    code = value if isinstance(value, OrgPlan) else OrgPlan(value)
    try:
        return PLANS[code]
    except KeyError as exc:  # pragma: no cover - enums make this unreachable
        raise ValueError(f"Unknown plan: {value!r}") from exc


def scrape_credit_cost(
    *,
    render_js: bool,
    screenshot: bool,
    proxy_country: str | None,
    max_pages: int,
) -> int:
    """Credits reserved for one scrape job."""
    cost = BASE_COST
    if render_js:
        cost += BROWSER_COST
    if screenshot:
        cost += SCREENSHOT_COST
    if proxy_country:
        cost += PROXY_COST
    cost += max(0, max_pages - 1)
    return cost


def automation_credit_cost(
    *,
    step_count: int,
    screenshot: bool,
    screenshot_steps: int,
    proxy_country: str | None,
    extra_pages: int,
) -> int:
    """Credits reserved for one automation job (always browser-executed)."""
    cost = BASE_COST + BROWSER_COST
    cost += math.ceil(max(0, step_count) / 10)
    if screenshot:
        cost += SCREENSHOT_COST
    cost += max(0, screenshot_steps) * SCREENSHOT_COST
    if proxy_country:
        cost += PROXY_COST
    cost += max(0, extra_pages)
    return cost
