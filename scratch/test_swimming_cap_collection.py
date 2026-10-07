import time
import re
from urllib.parse import quote_plus
from sqlalchemy import text
from app.database import SessionLocal
from app.models.keyword_url import KeywordSearchUrl
from playwright.sync_api import sync_playwright

DEFAULT_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"

def scrape_amazon_top5_urls(page, keyword: str) -> list:
    urls = []
    seen_asins = set()
    search_url = f"https://www.amazon.in/s?k={quote_plus(keyword.strip())}"

    for attempt in range(1, 4):
        try:
            page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
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

                if len(urls) >= 5:
                    break

            if urls:
                break
        except Exception as err:
            time.sleep(2 * attempt)

    return urls

def test_swimming_cap_step6():
    db = SessionLocal()
    keyword = "swimming cap"
    
    print("==========================================================================")
    print("STEP 6: TESTING URL COLLECTION FOR KEYWORD 'swimming cap'")
    print("==========================================================================")

    # Fetch existing stored URLs for swimming cap
    existing_records = db.execute(text("""
        SELECT id, source_product_asin, keyword, url_1, url_2, url_3, url_4, url_5 
        FROM keyword_search_urls 
        WHERE keyword = :kw AND LOWER(marketplace) = 'amazon';
    """), {"kw": keyword}).fetchall()

    print(f"Found {len(existing_records)} existing DB record(s) for '{keyword}':")
    for r in existing_records:
        print(f"  ASIN: {r.source_product_asin} | URL1: {r.url_1} | URL2: {r.url_2} | URL3: {r.url_3} | URL4: {r.url_4} | URL5: {r.url_5}")

    # Scrape actual top 5 displayed search results from Amazon India
    print("\nNavigating to Amazon India to extract top 5 displayed product cards (including sponsored)...")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent=DEFAULT_USER_AGENT,
            locale="en-IN",
            viewport={"width": 1366, "height": 900},
            extra_http_headers={"Accept-Language": "en-IN,en;q=0.9"}
        )
        page = context.new_page()
        top5_urls = scrape_amazon_top5_urls(page, keyword)
        browser.close()

    print(f"\nExtracted Actual Top 5 Displayed Amazon URLs for '{keyword}':")
    for idx, u in enumerate(top5_urls, 1):
        print(f"  URL {idx}: {u}")

    assert len(top5_urls) == 5, f"Expected 5 URLs, got {len(top5_urls)}"

    # Update DB for swimming cap
    print("\nUpdating DB records for 'swimming cap' with newly extracted displayed URLs...")
    for r in existing_records:
        db.execute(text("""
            UPDATE keyword_search_urls 
            SET url_1 = :u1, url_2 = :u2, url_3 = :u3, url_4 = :u4, url_5 = :u5 
            WHERE id = :id;
        """), {
            "id": r.id,
            "u1": top5_urls[0],
            "u2": top5_urls[1],
            "u3": top5_urls[2],
            "u4": top5_urls[3],
            "u5": top5_urls[4]
        })
    db.commit()

    # Re-verify DB values
    updated_records = db.execute(text("""
        SELECT id, source_product_asin, keyword, url_1, url_2, url_3, url_4, url_5 
        FROM keyword_search_urls 
        WHERE keyword = :kw AND LOWER(marketplace) = 'amazon';
    """), {"kw": keyword}).fetchall()

    print("\nVerified Updated DB Records for 'swimming cap':")
    for r in updated_records:
        print(f"  ASIN: {r.source_product_asin}")
        print(f"    url_1: {r.url_1}")
        print(f"    url_2: {r.url_2}")
        print(f"    url_3: {r.url_3}")
        print(f"    url_4: {r.url_4}")
        print(f"    url_5: {r.url_5}")

    db.close()
    print("==========================================================================")
    print("STEP 6 TEST FOR 'swimming cap' PASSED 100% SUCCESSFULLY!")
    print("==========================================================================")

if __name__ == "__main__":
    test_swimming_cap_step6()
