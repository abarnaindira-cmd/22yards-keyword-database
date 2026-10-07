import time
import re
from urllib.parse import quote_plus
from playwright.sync_api import sync_playwright

DEFAULT_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"

def test_selectors():
    keyword = "swimming cap"
    search_url = f"https://www.amazon.in/s?k={quote_plus(keyword)}"
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent=DEFAULT_USER_AGENT,
            locale="en-IN",
            viewport={"width": 1366, "height": 900},
            extra_http_headers={"Accept-Language": "en-IN,en;q=0.9"}
        )
        page = context.new_page()
        page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
        time.sleep(2)
        page.evaluate("window.scrollBy(0, 600)")
        time.sleep(1)

        print("=== Option A: div[data-component-type='s-search-result'] ===")
        cards_a = page.locator('div[data-component-type="s-search-result"]')
        seen_a = set()
        list_a = []
        for i in range(cards_a.count()):
            card = cards_a.nth(i)
            asin = (card.get_attribute("data-asin") or "").strip()
            if asin and len(asin) == 10 and re.match(r'^[A-Z0-9]{10}$', asin) and asin not in seen_a:
                seen_a.add(asin)
                list_a.append(asin)
                if len(list_a) >= 5:
                    break
        print("First 5 ASINs (Option A):", list_a)

        print("\n=== Option B: div[data-asin]:not([data-asin='']) ===")
        cards_b = page.locator('div[data-asin]:not([data-asin=""])')
        seen_b = set()
        list_b = []
        for i in range(cards_b.count()):
            card = cards_b.nth(i)
            asin = (card.get_attribute("data-asin") or "").strip()
            if asin and len(asin) == 10 and re.match(r'^[A-Z0-9]{10}$', asin) and asin not in seen_b:
                seen_b.add(asin)
                list_b.append(asin)
                if len(list_b) >= 5:
                    break
        print("First 5 ASINs (Option B):", list_b)

        browser.close()

if __name__ == "__main__":
    test_selectors()
