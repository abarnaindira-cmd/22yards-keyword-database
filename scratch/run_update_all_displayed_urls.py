import time
import re
import logging
from urllib.parse import quote_plus
from sqlalchemy import text
from app.database import SessionLocal
from app.models.keyword_url import KeywordSearchUrl
from playwright.sync_api import sync_playwright

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("update_displayed_urls")

DEFAULT_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"

def scrape_amazon_top5_urls(page, keyword: str) -> list:
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

                if len(urls) >= 5:
                    break

            if urls:
                break
        except Exception as err:
            logger.warning(f"Scrape attempt {attempt} error for keyword '{keyword}': {err}")
            time.sleep(2 * attempt)

    return urls

def update_all_amazon_urls():
    db = SessionLocal()

    # 1. Fetch products 1 to 100 (IDs 4 to 103)
    prods = db.execute(text("SELECT id, asin, product_name FROM products ORDER BY id ASC LIMIT 100;")).fetchall()
    first_100_asins = [p.asin for p in prods if p.asin]

    # 2. Fetch all keyword records for these 100 products
    kws = db.execute(text("""
        SELECT DISTINCT keyword 
        FROM keywords 
        WHERE source_product_asin IN :asins AND LOWER(marketplace) = 'amazon'
        ORDER BY keyword ASC;
    """), {"asins": tuple(first_100_asins)}).fetchall()

    unique_keywords = [k.keyword for k in kws]
    logger.info(f"Total Unique Keyword Phrases to process across 100 products: {len(unique_keywords)}")

    kw_search_url_records = db.execute(text("""
        SELECT id, source_product_asin, keyword 
        FROM keyword_search_urls 
        WHERE source_product_asin IN :asins AND LOWER(marketplace) = 'amazon';
    """), {"asins": tuple(first_100_asins)}).fetchall()

    logger.info(f"Total `keyword_search_urls` DB records: {len(kw_search_url_records)}")

    kw_to_db_ids = {}
    for r in kw_search_url_records:
        kw_key = r.keyword.strip().lower()
        if kw_key not in kw_to_db_ids:
            kw_to_db_ids[kw_key] = []
        kw_to_db_ids[kw_key].append(r.id)

    corrected_keywords = 0
    failed_keywords = 0

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent=DEFAULT_USER_AGENT,
            locale="en-IN",
            viewport={"width": 1366, "height": 900},
            extra_http_headers={"Accept-Language": "en-IN,en;q=0.9"}
        )
        page = context.new_page()

        for idx, kw in enumerate(unique_keywords, 1):
            logger.info(f"[{idx}/{len(unique_keywords)}] Scraping top 5 displayed search results for: '{kw}'...")
            top5 = scrape_amazon_top5_urls(page, kw)

            if top5:
                u1 = top5[0] if len(top5) > 0 else None
                u2 = top5[1] if len(top5) > 1 else None
                u3 = top5[2] if len(top5) > 2 else None
                u4 = top5[3] if len(top5) > 3 else None
                u5 = top5[4] if len(top5) > 4 else None

                target_ids = kw_to_db_ids.get(kw.strip().lower(), [])
                for db_id in target_ids:
                    db.execute(text("""
                        UPDATE keyword_search_urls 
                        SET url_1 = :u1, url_2 = :u2, url_3 = :u3, url_4 = :u4, url_5 = :u5 
                        WHERE id = :id;
                    """), {"id": db_id, "u1": u1, "u2": u2, "u3": u3, "u4": u4, "u5": u5})
                db.commit()
                corrected_keywords += 1
                logger.info(f"  -> Updated DB records for '{kw}' with {len(top5)} displayed URLs.")
            else:
                failed_keywords += 1
                logger.warning(f"  -> Could not extract URLs for '{kw}'")

            time.sleep(0.3)

        browser.close()

    db.close()
    logger.info("FINISHED UPDATING ALL KEYWORD URL RECORDS!")

if __name__ == "__main__":
    update_all_amazon_urls()
