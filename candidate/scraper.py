"""
HTML parsing and price extraction for the price intelligence platform.

PriceParser extracts structured product data from retailer page HTML.
It validates structural integrity (valid parseable HTML above a minimum
size threshold) before attempting extraction.

Content validity — distinguishing product pages from challenge or error
pages — is a separate concern handled upstream by the HTTP client and
error classifier. Those layers filter non-200 responses before the
response body reaches the parser.
"""

from __future__ import annotations

import logging
import re
import time
from typing import Optional

from bs4 import BeautifulSoup

from .config import config
from .models import ParseResult

logger = logging.getLogger(__name__)


class PriceParser:
    """
    Extracts price and availability from a retailer product page.

    The parser operates in two phases:
      1. Structural validation: is this valid, parseable HTML above the
         minimum size threshold?
      2. Content extraction: locate price and availability selectors

    success=True means phase 1 passed. price=None on a successful parse
    means the product is currently unlisted — not that the page was wrong.

    Does not distinguish between product pages and non-product pages
    (challenge pages, access-denied pages, maintenance pages) — those
    are expected to have been filtered upstream by the HTTP client before
    the response body reaches this method.
    """

    _PRICE_RE = re.compile(r"[\$£€]?\s*(\d{1,6}[.,]\d{2})\b")

    def parse(self, html: str, url: str = "") -> ParseResult:
        """
        Parse product page HTML and extract price/availability.

        Returns ParseResult with success=True if the HTML is structurally
        valid (parseable and above the minimum size threshold).

        Returns ParseResult with success=False only if:
          - html is None or empty
          - html is below config.scraper.min_page_size_bytes
          - BeautifulSoup raises an exception during parsing
        """
        t0 = time.monotonic()

        if not html or len(html) < config.scraper.min_page_size_bytes:
            return ParseResult(
                success=False,
                price=None,
                available=None,
                raw_html_size=len(html) if html else 0,
                parse_duration_ms=(time.monotonic() - t0) * 1000,
            )

        try:
            soup = BeautifulSoup(html, "html.parser")
        except Exception as exc:
            logger.warning("html parse error for %s: %s", url, exc)
            return ParseResult(
                success=False,
                price=None,
                available=None,
                raw_html_size=len(html),
                parse_duration_ms=(time.monotonic() - t0) * 1000,
            )

        price = self._extract_price(soup)
        available = self._extract_availability(soup)
        elapsed = (time.monotonic() - t0) * 1000

        logger.debug(
            "parsed %s: price=%s available=%s (%.1fms)",
            url, price, available, elapsed,
        )

        return ParseResult(
            success=True,
            price=price,
            available=available,
            raw_html_size=len(html),
            parse_duration_ms=elapsed,
        )

    def _extract_price(self, soup: BeautifulSoup) -> Optional[float]:
        el = soup.select_one(config.scraper.price_selector)
        if el is None:
            return None
        text = el.get_text(strip=True)
        match = self._PRICE_RE.search(text)
        if not match:
            return None
        raw = match.group(1).replace(",", ".")
        try:
            return float(raw)
        except ValueError:
            return None

    def _extract_availability(self, soup: BeautifulSoup) -> Optional[bool]:
        el = soup.select_one(config.scraper.availability_selector)
        if el is None:
            return None
        text = el.get_text(strip=True).lower()
        if any(kw in text for kw in ("in stock", "available", "add to cart")):
            return True
        if any(kw in text for kw in ("out of stock", "unavailable", "sold out")):
            return False
        return None
