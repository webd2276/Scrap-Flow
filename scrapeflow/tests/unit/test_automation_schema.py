from __future__ import annotations

import pytest
from apps.api.schemas.automation import (
    MAX_STEPS,
    AutomationRequest,
    ClickStep,
    ExecuteIfPresentStep,
    GotoStep,
    LoopPagesStep,
    TypeStep,
    walk_steps,
)
from pydantic import ValidationError


def _steps(count: int) -> list[dict[str, object]]:
    return [{"action": "click", "selector": f"#item-{index}"} for index in range(count)]


def test_minimal_request_defaults() -> None:
    request = AutomationRequest(
        url="https://example.com/", steps=[{"action": "click", "selector": "#go"}]
    )
    assert request.secrets == {}
    assert request.screenshot is False
    assert isinstance(request.steps[0], ClickStep)


def test_unknown_action_and_extra_fields_are_rejected() -> None:
    with pytest.raises(ValidationError):
        AutomationRequest(url="https://example.com/", steps=[{"action": "explode"}])
    with pytest.raises(ValidationError):
        AutomationRequest(
            url="https://example.com/",
            steps=[{"action": "click", "selector": "#go", "payload": "x"}],
        )
    with pytest.raises(ValidationError):
        AutomationRequest(url="https://example.com/", steps=[{"action": "click"}])


def test_goto_requires_absolute_http_url() -> None:
    with pytest.raises(ValidationError):
        GotoStep(url="/relative")
    with pytest.raises(ValidationError):
        GotoStep(url="file:///etc/passwd")
    assert GotoStep(url="https://example.com/x").url == "https://example.com/x"


def test_secret_placeholders_must_be_declared() -> None:
    with pytest.raises(ValidationError):
        AutomationRequest(
            url="https://example.com/",
            steps=[{"action": "type", "selector": "#p", "text": "{{pass}}"}],
        )
    request = AutomationRequest(
        url="https://example.com/",
        steps=[{"action": "type", "selector": "#p", "text": "{{pass}}"}],
        secrets={"pass": "hunter2"},
    )
    assert request.secrets == {"pass": "hunter2"}


def test_malformed_placeholders_are_rejected() -> None:
    with pytest.raises(ValidationError):
        AutomationRequest(
            url="https://example.com/",
            steps=[{"action": "type", "selector": "#p", "text": "{{pass"}],
            secrets={"pass": "x"},
        )


def test_secret_names_and_bounds() -> None:
    with pytest.raises(ValidationError):
        AutomationRequest(
            url="https://example.com/",
            steps=[{"action": "click", "selector": "#a"}],
            secrets={"1bad": "x"},
        )
    too_many = {f"s{index}": "x" for index in range(21)}
    with pytest.raises(ValidationError):
        AutomationRequest(
            url="https://example.com/",
            steps=[{"action": "click", "selector": "#a"}],
            secrets=too_many,
        )
    with pytest.raises(ValidationError):
        AutomationRequest(
            url="https://example.com/",
            steps=[{"action": "click", "selector": "#a"}],
            secrets={"big": "x" * 4097},
        )


def test_step_count_is_bounded() -> None:
    request = AutomationRequest(url="https://example.com/", steps=_steps(MAX_STEPS))
    assert len(request.steps) == MAX_STEPS
    with pytest.raises(ValidationError):
        AutomationRequest(url="https://example.com/", steps=_steps(MAX_STEPS + 1))


def test_nesting_depth_is_bounded() -> None:
    deep: dict[str, object] = {"action": "click", "selector": "#leaf"}
    for index in range(3):
        deep = {
            "action": "execute_if_present",
            "selector": f"#level-{index}",
            "steps": [deep],
        }
    with pytest.raises(ValidationError):
        AutomationRequest(url="https://example.com/", steps=[deep])

    allowed: dict[str, object] = {"action": "click", "selector": "#leaf"}
    for index in range(2):
        allowed = {
            "action": "execute_if_present",
            "selector": f"#level-{index}",
            "steps": [allowed],
        }
    request = AutomationRequest(url="https://example.com/", steps=[allowed])
    assert max(depth for _step, depth in walk_steps(request.steps)) == 3


def test_container_steps_require_children() -> None:
    with pytest.raises(ValidationError):
        ExecuteIfPresentStep(selector="#optional")
    with pytest.raises(ValidationError):
        LoopPagesStep(next_selector="#next")


def test_walk_steps_counts_nested_steps() -> None:
    step = LoopPagesStep(
        next_selector="#next",
        steps=[TypeStep(selector="#q", text="x", optional=True)],
    )
    walked = walk_steps([step, ClickStep(selector="#go")])
    assert len(walked) == 3
    assert [depth for _step, depth in walked] == [1, 2, 1]


def test_headers_are_restricted() -> None:
    with pytest.raises(ValidationError):
        AutomationRequest(
            url="https://example.com/",
            steps=[{"action": "click", "selector": "#a"}],
            headers={"Host": "evil"},
        )
    with pytest.raises(ValidationError):
        AutomationRequest(
            url="https://example.com/",
            steps=[{"action": "click", "selector": "#a"}],
            headers={"X-Test": "a\r\nInjected: 1"},
        )


def test_extract_and_screenshot_names_are_bounded() -> None:
    with pytest.raises(ValidationError):
        AutomationRequest(
            url="https://example.com/",
            steps=[{"action": "extract", "name": "1bad", "selector": "#a"}],
        )
    with pytest.raises(ValidationError):
        AutomationRequest(
            url="https://example.com/",
            steps=[{"action": "screenshot", "name": "../escape"}],
        )
    request = AutomationRequest(
        url="https://example.com/",
        steps=[
            {"action": "extract", "name": "price", "selector": "#p"},
            {"action": "screenshot", "name": "after-submit"},
        ],
    )
    assert len(request.steps) == 2
