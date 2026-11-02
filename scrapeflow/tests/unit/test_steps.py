from __future__ import annotations

import time

import pytest
from apps.api.schemas.automation import (
    ClickStep,
    ExecuteIfPresentStep,
    ExtractStep,
    GetTextStep,
    GotoStep,
    HoverStep,
    LoopPagesStep,
    PressStep,
    ScreenshotStep,
    ScrollStep,
    SelectStep,
    SleepStep,
    TypeStep,
    WaitForStep,
)
from apps.worker.browser.steps import (
    SeleniumActions,
    StepExecutionError,
    StepRun,
    execute_steps,
    redact,
    resolve_secrets,
)
from packages.core.errors import AppError, ErrorCode


class FakeActions:
    def __init__(self) -> None:
        self.current = "https://example.com/"
        self.present: set[str] = set()
        self.texts: dict[str, str] = {}
        self.values_map: dict[str, list[str]] = {}
        self.failures: dict[str, list[Exception]] = {}
        self.clicked: list[str] = []
        self.typed: list[tuple[str, str]] = []
        self.pressed: list[tuple[str | None, str]] = []
        self.selected: list[tuple[str, str]] = []
        self.hovered: list[str] = []
        self.scrolled: list[tuple[str | None, int, int]] = []
        self.waited: list[tuple[str, str]] = []
        self.slept: list[float] = []
        self.shots: list[bool] = []
        self.pages_left = 0

    def _fail(self, selector: str | None) -> None:
        queue = self.failures.get(selector or "") if selector else None
        if queue:
            raise queue.pop(0)

    def goto(self, url: str, *, timeout: float) -> str:
        self.current = url
        return url

    def current_url(self) -> str:
        return self.current

    def page_source(self) -> str:
        return "<html><body>fake</body></html>"

    def click(self, selector: str, *, by: str, timeout: float) -> None:
        self._fail(selector)
        self.clicked.append(selector)
        if selector == "#next" and self.pages_left > 0:
            self.pages_left -= 1
            self.current = f"https://example.com/page-{self.pages_left}"

    def type_text(self, selector: str, text: str, *, by: str, clear: bool, timeout: float) -> None:
        self._fail(selector)
        self.typed.append((selector, text))

    def press(self, key: str, *, selector: str | None, by: str, timeout: float) -> None:
        self._fail(selector)
        self.pressed.append((selector, key))

    def select_option(self, selector: str, value: str, *, by: str, timeout: float) -> None:
        self._fail(selector)
        self.selected.append((selector, value))

    def hover(self, selector: str, *, by: str, timeout: float) -> None:
        self._fail(selector)
        self.hovered.append(selector)

    def wait_for(self, selector: str, *, by: str, state: str, timeout: float) -> None:
        self._fail(selector)
        self.waited.append((selector, state))

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)

    def scroll(self, *, selector: str | None, by: str, x: int, y: int, timeout: float) -> None:
        self._fail(selector)
        self.scrolled.append((selector, x, y))

    def exists(self, selector: str, *, by: str, timeout: float) -> bool:
        self._fail(selector)
        return selector in self.present

    def text(self, selector: str, *, by: str, timeout: float) -> str:
        self._fail(selector)
        return " ".join(self.texts.get(selector, "").split())

    def values(self, selector: str, *, by: str, attr: str | None, timeout: float) -> list[str]:
        self._fail(selector)
        return self.values_map.get(selector, [])

    def screenshot(self, *, full_page: bool) -> bytes:
        self.shots.append(full_page)
        return b"\x89PNG-" + (b"full" if full_page else b"view")


def _run(steps: list[object], *, secrets: dict[str, str] | None = None) -> StepRun:
    run = StepRun()
    execute_steps(
        FakeActions(),
        steps,  # type: ignore[arg-type]
        run=run,
        secrets=secrets or {},
        deadline=time.monotonic() + 30,
    )
    return run


