import base64
import re
from typing import Any

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from . import config
from .security import assert_safe_url

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
PHONE_RE = re.compile(r"(?:\+\d{1,3}[\s-]?)?(?:\(\d{2,4}\)[\s-]?)?\d{3,4}[\s-]?\d{3,4}[\s-]?\d{0,4}")


def make_driver() -> webdriver.Chrome:
    opts = Options()
    if config.CHROME_BIN:
        opts.binary_location = config.CHROME_BIN
    for arg in (
        "--headless=new",
        "--no-sandbox",
        "--disable-dev-shm-usage",
        "--disable-gpu",
        "--disable-extensions",
        "--window-size=1366,900",
        f"--user-agent={config.USER_AGENT}",
    ):
        opts.add_argument(arg)
    if config.PROXY_URL:
        opts.add_argument(f"--proxy-server={config.PROXY_URL}")
    opts.page_load_strategy = "eager"
    service = Service(config.CHROMEDRIVER) if config.CHROMEDRIVER else None
    driver = webdriver.Chrome(options=opts, service=service) if service else webdriver.Chrome(options=opts)
    driver.set_page_load_timeout(config.PAGE_TIMEOUT)
    return driver


def extract(driver: webdriver.Chrome, spec: dict[str, Any]) -> dict[str, Any]:
    """spec: {"name": "css"} or {"name": {"css": "...", "attr": "href", "all": true}}"""
    out: dict[str, Any] = {}
    for name, rule in spec.items():
        if isinstance(rule, str):
            rule = {"css": rule}
        els = driver.find_elements(By.CSS_SELECTOR, rule["css"])
        attr = rule.get("attr")
        vals = [(e.get_attribute(attr) if attr else e.text.strip()) for e in els]
        out[name] = vals if rule.get("all", True) else (vals[0] if vals else None)
    return out


def screenshot_b64(driver: webdriver.Chrome) -> str:
    return base64.b64encode(driver.get_screenshot_as_png()).decode()


def scrape(
    url: str,
    selectors: dict[str, Any] | None = None,
    wait_for: str | None = None,
    screenshot: bool = False,
    include_html: bool = False,
    find_contacts: bool = False,
) -> dict[str, Any]:
    assert_safe_url(url)
    driver = make_driver()
    try:
        driver.get(url)
        assert_safe_url(driver.current_url)  # re-check after redirects
        if wait_for:
            WebDriverWait(driver, config.WAIT_TIMEOUT).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, wait_for))
            )

        text = driver.find_element(By.TAG_NAME, "body").text[: config.MAX_TEXT_CHARS]
        links = []
        for a in driver.find_elements(By.CSS_SELECTOR, "a[href]")[: config.MAX_LINKS]:
            href = a.get_attribute("href")
            if href and href.startswith(("http://", "https://")):
                links.append({"text": a.text.strip()[:120], "href": href})

        meta = {}
        for m in driver.find_elements(By.CSS_SELECTOR, "meta[name], meta[property]"):
            key = m.get_attribute("name") or m.get_attribute("property")
            val = m.get_attribute("content")
            if key and val and (key in ("description", "keywords") or key.startswith(("og:", "twitter:"))):
                meta[key] = val

        result: dict[str, Any] = {
            "url": driver.current_url,
            "title": driver.title,
            "meta": meta,
            "text": text,
            "links": links,
        }
        if selectors:
            result["data"] = extract(driver, selectors)
        if find_contacts:
            result["emails"] = sorted(set(EMAIL_RE.findall(driver.page_source)))[:100]
            result["phones"] = sorted({p.strip() for p in PHONE_RE.findall(text) if len(re.sub(r"\D", "", p)) >= 8})[:100]
        if include_html:
            result["html"] = driver.page_source[: config.MAX_TEXT_CHARS * 2]
        if screenshot:
            result["screenshot_b64"] = screenshot_b64(driver)
        return result
    finally:
        driver.quit()
