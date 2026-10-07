import sys
import os
import time
import re
from urllib.parse import quote_plus
import pandas as pd
import openpyxl

sys.path.insert(0, r"d:\22yards_keyword_database_competitor_ready\22yards_keyword_database")

from playwright.sync_api import sync_playwright
from app.database import SessionLocal
from app.models.product import Product
from app.models.keyword import Keyword

DEFAULT_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"

def is_sponsored_card(card):
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

def collect_amazon_urls_for_keyword(page, keyword, max_urls=5):
    urls = []
    seen_asins = set()

    url = f"https://www.amazon.in/s?k={quote_plus(keyword.strip())}"
    for attempt in range(1, 4):
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            time.sleep(2)

            page.evaluate("window.scrollBy(0, 800)")
            time.sleep(1)
            page.evaluate("window.scrollBy(0, 800)")
            time.sleep(1)

            body_text = page.locator("body").inner_text().lower()
            if "enter the characters you see below" in body_text or "captcha" in body_text:
                time.sleep(3 * attempt)
                continue

            cards = page.locator('div[data-asin]:not([data-asin=""])')
            count = cards.count()

            for i in range(count):
                card = cards.nth(i)
                asin = (card.get_attribute("data-asin") or "").strip()

                if not asin or len(asin) != 10 or not re.match(r'^[A-Z0-9]{10}$', asin):
                    continue

                if is_sponsored_card(card):
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
            time.sleep(2 * attempt)

    return urls

def main():
    db = SessionLocal()
    target_asin = "T2YVIVA000017"
    prod = db.query(Product).filter(Product.asin == target_asin).first()
    if not prod:
        print(f"Error: Product {target_asin} not found in database.")
        db.close()
        return

    keywords = db.query(Keyword).filter(Keyword.source_product_asin == target_asin).all()

    print("=" * 90)
    print(f" RUNNING ONE-PRODUCT AMAZON KEYWORD URL TEST FOR: {target_asin}")
    print(f" Product Name: {prod.product_name}")
    print(f" Category:     {prod.category}")
    print(f" Keywords:     {len(keywords)} total harvested keywords")
    print("=" * 90 + "\n")

    report_rows = []
    total_urls_collected = 0
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
            found_urls = collect_amazon_urls_for_keyword(page, kw_text, max_urls=5)
            cnt = len(found_urls)
            total_urls_collected += cnt

            if cnt == 0:
                failed_keywords.append(kw_text)

            u1 = found_urls[0] if len(found_urls) > 0 else ""
            u2 = found_urls[1] if len(found_urls) > 1 else ""
            u3 = found_urls[2] if len(found_urls) > 2 else ""
            u4 = found_urls[3] if len(found_urls) > 3 else ""
            u5 = found_urls[4] if len(found_urls) > 4 else ""

            row_data = {
                "Source Product ASIN": prod.asin,
                "Source Product Name": prod.product_name,
                "Keyword Phrase": kw_text,
                "Source": kw_obj.source or "search_suggestions",
                "Relevance": kw_obj.relevance_score if kw_obj.relevance_score is not None else 0.0,
                "Amazon Product URL 1": u1,
                "Amazon Product URL 2": u2,
                "Amazon Product URL 3": u3,
                "Amazon Product URL 4": u4,
                "Amazon Product URL 5": u5,
            }
            report_rows.append(row_data)

            print(f"[{idx:2d}/10] Keyword Searched: '{kw_text}'")
            print(f"       Valid URLs Found: {cnt}")
            for u_idx, u in enumerate(found_urls, 1):
                print(f"         URL {u_idx}: {u}")
            print("-" * 90)

        browser.close()

    # Generate Excel Report
    df_report = pd.DataFrame(report_rows)
    excel_path = os.path.join(r"d:\22yards_keyword_database_competitor_ready\22yards_keyword_database", "T2YVIVA000017_Harvested_Keywords_Report.xlsx")
    
    with pd.ExcelWriter(excel_path, engine="openpyxl") as writer:
        df_report.to_excel(writer, sheet_name="Harvested Keywords", index=False)

    print("\n" + "=" * 90)
    print(" ONE-PRODUCT TEST COMPLETION REPORT (T2YVIVA000017)")
    print("=" * 90)
    print(f"- Total Keywords Processed:      {len(keywords)}")
    print(f"- Total Valid URLs Collected:    {total_urls_collected}")
    print(f"- Failed Keywords Count:         {len(failed_keywords)}")
    if failed_keywords:
        print(f"- Failed Keywords List:          {failed_keywords}")
    print(f"- Excel Report Generated:        {excel_path}")
    print("=" * 90 + "\n")

    db.close()

if __name__ == "__main__":
    main()
