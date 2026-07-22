"""Reference fetching helpers for J-STAGE article pages."""

from __future__ import annotations

import html
import re
import time
from typing import Dict, List, Optional

import requests
from bs4 import BeautifulSoup

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36"
)
DEFAULT_REFERENCE_META_NAME = "citation_reference"
DEFAULT_REFERENCE_LIST_ID = "article-overview-references-list"


def _normalize_reference_text(text: str) -> str:
    normalized = html.unescape(text)
    normalized = normalized.replace("\xa0", " ")
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized.strip()


def _parse_references_from_meta(
    soup: BeautifulSoup,
    meta_name: str = DEFAULT_REFERENCE_META_NAME,
) -> List[str]:
    references: List[str] = []
    for meta in soup.find_all("meta", attrs={"name": meta_name}):
        content = meta.get("content")
        if not content:
            continue
        text = _normalize_reference_text(content)
        if text:
            references.append(text)
    return references


def _parse_references_from_list(
    soup: BeautifulSoup,
    ul_id: str = DEFAULT_REFERENCE_LIST_ID,
) -> List[str]:
    ul = soup.find("ul", id=ul_id)
    if ul is None:
        return []

    references: List[str] = []
    for li in ul.find_all("li"):
        span = li.find("span", class_="reference-num-txt")
        if span is None:
            continue
        text = _normalize_reference_text(span.get_text(separator=" ", strip=True))
        if text:
            references.append(text)
    return references


def _parse_references(
    html_text: str,
    ul_id: str = DEFAULT_REFERENCE_LIST_ID,
    meta_name: str = DEFAULT_REFERENCE_META_NAME,
) -> List[str]:
    soup = BeautifulSoup(html_text, "html.parser")

    meta_references = _parse_references_from_meta(soup, meta_name=meta_name)
    if meta_references:
        return meta_references

    return _parse_references_from_list(soup, ul_id=ul_id)


def get_references(
    url: str,
    driver: Optional[object] = None,
    ul_id: str = DEFAULT_REFERENCE_LIST_ID,
    wait_sec: int = 20,
    session: Optional[requests.Session] = None,
) -> List[str]:
    """Fetch references from one J-STAGE article page."""
    del driver

    own_session = session is None
    if own_session:
        session = requests.Session()
        session.headers.update({"User-Agent": USER_AGENT})

    try:
        response = session.get(url, timeout=wait_sec)
        response.raise_for_status()
        return _parse_references(response.text, ul_id=ul_id)
    except requests.RequestException:
        return []
    finally:
        if own_session and session is not None:
            session.close()


def get_references_batch(
    urls: List[str],
    ul_id: str = DEFAULT_REFERENCE_LIST_ID,
    wait_sec: int = 20,
    sleep_sec: float = 1.0,
    headless: bool = True,
) -> Dict[str, List[str]]:
    """Fetch references for many URLs, returning [] for failed URLs."""
    del headless

    if not urls:
        return {}

    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})

    results: Dict[str, List[str]] = {}
    try:
        for index, url in enumerate(urls):
            results[url] = get_references(
                url,
                ul_id=ul_id,
                wait_sec=wait_sec,
                session=session,
            )

            if index < len(urls) - 1 and sleep_sec > 0:
                time.sleep(sleep_sec)
    finally:
        session.close()

    return results
