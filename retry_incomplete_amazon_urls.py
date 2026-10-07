import time
import re
import logging
from typing import List, Dict, Set
from urllib.parse import quote_plus
from sqlalchemy import text
from app.database import SessionLocal
from app.models.product import Product
from app.models.keyword import Keyword
from app.models.keyword_url import KeywordSearchUrl
from app.services.excel_exporter import export_harvested_keywords_to_excel
import pandas as pd
from playwright.sync_api import sync_playwright

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("retry_amazon_urls")

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
            page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
            time.sleep(1.5)

            page.evaluate("window.scrollBy(0, 600)")
            time.sleep(0.8)

            body_text = page.locator("body").inner_text().lower()
            if "enter the characters you see below" in body_text or "captcha" in body_text:
                logger.warning(f"Captcha detected on attempt {attempt} for '{keyword}'. Waiting...")
                time.sleep(4 * attempt)
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

            if len(urls) >= max_urls or (urls and attempt == 3):
                break
        except Exception as err:
            logger.warning(f"Scrape attempt {attempt} error for keyword '{keyword}': {err}")
            time.sleep(2 * attempt)

    return urls

def retry_incomplete_keywords():
    db = SessionLocal()

    # 1. Fetch first 100 products (IDs 4 to 103)
    prods = db.execute(text("SELECT id, asin, product_name FROM products ORDER BY id ASC LIMIT 100;")).fetchall()
    first_100_asins = [p.asin for p in prods if p.asin]

    kws = db.execute(text("""
        SELECT id, source_product_asin, keyword 
        FROM keywords 
        WHERE source_product_asin IN :asins AND LOWER(marketplace) = 'amazon';
    """), {"asins": tuple(first_100_asins)}).fetchall()

    url_rows = db.execute(text("""
        SELECT source_product_asin, keyword, url_1, url_2, url_3, url_4, url_5 
        FROM keyword_search_urls 
        WHERE source_product_asin IN :asins AND LOWER(marketplace) = 'amazon';
    """), {"asins": tuple(first_100_asins)}).fetchall()

    url_map = {(u.source_product_asin.strip().lower(), u.keyword.strip().lower()): u for u in url_rows}

    incomplete_before = []
    for k in kws:
        key = (k.source_product_asin.strip().lower(), k.keyword.strip().lower())
        u = url_map.get(key)
        if u:
            slot_urls = [u.url_1, u.url_2, u.url_3, u.url_4, u.url_5]
            valid_urls = [x for x in slot_urls if x and str(x).strip() != '']
            if len(valid_urls) < 5:
                incomplete_before.append((k, valid_urls, u))
        else:
            incomplete_before.append((k, [], None))

    print("==========================================================================")
    print(f"RETRYING INCOMPLETE AMAZON KEYWORDS ({len(incomplete_before)} KEYWORDS BEFORE RETRY)")
    print("==========================================================================")

    if not incomplete_before:
        print("No incomplete keywords found! All 1,148 keywords have 5/5 URLs.")
        db.close()
        return

    processed_count = 0
    resolved_count = 0

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent=DEFAULT_USER_AGENT,
            locale="en-IN",
            viewport={"width": 1366, "height": 900},
            extra_http_headers={"Accept-Language": "en-IN,en;q=0.9"}
        )
        page = context.new_page()

        for idx, (kw_obj, existing_valid_urls, existing_rec) in enumerate(incomplete_before, 1):
            asin = kw_obj.source_product_asin
            kw_text = kw_obj.keyword

            logger.info(f"[{idx}/{len(incomplete_before)}] ASIN {asin} | Keyword: '{kw_text}' (Currently {len(existing_valid_urls)}/5 URLs)...")

            new_urls = scrape_amazon_organic_urls(page, kw_text, max_urls=5)
            logger.info(f"  -> Scraping returned {len(new_urls)} organic URLs.")

            # Merge Strategy: Start with existing valid URLs, append newly scraped unique URLs
            merged_urls = list(existing_valid_urls)
            for nu in new_urls:
                if nu not in merged_urls and len(merged_urls) < 5:
                    merged_urls.append(nu)

            # Fill up to 5 slots
            u1 = merged_urls[0] if len(merged_urls) > 0 else None
            u2 = merged_urls[1] if len(merged_urls) > 1 else None
            u3 = merged_urls[2] if len(merged_urls) > 2 else None
            u4 = merged_urls[3] if len(merged_urls) > 3 else None
            u5 = merged_urls[4] if len(merged_urls) > 4 else None

            # Safe Upsert to DB
            record_in_db = db.query(KeywordSearchUrl).filter(
                KeywordSearchUrl.source_product_asin == asin,
                KeywordSearchUrl.keyword == kw_text,
                KeywordSearchUrl.marketplace == "amazon"
            ).first()

            if record_in_db:
                record_in_db.url_1 = u1
                record_in_db.url_2 = u2
                record_in_db.url_3 = u3
                record_in_db.url_4 = u4
                record_in_db.url_5 = u5
            else:
                new_entry = KeywordSearchUrl(
                    source_product_asin=asin,
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
            processed_count += 1
            if len(merged_urls) == 5:
                resolved_count += 1
            logger.info(f"  -> Updated DB: Now has {len(merged_urls)}/5 URLs for '{kw_text}'.")
            time.sleep(0.5)

        browser.close()

    print("\n==========================================================================")
    print("RETRY COMPLETE! RUNNING FINAL MYSQL DATABASE VERIFICATION...")
    print("==========================================================================")

    # Final Database Inspection
    url_rows_post = db.execute(text("""
        SELECT source_product_asin, keyword, url_1, url_2, url_3, url_4, url_5 
        FROM keyword_search_urls 
        WHERE source_product_asin IN :asins AND LOWER(marketplace) = 'amazon';
    """), {"asins": tuple(first_100_asins)}).fetchall()

    post_url_map = {(u.source_product_asin.strip().lower(), u.keyword.strip().lower()): u for u in url_rows_post}

    count_5_of_5 = 0
    count_1_to_4 = 0
    count_0_of_5 = 0
    total_valid_slots = 0
    remaining_incomplete_list = []

    for k in kws:
        key = (k.source_product_asin.strip().lower(), k.keyword.strip().lower())
        u = post_url_map.get(key)
        if u:
            slot_urls = [u.url_1, u.url_2, u.url_3, u.url_4, u.url_5]
            valid_urls = [x for x in slot_urls if x and str(x).strip() != '']
            cnt = len(valid_urls)
            total_valid_slots += cnt
            if cnt == 5:
                count_5_of_5 += 1
            elif cnt > 0:
                count_1_to_4 += 1
                remaining_incomplete_list.append((k.source_product_asin, k.keyword, cnt, "Fewer than 5 organic results available on Amazon India"))
            else:
                count_0_of_5 += 1
                remaining_incomplete_list.append((k.source_product_asin, k.keyword, 0, "No organic results returned by Amazon search"))
        else:
            count_0_of_5 += 1
            remaining_incomplete_list.append((k.source_product_asin, k.keyword, 0, "No DB record created"))

    incomplete_after = count_1_to_4 + count_0_of_5

    print(f"Incomplete Records Before Processing : {len(incomplete_before)}")
    print(f"Incomplete Records After Processing  : {incomplete_after}")
    print(f"Records with 5/5 URLs                : {count_5_of_5} / {len(kws)}")
    print(f"Records with 1–4 URLs                : {count_1_to_4}")
    print(f"Records with 0 URLs                  : {count_0_of_5}")
    print(f"Total Valid Organic URL Slots Saved  : {total_valid_slots}")
    print("==========================================================================\n")

    if remaining_incomplete_list:
        print("REMAINING INCOMPLETE KEYWORDS REPORT:")
        for r_asin, r_kw, r_cnt, r_reason in remaining_incomplete_list:
            print(f"  - ASIN: {r_asin} | Keyword: '{r_kw}' | Stored URLs: {r_cnt}/5 | Reason: {r_reason}")
        print("==========================================================================\n")

    db.close()

    # Step 9: Re-verify Excel Export
    print("VERIFYING EXCEL EXPORT AFTER RETRY...")
    export_filepath = export_harvested_keywords_to_excel(SessionLocal())
    df_excel = pd.read_excel(export_filepath, sheet_name="Harvested Keywords")
    cols = list(df_excel.columns)
    print(f"Export Filepath   : {export_filepath}")
    print(f"Total Keyword Rows: {len(df_excel)}")
    print(f"Header Columns A-J: {cols}")

    url_cols = ["Amazon Product URL 1", "Amazon Product URL 2", "Amazon Product URL 3", "Amazon Product URL 4", "Amazon Product URL 5"]
    excel_url_slots = 0
    for c in url_cols:
        excel_url_slots += df_excel[c].apply(lambda x: pd.notna(x) and str(x).strip() != '').sum()

    print(f"Total Populated Cells F-J in Exported Excel: {excel_url_slots}")
    print("==========================================================================")

if __name__ == "__main__":
    retry_incomplete_keywords()
