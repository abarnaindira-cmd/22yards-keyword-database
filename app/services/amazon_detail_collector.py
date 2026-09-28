import os
import re
import time
from dataclasses import dataclass, asdict
from typing import List, Optional, Dict, Any
from urllib.parse import quote_plus

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

from app.services.keyword_collector import DEFAULT_USER_AGENT


@dataclass
class CompetitorProductDetail:
    asin: str
    title: str
    description: str
    bullet_points: List[str]
    price: Optional[str] = None
    rating: Optional[float] = None
    review_count: Optional[int] = None
    reviews: List[str] = None
    product_url: Optional[str] = None

    def __post_init__(self):
        if self.bullet_points is None:
            self.bullet_points = []
        if self.reviews is None:
            self.reviews = []

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _clean_text(text: str) -> str:
    if not text:
        return ""
    cleaned = re.sub(r"<[^>]+>", " ", text)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


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


def extract_details_from_page(page, asin: str, product_url: Optional[str] = None) -> CompetitorProductDetail:
    """Extract product details, description, bullet points, and reviews from an open Playwright page."""
    body_text = page.locator("body").inner_text() if page.locator("body").count() else ""
    lower = body_text.lower()
    if "enter the characters you see below" in lower or "captcha" in lower:
        raise RuntimeError(f"CAPTCHA challenge encountered on product page for ASIN {asin}")

    # 1. Title
    title = ""
    for sel in ["#productTitle", "h1#title", "#title span"]:
        loc = page.locator(sel).first
        if loc.count() > 0:
            title = _clean_text(loc.inner_text())
            if title:
                break

    # 2. Description
    description = ""
    for sel in ["#productDescription", "#productDescription_feature_div", "#bookDescription_feature_div"]:
        loc = page.locator(sel).first
        if loc.count() > 0:
            description = _clean_text(loc.inner_text())
            if description:
                break

    # 3. Bullet Points / Feature Bullets
    bullet_points: List[str] = []
    bp_locs = page.locator("#feature-bullets ul li span.a-list-item, #featurebullets_feature_div ul li span.a-list-item")
    count = bp_locs.count()
    for i in range(count):
        bp_text = _clean_text(bp_locs.nth(i).inner_text())
        if bp_text and len(bp_text) > 3 and bp_text not in bullet_points:
            bullet_points.append(bp_text)

    # 4. Price
    price = None
    for sel in ["span.a-price span.a-offscreen", "#priceblock_ourprice", "#priceblock_dealprice", ".apexPriceToPay span.a-offscreen"]:
        loc = page.locator(sel).first
        if loc.count() > 0:
            p_text = _clean_text(loc.inner_text())
            if p_text and ("₹" in p_text or "INR" in p_text or p_text.replace(".", "").isdigit()):
                price = p_text
                break

    # 5. Rating
    rating = None
    rating_loc = page.locator("span.a-icon-alt, #acrPopover").first
    if rating_loc.count() > 0:
        rating = _parse_rating(rating_loc.inner_text())

    # 6. Review Count
    review_count = None
    rc_loc = page.locator("#acrCustomerReviewText, span#acrCustomerReviewText").first
    if rc_loc.count() > 0:
        review_count = _parse_review_count(rc_loc.inner_text())

    # 7. Customer Reviews
    reviews: List[str] = []
    rev_locs = page.locator("div[data-hook='review-collapsed'] span, span[data-hook='review-body'] span, .review-text-content span")
    rcount = rev_locs.count()
    for i in range(min(rcount, 10)):
        r_text = _clean_text(rev_locs.nth(i).inner_text())
        if r_text and len(r_text) > 10 and r_text not in reviews:
            reviews.append(r_text)

    return CompetitorProductDetail(
        asin=asin,
        title=title,
        description=description,
        bullet_points=bullet_points,
        price=price,
        rating=rating,
        review_count=review_count,
        reviews=reviews,
        product_url=product_url or f"https://www.amazon.in/dp/{asin}",
    )


def fetch_competitor_details_batch(
    competitors: List[Dict[str, Any]],
    delay_seconds: float = 1.0,
    headless: Optional[bool] = None,
) -> List[CompetitorProductDetail]:
    """Fetch product details for a list of competitor dictionaries containing 'asin' and optional 'product_url'."""
    if not competitors:
        return []

    if headless is None:
        headless = os.getenv("HEADLESS", "true").lower() == "true"

    detailed_results: List[CompetitorProductDetail] = []

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=headless)
        context = browser.new_context(
            user_agent=DEFAULT_USER_AGENT,
            locale="en-IN",
            viewport={"width": 1366, "height": 900},
            extra_http_headers={
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
                "Accept-Language": "en-IN,en;q=0.9",
            },
        )
        page = context.new_page()
        page.set_default_timeout(25000)

        for comp in competitors:
            asin = comp.get("asin")
            if not asin:
                continue

            url = comp.get("product_url") or f"https://www.amazon.in/dp/{asin}"

            try:
                page.goto(url, wait_until="domcontentloaded", timeout=25000)
                page.wait_for_timeout(1000)

                detail = extract_details_from_page(page, asin, url)

                # Fall back to card title/price/rating if page missing them
                if not detail.title and comp.get("title"):
                    detail.title = comp.get("title")
                if not detail.price and comp.get("price"):
                    detail.price = comp.get("price")
                if detail.rating is None and comp.get("rating"):
                    detail.rating = comp.get("rating")
                if detail.review_count is None and comp.get("review_count"):
                    detail.review_count = comp.get("review_count")

                detailed_results.append(detail)
            except Exception as exc:
                fallback_detail = CompetitorProductDetail(
                    asin=asin,
                    title=comp.get("title") or f"Product {asin}",
                    description="",
                    bullet_points=[],
                    price=comp.get("price"),
                    rating=comp.get("rating"),
                    review_count=comp.get("review_count"),
                    reviews=[],
                    product_url=url,
                )
                detailed_results.append(fallback_detail)

            if delay_seconds > 0:
                time.sleep(delay_seconds)

        context.close()
        browser.close()

    return detailed_results
