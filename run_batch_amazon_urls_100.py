import time
import re
import logging
from typing import List
from urllib.parse import quote_plus
from sqlalchemy import text
from app.database import SessionLocal
from app.models.product import Product
from app.models.keyword import Keyword
from app.models.keyword_url import KeywordSearchUrl
from playwright.sync_api import sync_playwright

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("amazon_url_batch_100")

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
    search_url = f"https://www.amazon.in/s?k={quote_plus(keyword.strip())}"

    for attempt in range(1, 4):
        try:
            page.goto(search_url, wait_until="domcontentloaded", timeout=25000)
            time.sleep(1.2)

            page.evaluate("window.scrollBy(0, 600)")
            time.sleep(0.6)

            body_text = page.locator("body").inner_text().lower()
            if "enter the characters you see below" in body_text or "captcha" in body_text:
                logger.warning(f"Captcha detected on attempt {attempt} for '{keyword}'. Waiting...")
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
            logger.warning(f"Scrape attempt {attempt} error for keyword '{keyword}': {err}")
            time.sleep(2 * attempt)

    return urls

def run_batch_amazon_urls_100():
    db = SessionLocal()
    # Query products 1 to 100 (IDs 4 to 103)
    prods = db.query(Product).order_by(Product.id.asc()).limit(100).all()
    prod_asins = [p.asin for p in prods if p.asin]

    print("==========================================================================")
    print(f"STARTING BATCH AMAZON URL COLLECTION FOR PRODUCTS #1 TO #100 ({len(prods)} PRODUCTS)")
    print("==========================================================================")

    # Pre-fetch existing keyword search url records
    existing_urls = db.query(KeywordSearchUrl).filter(
        KeywordSearchUrl.source_product_asin.in_(prod_asins),
        KeywordSearchUrl.marketplace == "amazon"
    ).all()

    url_map = {}
    for u in existing_urls:
        key = (u.source_product_asin.strip().lower(), u.keyword.strip().lower())
        valid_urls = [x for x in [u.url_1, u.url_2, u.url_3, u.url_4, u.url_5] if x and str(x).strip() != '']
        url_map[key] = (u, valid_urls)

    # Collect all keywords for the 100 products
    all_kws = db.query(Keyword).filter(
        Keyword.source_product_asin.in_(prod_asins),
        Keyword.marketplace == "amazon"
    ).all()

    pending_keywords = []
    skipped_keywords = []

    for k in all_kws:
        key = (k.source_product_asin.strip().lower(), k.keyword.strip().lower())
        if key in url_map and len(url_map[key][1]) == 5:
            skipped_keywords.append(k)
        else:
            pending_keywords.append(k)

    print(f"Total Harvested Keywords Found : {len(all_kws)}")
    print(f"Already Completed (5 URLs)    : {len(skipped_keywords)} (Skipping)")
    print(f"Pending Keywords to Process    : {len(pending_keywords)}")
    print("==========================================================================\n")

    if not pending_keywords:
        print("All 100 products keywords already have 5 valid Amazon URLs! Nothing to do.")
        db.close()
        return

    processed_count = 0
    successful_count = 0
    failed_count = 0
    new_urls_collected = 0

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent=DEFAULT_USER_AGENT,
            locale="en-IN",
            viewport={"width": 1366, "height": 900},
            extra_http_headers={"Accept-Language": "en-IN,en;q=0.9"}
        )
        page = context.new_page()

        for idx, kw in enumerate(pending_keywords, 1):
            asin = kw.source_product_asin
            kw_text = kw.keyword

            logger.info(f"[{idx}/{len(pending_keywords)}] ASIN {asin} | Keyword: '{kw_text}' ...")

            urls = scrape_amazon_organic_urls(page, kw_text, max_urls=5)
            cnt = len(urls)
            processed_count += 1

            if cnt > 0:
                successful_count += 1
                new_urls_collected += cnt
            else:
                failed_count += 1

            u1 = urls[0] if len(urls) > 0 else None
            u2 = urls[1] if len(urls) > 1 else None
            u3 = urls[2] if len(urls) > 2 else None
            u4 = urls[3] if len(urls) > 3 else None
            u5 = urls[4] if len(urls) > 4 else None

            # Safe Upsert
            existing_rec = db.query(KeywordSearchUrl).filter(
                KeywordSearchUrl.source_product_asin == asin,
                KeywordSearchUrl.keyword == kw_text,
                KeywordSearchUrl.marketplace == "amazon"
            ).first()

            if existing_rec:
                if u1: existing_rec.url_1 = u1
                if u2: existing_rec.url_2 = u2
                if u3: existing_rec.url_3 = u3
                if u4: existing_rec.url_4 = u4
                if u5: existing_rec.url_5 = u5
            else:
                new_rec = KeywordSearchUrl(
                    source_product_asin=asin,
                    keyword=kw_text,
                    url_1=u1,
                    url_2=u2,
                    url_3=u3,
                    url_4=u4,
                    url_5=u5,
                    marketplace="amazon"
                )
                db.add(new_rec)

            db.commit()
            logger.info(f"  -> Saved {cnt}/5 URLs for '{kw_text}'.")
            time.sleep(0.3)

        browser.close()

    print("\n==========================================================================")
    print("BATCH RUN COMPLETE! RUNNING FINAL MYSQL DATABASE VERIFICATION...")
    print("==========================================================================")

    # Post-run verification
    url_rows_post = db.query(KeywordSearchUrl).filter(
        KeywordSearchUrl.source_product_asin.in_(prod_asins),
        KeywordSearchUrl.marketplace == "amazon"
    ).all()

    total_populated_slots = 0
    completed_5_urls_kw = 0
    partial_or_0_urls_kw = 0

    for u in url_rows_post:
        valid_u = [x for x in [u.url_1, u.url_2, u.url_3, u.url_4, u.url_5] if x and str(x).strip() != '']
        total_populated_slots += len(valid_u)
        if len(valid_u) == 5:
            completed_5_urls_kw += 1
        else:
            partial_or_0_urls_kw += 1

    remaining_pending = len(all_kws) - completed_5_urls_kw

    print(f"Products Processed          : {len(prods)}")
    print(f"Keywords Processed in Run   : {processed_count}")
    print(f"Keywords Successfully Found : {successful_count}")
    print(f"Keywords Failed (0 URLs)    : {failed_count}")
    print(f"Keywords With 5/5 URLs      : {completed_5_urls_kw} / {len(all_kws)}")
    print(f"Keywords Remaining Pending  : {remaining_pending}")
    print(f"Total URL Slots Populated   : {total_populated_slots}")
    print("==========================================================================")

    db.close()

if __name__ == "__main__":
    run_batch_amazon_urls_100()
