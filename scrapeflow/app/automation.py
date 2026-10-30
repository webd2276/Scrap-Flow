"""Step-based browser automation.

Each step is a dict: {"action": "<name>", ...params}. Supported actions:

  goto        url
  click       css
  type        css, text, [clear=true], [submit=false]
  press       key            (ENTER, TAB, ESCAPE, ...)
  select      css, value     (for <select>)
  wait_for    css, [timeout]
  sleep       seconds
  scroll      [to="bottom"|"top"] or [y=pixels]
  extract     name, selectors={...}   (same format as /v1/scrape)
  get_text    name, css
  screenshot  name
"""
import time
from typing import Any

from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import Select, WebDriverWait

from . import config
from .scraper import extract, make_driver, screenshot_b64
from .security import assert_safe_url


class StepError(Exception):
    pass


def _need(step: dict, *keys: str) -> None:
    for k in keys:
        if k not in step:
            raise StepError(f"'{step.get('action')}' needs '{k}'")


def run_steps(steps: list[dict[str, Any]]) -> dict[str, Any]:
    if not steps:
        raise StepError("No steps given")
    if len(steps) > config.MAX_STEPS:
        raise StepError(f"Too many steps (max {config.MAX_STEPS})")

    driver = make_driver()
    outputs: dict[str, Any] = {}
    log: list[dict[str, Any]] = []
    try:
        for i, step in enumerate(steps):
            action = step.get("action")
            started = time.time()
            try:
                if action == "goto":
                    _need(step, "url")
                    assert_safe_url(step["url"])
                    driver.get(step["url"])
                    assert_safe_url(driver.current_url)
                elif action == "click":
                    _need(step, "css")
                    el = WebDriverWait(driver, config.WAIT_TIMEOUT).until(
                        EC.element_to_be_clickable((By.CSS_SELECTOR, step["css"]))
                    )
                    el.click()
                elif action == "type":
                    _need(step, "css", "text")
                    el = WebDriverWait(driver, config.WAIT_TIMEOUT).until(
                        EC.visibility_of_element_located((By.CSS_SELECTOR, step["css"]))
                    )
                    if step.get("clear", True):
                        el.clear()
                    el.send_keys(step["text"])
                    if step.get("submit"):
                        el.send_keys(Keys.ENTER)
                elif action == "press":
                    _need(step, "key")
                    key = getattr(Keys, str(step["key"]).upper(), None)
                    if key is None:
                        raise StepError(f"Unknown key: {step['key']}")
                    driver.switch_to.active_element.send_keys(key)
                elif action == "select":
                    _need(step, "css", "value")
                    el = WebDriverWait(driver, config.WAIT_TIMEOUT).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, step["css"]))
                    )
                    Select(el).select_by_value(str(step["value"]))
                elif action == "wait_for":
                    _need(step, "css")
                    WebDriverWait(driver, min(int(step.get("timeout", config.WAIT_TIMEOUT)), 60)).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, step["css"]))
                    )
                elif action == "sleep":
                    time.sleep(min(float(step.get("seconds", 1)), config.MAX_SLEEP))
                elif action == "scroll":
                    if "y" in step:
                        driver.execute_script("window.scrollBy(0, arguments[0]);", int(step["y"]))
                    elif step.get("to") == "top":
                        driver.execute_script("window.scrollTo(0, 0);")
                    else:
                        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                elif action == "extract":
                    _need(step, "name", "selectors")
                    outputs[step["name"]] = extract(driver, step["selectors"])
                elif action == "get_text":
                    _need(step, "name", "css")
                    outputs[step["name"]] = driver.find_element(By.CSS_SELECTOR, step["css"]).text.strip()
                elif action == "screenshot":
                    outputs[step.get("name", f"shot_{i}")] = screenshot_b64(driver)
                else:
                    raise StepError(f"Unknown action: {action}")
                log.append({"step": i, "action": action, "ok": True, "ms": int((time.time() - started) * 1000)})
            except Exception as exc:  # noqa: BLE001 - report which step failed
                log.append({"step": i, "action": action, "ok": False, "error": type(exc).__name__ + ": " + str(exc)[:300]})
                if step.get("optional"):
                    continue
                try:
                    outputs["_failure_screenshot"] = screenshot_b64(driver)
                except Exception:  # noqa: BLE001
                    pass
                raise StepError(f"Step {i} ({action}) failed: {str(exc)[:200]}") from exc
        return {"final_url": driver.current_url, "title": driver.title, "outputs": outputs, "log": log}
    except StepError as exc:
        exc.partial = {"outputs": outputs, "log": log}  # type: ignore[attr-defined]
        raise
    finally:
        driver.quit()
