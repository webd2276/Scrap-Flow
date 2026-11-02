from __future__ import annotations

import pytest
from packages.core.models import OrgPlan
from packages.core.plans import (
    PLANS,
    automation_credit_cost,
    plan_for,
    scrape_credit_cost,
)


def test_plan_catalog_matches_the_product_spec() -> None:
    assert PLANS[OrgPlan.FREE].monthly_credits == 100
    assert PLANS[OrgPlan.FREE].max_concurrency == 1
    assert PLANS[OrgPlan.FREE].max_steps == 10
    assert PLANS[OrgPlan.FREE].max_pages == 5
    assert PLANS[OrgPlan.FREE].artifact_retention_days == 1

    assert PLANS[OrgPlan.STARTER].monthly_credits == 5_000
    assert PLANS[OrgPlan.PRO].monthly_credits == 50_000
    assert PLANS[OrgPlan.BUSINESS].monthly_credits == 250_000
    assert PLANS[OrgPlan.BUSINESS].max_pages == 500
    assert PLANS[OrgPlan.BUSINESS].artifact_retention_days == 90


def test_plan_lookup_accepts_stored_strings() -> None:
    assert plan_for("pro") is PLANS[OrgPlan.PRO]
    assert plan_for(OrgPlan.BUSINESS) is PLANS[OrgPlan.BUSINESS]
    with pytest.raises(ValueError):
        plan_for("enterprise")


def test_scrape_credit_weights() -> None:
    assert (
        scrape_credit_cost(
            render_js=False,
            screenshot=False,
            proxy_country=None,
            max_pages=1,
        )
        == 1
    )
    assert (
        scrape_credit_cost(
            render_js=True,
            screenshot=True,
            proxy_country=None,
            max_pages=1,
        )
        == 3
    )
    assert (
        scrape_credit_cost(
            render_js=False,
            screenshot=False,
            proxy_country=None,
            max_pages=5,
        )
        == 5
    )
    assert (
        scrape_credit_cost(
            render_js=True,
            screenshot=False,
            proxy_country="DE",
            max_pages=3,
        )
        == 6
    )


def test_automation_credit_weights() -> None:
    assert (
        automation_credit_cost(
            step_count=1,
            screenshot=False,
            screenshot_steps=0,
            proxy_country=None,
            extra_pages=0,
        )
        == 3
    )
    assert (
        automation_credit_cost(
            step_count=10,
            screenshot=False,
            screenshot_steps=0,
            proxy_country=None,
            extra_pages=0,
        )
        == 3
    )
    assert (
        automation_credit_cost(
            step_count=11,
            screenshot=True,
            screenshot_steps=2,
            proxy_country=None,
            extra_pages=3,
        )
        == 2 + 2 + 1 + 2 + 3
    )
