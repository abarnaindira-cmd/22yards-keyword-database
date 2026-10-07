import time
import re
from urllib.parse import quote_plus
from playwright.sync_api import sync_playwright

DEFAULT_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"

distinct_keywords = [
    'gym training shirts men',
    'swimming costume for girls 14-16',
    'shoe rack',
    'nike shoes men',
    'adidas shoes for women'
]

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

def scrape_test(page, keyword: str, max_urls: int = 5):
    urls = []
    seen_asins = set()
    search_url = f"https://www.amazon.in/s?k={quote_plus(keyword.strip())}"

    page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
    time.sleep(2)

    # Scroll deeper to load more organic search result cards
    for _ in range(4):
        page.evaluate("window.scrollBy(0, 1000)")
        time.sleep(0.8)

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

    return urls

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context(
        user_agent=DEFAULT_USER_AGENT,
        locale="en-IN",
        viewport={"width": 1366, "height": 900},
        extra_http_headers={"Accept-Language": "en-IN,en;q=0.9"}
    )
    page = context.new_page()

    print("==========================================================================")
    print("TESTING RETRY SCRAPING FOR INCOMPLETE KEYWORDS ON AMAZON INDIA")
    print("==========================================================================")

    for kw in distinct_keywords:
        urls = scrape_test(page, kw, max_urls=5)
        print(f"\nKeyword: '{kw}' | Organic URLs Found: {len(urls)}/5")
        for idx, u in enumerate(urls, 1):
            print(f"  URL {idx}: {u}")

    browser.close()