def test_every_action_executes_and_records_status() -> None:
    actions = FakeActions()
    actions.present = {"#present"}
    actions.texts = {"#label": "  Hello   world "}
    actions.values_map = {"#items": ["one", "two", "three"]}
    run = StepRun()
    steps = [
        GotoStep(url="https://example.com/start"),
        ClickStep(selector="#a"),
        TypeStep(selector="#i", text="hello"),
        PressStep(selector="#i", key="ENTER"),
        PressStep(key="TAB"),
        SelectStep(selector="#s", value="v"),
        HoverStep(selector="#h"),
        WaitForStep(selector="#w"),
        SleepStep(seconds=0.1),
        ScrollStep(selector="#h"),
        ScrollStep(x=0, y=300),
        ExtractStep(name="one", selector="#items"),
        ExtractStep(name="all", selector="#items", all=True, limit=2),
        GetTextStep(name="label", selector="#label"),
        ScreenshotStep(name="shot"),
        ScreenshotStep(name="full", full_page=True),
        ExecuteIfPresentStep(selector="#present", steps=[ClickStep(selector="#nested")]),
        ExecuteIfPresentStep(selector="#absent", steps=[ClickStep(selector="#never")]),
    ]
    execute_steps(
        actions,
        steps,
        run=run,
        secrets={},
        deadline=time.monotonic() + 30,
    )

    assert all(record.status == "ok" for record in run.records)
    assert run.records[-1].detail == "absent"
    assert run.extracted == {
        "one": "one",
        "all": ["one", "two"],
        "label": "Hello world",
    }
    assert [shot.name for shot in run.screenshots] == ["shot", "full"]
    assert actions.clicked == ["#a", "#nested"]
    assert actions.typed == [("#i", "hello")]
    assert actions.pressed == [("#i", "ENTER"), (None, "TAB")]
    assert actions.selected == [("#s", "v")]
    assert actions.hovered == ["#h"]
    assert actions.waited == [("#w", "visible")]
    assert actions.scrolled == [("#h", 0, 0), (None, 0, 300)]


def test_secret_interpolation_and_redaction() -> None:
    actions = FakeActions()
    run = StepRun()
    secrets = {"user": "alice", "pass": "s3cret"}
    execute_steps(
        actions,
        [
            TypeStep(selector="#u", text="{{user}}"),
            TypeStep(selector="#p", text="prefix-{{pass}}"),
            SelectStep(selector="#s", value="{{pass}}"),
            PressStep(selector="#p", key="{{pass}}"),
        ],
        run=run,
        secrets=secrets,
        deadline=time.monotonic() + 10,
    )
    assert actions.typed == [("#u", "alice"), ("#p", "prefix-s3cret")]
    assert actions.selected == [("#s", "s3cret")]
    assert actions.pressed == [("#p", "s3cret")]
    assert "s3cret" not in str(run.as_dict())
    assert redact("prefix-s3cret", secrets) == "prefix-[REDACTED]"


def test_missing_secret_fails_without_leaking() -> None:
    run = StepRun()
    with pytest.raises(StepExecutionError) as raised:
        execute_steps(
            FakeActions(),
            [TypeStep(selector="#p", text="{{pass}}")],
            run=run,
            secrets={},
            deadline=time.monotonic() + 10,
        )
    assert raised.value.error.code == ErrorCode.STEP_FAILED
    assert "s3cret" not in raised.value.error.message
    assert run.records[-1].status == "failed"


def test_optional_step_continues_after_failure() -> None:
    actions = FakeActions()
    actions.failures["#missing"] = [
        AppError(
            422,
            ErrorCode.SELECTOR_NOT_FOUND,
            "Element not found",
            details={"retryable": False},
        )
    ]
    run = StepRun()
    execute_steps(
        actions,
        [
            ClickStep(selector="#missing", optional=True),
            ClickStep(selector="#after"),
        ],
        run=run,
        secrets={},
        deadline=time.monotonic() + 10,
    )
    assert [record.status for record in run.records] == ["skipped", "ok"]
    assert run.records[0].error_code == "SELECTOR_NOT_FOUND"
    assert actions.clicked == ["#after"]


