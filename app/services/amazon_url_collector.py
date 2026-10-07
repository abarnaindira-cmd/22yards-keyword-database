import os
import time
import re
import logging
from typing import List, Dict, Any, Optional
from urllib.parse import quote_plus
from sqlalchemy.orm import Session

from playwright.sync_api import sync_playwright
from app.models.product import Product
from app.models.keyword import Keyword
from app.models.keyword_url import KeywordSearchUrl

logger = logging.getLogger("amazon_url_collector")

DEFAULT_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"

def is_sponsored_card(card) -> bool:
    try:
        html = card.inner_html().lower()
        if "sponsored" in html or "promoted" in html:
            if (card.locator(".puis-sponsored-label-text").count() > 0 or
                card.locator(".s-sponsored-label-info-icon").count() > 0 or
                card.locator("span.a-color-base:has-text('Sponsored')").count() > 0 or
                card.locator("span:has-text('Sponsored')").count() > 0 or
                card.locator("span:has-text('Ad')").count() > 0 or
                card.locator("[aria-label*='Sponsored']").count() > 0):
                return True
    except Exception:
        pass
    return False

def scrape_amazon_organic_urls(page, keyword: str, max_urls: int = 5) -> List[str]:
    urls = []
    seen_asins = set()

    url = f"https://www.amazon.in/s?k={quote_plus(keyword.strip())}"
    for attempt in range(1, 4):
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            time.sleep(2)

            page.evaluate("window.scrollBy(0, 600)")
            time.sleep(1)

            body_text = page.locator("body").inner_text().lower()
            if "enter the characters you see below" in body_text or "captcha" in body_text:
                time.sleep(3 * attempt)
                continue

            cards = page.locator('div[data-component-type="s-search-result"]')
            if cards.count() == 0:
                cards = page.locator('div[data-asin]:not([data-asin=""])')

            count = cards.count()

            for i in range(count):
                card = cards.nth(i)
                asin = (card.get_attribute("data-asin") or "").strip()

                if not asin or len(asin) != 10 or not re.match(r'^[A-Z0-9]{10}$', asin):
                    continue

                if asin not in seen_asins:
                    seen_asins.add(asin)
                    clean_url = f"https://www.amazon.in/dp/{asin}"
                    urls.append(clean_url)

                if len(urls) >= max_urls:
                    break

            if urls:
                break
        except Exception as err:
            logger.warning(f"Amazon scrape attempt {attempt} error for keyword '{keyword}': {err}")
            time.sleep(2 * attempt)

    return urls

def process_amazon_urls_for_asin(db: Session, target_asin: str) -> Dict[str, Any]:
    prod = db.query(Product).filter(Product.asin == target_asin).first()
    if not prod:
        return {"error": f"Product with ASIN {target_asin} not found."}

    keywords = db.query(Keyword).filter(
        Keyword.source_product_asin == target_asin,
        Keyword.marketplace == "amazon"
    ).all()

    if not keywords:
        keywords = db.query(Keyword).filter(Keyword.source_product_asin == target_asin).all()

    results_details = []
    total_stored_urls = 0
    failed_keywords = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent=DEFAULT_USER_AGENT,
            locale="en-IN",
            viewport={"width": 1366, "height": 900},
            extra_http_headers={"Accept-Language": "en-IN,en;q=0.9"}
        )
        page = context.new_page()

        for idx, kw_obj in enumerate(keywords, 1):
            kw_text = kw_obj.keyword
            urls = scrape_amazon_organic_urls(page, kw_text, max_urls=5)
            cnt = len(urls)
            total_stored_urls += cnt

            if cnt == 0:
                failed_keywords.append(kw_text)

            u1 = urls[0] if len(urls) > 0 else None
            u2 = urls[1] if len(urls) > 1 else None
            u3 = urls[2] if len(urls) > 2 else None
            u4 = urls[3] if len(urls) > 3 else None
            u5 = urls[4] if len(urls) > 4 else None

            existing = db.query(KeywordSearchUrl).filter(
                KeywordSearchUrl.source_product_asin == target_asin,
                KeywordSearchUrl.keyword == kw_text,
                KeywordSearchUrl.marketplace == "amazon"
            ).first()

            if existing:
                existing.url_1 = u1
                existing.url_2 = u2
                existing.url_3 = u3
                existing.url_4 = u4
                existing.url_5 = u5
            else:
                new_entry = KeywordSearchUrl(
                    source_product_asin=target_asin,
                    keyword=kw_text,
                    url_1=u1,
                    url_2=u2,
                    url_3=u3,
                    url_4=u4,
                    url_5=u5,
                    marketplace="amazon"
                )
                db.add(new_entry)

            db.commit()

            results_details.append({
                "keyword": kw_text,
                "urls_found": cnt,
                "urls": urls
            })

        browser.close()

    return {
        "source_product_asin": target_asin,
        "product_name": prod.product_name,
        "total_keywords_processed": len(keywords),
        "total_urls_stored": total_stored_urls,
        "failed_keywords_count": len(failed_keywords),
        "failed_keywords": failed_keywords,
        "details": results_details
    }
