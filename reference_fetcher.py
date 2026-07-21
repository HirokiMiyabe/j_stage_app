"""Reference fetching helpers for J-STAGE article pages."""

from __future__ import annotations

import os
import re
import time
from pathlib import Path
from typing import Dict, List, Optional

from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36"
)
DEFAULT_REFERENCE_LIST_ID = "article-overview-references-list"
CHROME_BINARY_ENV_VARS = ("CHROME_BIN", "GOOGLE_CHROME_BIN", "CHROMIUM_BIN")
CHROME_BINARY_CANDIDATES = (
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files\Chromium\Application\chrome.exe",
    r"C:\Program Files (x86)\Chromium\Application\chrome.exe",
    "/usr/bin/chromium",
    "/usr/bin/chromium-browser",
    "/usr/bin/google-chrome",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
)


def _resolve_chrome_binary() -> Optional[str]:
    for env_var in CHROME_BINARY_ENV_VARS:
        candidate = os.getenv(env_var)
        if candidate and Path(candidate).exists():
            return candidate

    for candidate in CHROME_BINARY_CANDIDATES:
        if Path(candidate).exists():
            return candidate
    return None


def create_driver(headless: bool = True) -> webdriver.Chrome:
    """Create a Selenium Chrome driver with conservative defaults."""
    options = Options()
    if headless:
        options.add_argument("--headless=new")
    options.add_argument("--disable-gpu")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--no-sandbox")
    options.add_argument("--window-size=1280,1800")
    options.add_argument(f"user-agent={USER_AGENT}")

    chrome_binary = _resolve_chrome_binary()
    if chrome_binary is not None:
        options.binary_location = chrome_binary

    return webdriver.Chrome(options=options)


def _parse_references(html: str, ul_id: str = DEFAULT_REFERENCE_LIST_ID) -> List[str]:
    """Parse rendered HTML and return the visible reference strings."""
    soup = BeautifulSoup(html, "html.parser")
    ul = soup.find("ul", id=ul_id)
    if ul is None:
        return []

    references: List[str] = []
    for li in ul.find_all("li"):
        span = li.find("span", class_="reference-num-txt")
        if span is None:
            continue
        text = span.get_text(separator=" ", strip=True)
        text = re.sub(r"\s+", " ", text)
        if text:
            references.append(text)
    return references


def get_references(
    url: str,
    driver: Optional[webdriver.Chrome] = None,
    ul_id: str = DEFAULT_REFERENCE_LIST_ID,
    wait_sec: int = 20,
) -> List[str]:
    """Fetch references from one J-STAGE article page."""
    own_driver = driver is None
    if own_driver:
        driver = create_driver()

    try:
        driver.get(url)
        try:
            WebDriverWait(driver, wait_sec).until(
                EC.presence_of_element_located((By.ID, ul_id))
            )
        except TimeoutException:
            return []
        return _parse_references(driver.page_source, ul_id)
    finally:
        if own_driver and driver is not None:
            driver.quit()


def get_references_batch(
    urls: List[str],
    ul_id: str = DEFAULT_REFERENCE_LIST_ID,
    wait_sec: int = 20,
    sleep_sec: float = 1.0,
    headless: bool = True,
) -> Dict[str, List[str]]:
    """Fetch references for many URLs, returning [] for failed URLs."""
    if not urls:
        return {}

    driver = create_driver(headless=headless)
    results: Dict[str, List[str]] = {}
    try:
        for index, url in enumerate(urls):
            try:
                results[url] = get_references(
                    url,
                    driver=driver,
                    ul_id=ul_id,
                    wait_sec=wait_sec,
                )
            except Exception:
                results[url] = []

            if index < len(urls) - 1 and sleep_sec > 0:
                time.sleep(sleep_sec)
    finally:
        driver.quit()

    return results