def test_retryable_step_is_retried_then_succeeds() -> None:
    actions = FakeActions()
    actions.failures["#flaky"] = [
        AppError(
            502,
            ErrorCode.UPSTREAM_ERROR,
            "Transient browser failure",
            details={"retryable": True},
        ),
        AppError(
            502,
            ErrorCode.UPSTREAM_ERROR,
            "Transient browser failure",
            details={"retryable": True},
        ),
    ]
    run = StepRun()
    execute_steps(
        actions,
        [ClickStep(selector="#flaky", retries=2)],
        run=run,
        secrets={},
        deadline=time.monotonic() + 10,
    )
    assert run.records[0].status == "ok"
    assert actions.clicked == ["#flaky"]


def test_permanent_failure_stops_nested_execution() -> None:
    actions = FakeActions()
    actions.failures["#dead"] = [
        AppError(
            422,
            ErrorCode.SELECTOR_NOT_FOUND,
            "Element not found",
            details={"retryable": False},
        )
    ]
    run = StepRun()
    with pytest.raises(StepExecutionError) as raised:
        execute_steps(
            actions,
            [
                ClickStep(selector="#first"),
                ClickStep(selector="#dead"),
                ClickStep(selector="#never"),
            ],
            run=run,
            secrets={},
            deadline=time.monotonic() + 10,
        )
    assert raised.value.path == "1"
    assert raised.value.error.details["step"] == "1"
    assert [record.status for record in run.records] == ["ok", "failed"]
    assert actions.clicked == ["#first"]


def test_execute_if_present_runs_nested_steps_only_when_present() -> None:
    actions = FakeActions()
    actions.present = {"#modal"}
    run = StepRun()
    execute_steps(
        actions,
        [
            ExecuteIfPresentStep(selector="#modal", steps=[ClickStep(selector="#accept")]),
            ExecuteIfPresentStep(selector="#other", steps=[ClickStep(selector="#never")]),
        ],
        run=run,
        secrets={},
        deadline=time.monotonic() + 10,
    )
    assert actions.clicked == ["#accept"]
    assert [record.path for record in run.records] == ["0.0", "0", "1"]


def test_loop_pages_runs_nested_steps_per_page() -> None:
    actions = FakeActions()
    actions.pages_left = 2
    actions.present = {"#next"}
    actions.texts = {"#label": "row"}
    run = StepRun()
    execute_steps(
        actions,
        [
            LoopPagesStep(
                next_selector="#next",
                max_pages=3,
                steps=[GetTextStep(name="row", selector="#label")],
            )
        ],
        run=run,
        secrets={},
        deadline=time.monotonic() + 10,
    )
    assert run.extracted == {"row": "row"}
    assert actions.clicked == ["#next", "#next"]
    assert run.records[-1].detail == "3 page(s)"
    paths = [record.path for record in run.records]
    assert "0[0].0" in paths and "0[2].0" in paths


def test_deadline_expired_raises_timeout() -> None:
    run = StepRun()
    with pytest.raises(StepExecutionError) as raised:
        execute_steps(
            FakeActions(),
            [ClickStep(selector="#a")],
            run=run,
            secrets={},
            deadline=time.monotonic() - 1,
        )
    assert raised.value.error.code == ErrorCode.TIMEOUT


def test_resolve_secrets_leaves_plain_text_untouched() -> None:
    assert resolve_secrets("no placeholders", {"a": "b"}) == "no placeholders"


def test_selenium_actions_is_a_browser_actions_implementation() -> None:
    assert hasattr(SeleniumActions, "goto")
    assert hasattr(SeleniumActions, "screenshot")
