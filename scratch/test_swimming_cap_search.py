import time
import re
from urllib.parse import quote_plus
from playwright.sync_api import sync_playwright

DEFAULT_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"

def test_amazon_swimming_cap():
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
        
        print(f"Navigating to {search_url} ...")
        page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
        time.sleep(2)
        
        # Scroll to ensure images and lazy items load
        page.evaluate("window.scrollBy(0, 600)")
        time.sleep(1)
        
        # Check body for captcha
        body_text = page.locator("body").inner_text().lower()
        if "enter the characters you see below" in body_text or "captcha" in body_text:
            print("CAPTCHA detected!")
            browser.close()
            return
            
        print("\n--- Inspecting Product Cards in DOM Displayed Order ---")
        
        # Let's inspect div[data-component-type="s-search-result"] vs div[data-asin]
        cards = page.locator('div[data-component-type="s-search-result"]')
        count = cards.count()
        print(f"Found {count} search result cards via div[data-component-type='s-search-result']")
        
        extracted = []
        seen_asins = set()
        
        for i in range(count):
            card = cards.nth(i)
            asin = (card.get_attribute("data-asin") or "").strip()
            
            if not asin or len(asin) != 10 or not re.match(r'^[A-Z0-9]{10}$', asin):
                continue
                
            # Check title
            title_el = card.locator('h2 a span, h2 span, a.a-link-normal span.a-text-normal')
            title = title_el.first.inner_text().strip() if title_el.count() > 0 else "N/A"
            
            # Check link / URL
            link_el = card.locator('h2 a, a.a-link-normal[href*="/dp/"], a.a-link-normal[href*="/gp/product/"]')
            raw_href = link_el.first.get_attribute("href") if link_el.count() > 0 else ""
            
            # Is sponsored?
            html_lower = card.inner_html().lower()
            is_sponsored = "sponsored" in html_lower or "promoted" in html_lower
            
            clean_url = f"https://www.amazon.in/dp/{asin}"
            
            if asin not in seen_asins:
                seen_asins.add(asin)
                extracted.append({
                    "rank": len(extracted) + 1,
                    "asin": asin,
                    "title": title,
                    "clean_url": clean_url,
                    "raw_href": raw_href[:80] if raw_href else "N/A",
                    "sponsored": is_sponsored
                })
                
            if len(extracted) >= 5:
                break
                
        print(f"\nExtracted First 5 Cards for '{keyword}':")
        for item in extracted:
            print(f"#{item['rank']}: ASIN={item['asin']} | Sponsored={item['sponsored']}")
            print(f"    Title: {item['title'][:60]}")
            print(f"    Clean URL: {item['clean_url']}")
            print(f"    Raw Href: {item['raw_href']}")
            print()

        browser.close()

if __name__ == "__main__":
    test_amazon_swimming_cap()
