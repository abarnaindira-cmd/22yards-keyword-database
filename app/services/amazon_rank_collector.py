import os
import re
import time
from dataclasses import dataclass, asdict
from typing import List, Optional
from urllib.parse import quote_plus

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

from app.services.keyword_collector import DEFAULT_USER_AGENT


@dataclass
class AmazonResult:
    asin: str
    rank_position: int
    title: str
    product_url: Optional[str] = None
    price: Optional[str] = None
    rating: Optional[float] = None
    review_count: Optional[int] = None
    page_number: int = 1

    def to_dict(self):
        return asdict(self)


def _text(locator) -> str:
    try:
        return locator.inner_text().strip()
    except Exception:
        return ""


def _parse_rating(text: str) -> Optional[float]:
    m = re.search(r"(\d+(?:\.\d+)?)\s+out of", text or "", re.I)
    return float(m.group(1)) if m else None


def _parse_review_count(text: str) -> Optional[int]:
    if not text:
        return None
    cleaned = text.replace(",", "").strip()
    m = re.search(r"(\d+(?:\.\d+)?)\s*([KkMm])?", cleaned)
    if not m:
        return None
    value = float(m.group(1))
    suffix = (m.group(2) or "").lower()
    if suffix == "k":
        value *= 1000
    elif suffix == "m":
        value *= 1_000_000
    return int(value)


def _parse_card(card, rank: int, page_number: int) -> Optional[AmazonResult]:
    asin = (card.get_attribute("data-asin") or "").strip()
    if not asin:
        return None

    title = ""
    title_loc = card.locator("h2 a span").first
    if title_loc.count():
        title = _text(title_loc)
    if not title:
        title_loc = card.locator("h2").first
        if title_loc.count():
            title = _text(title_loc)

    link = None
    link_loc = card.locator("h2 a").first
    if link_loc.count():
        link = link_loc.get_attribute("href")
        if link and link.startswith("/"):
            link = "https://www.amazon.in" + link

    price = None
    price_loc = card.locator("span.a-price span.a-offscreen").first
    if price_loc.count():
        price = _text(price_loc)

    rating_text = _text(card.locator("span.a-icon-alt").first) if card.locator("span.a-icon-alt").count() else ""
    rating = _parse_rating(rating_text)

    review_count = None
    review_loc = card.locator("span.a-size-base.s-underline-text").first
    if review_loc.count():
        review_count = _parse_review_count(_text(review_loc))

    return AmazonResult(
        asin=asin,
        rank_position=rank,
        title=title,
        product_url=link,
        price=price,
        rating=rating,
        review_count=review_count,
        page_number=page_number,
    )


from typing import List, Optional


def search_amazon_results(
    keyword: str,
    max_pages: int = 2,
    max_results: int = 100,
    delay_seconds: float = 1.5,
    headless: Optional[bool] = None,
) -> List[AmazonResult]:
    """Collect displayed Amazon.in product-card results in order.

    This function only reads public search-result pages. If Amazon presents a CAPTCHA,
    sign-in wall, or other access block, it raises RuntimeError instead of guessing data.
    """
    if not keyword or not keyword.strip():
        return []

    if headless is None:
        headless = os.getenv("HEADLESS", "true").lower() == "true"

    results: List[AmazonResult] = []
    seen = set()

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=headless)
        context = browser.new_context(
            user_agent=DEFAULT_USER_AGENT,
            locale="en-IN",
            viewport={"width": 1366, "height": 900},
            extra_http_headers={"Accept-Language": "en-IN,en;q=0.9"},
        )
        page = context.new_page()
        page.set_default_timeout(20000)

        try:
            for page_number in range(1, max_pages + 1):
                url = f"https://www.amazon.in/s?k={quote_plus(keyword.strip())}&page={page_number}"
                try:
                    page.goto(url, wait_until="domcontentloaded", timeout=30000)
                except PlaywrightTimeoutError:
                    # Continue parsing if the page partially loaded.
                    pass

                page.wait_for_timeout(1500)
                try:
                    page.wait_for_selector('div[data-component-type="s-search-result"][data-asin]', timeout=5000)
                except Exception:
                    pass
                body_text = _text(page.locator("body"))
                lower = body_text.lower()
                if "enter the characters you see below" in lower or "captcha" in lower:
                    raise RuntimeError("Amazon CAPTCHA/access challenge detected")
                if "sorry! something went wrong" in lower and "search" not in lower:
                    raise RuntimeError("Amazon returned an error page")

                cards = page.locator('div[data-component-type="s-search-result"][data-asin]')
                count = cards.count()
                if count == 0:
                    # A useful diagnostic instead of fabricating a rank.
                    if "no results" in lower:
                        break
                    raise RuntimeError(f"No Amazon product cards found for keyword '{keyword}'")

                for i in range(count):
                    card = cards.nth(i)
                    item = _parse_card(card, len(results) + 1, page_number)
                    if not item or item.asin in seen:
                        continue
                    seen.add(item.asin)
                    item.rank_position = len(results) + 1
                    results.append(item)
                    if len(results) >= max_results:
                        return results

                if delay_seconds > 0 and page_number < max_pages:
                    time.sleep(delay_seconds)
        finally:
            context.close()
            browser.close()

    return results



