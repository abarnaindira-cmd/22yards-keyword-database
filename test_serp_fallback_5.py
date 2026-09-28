import sys
import re
import html
import urllib.parse
from typing import List, Dict, Any, Tuple
from playwright.sync_api import sync_playwright

sys.path.insert(0, r'd:\22yards_keyword_database')

from app.database import SessionLocal
from app.models.product import Product
from app.services.keyword_collector import clean_product_title_to_seeds, DEFAULT_USER_AGENT

def extract_keyword_candidates_from_titles(titles: List[str]) -> List[str]:
    """
    Extract meaningful multi-word keyword phrases from Amazon Search Result product titles.
    1. Unescapes HTML entities.
    2. Strips noise tags, brackets, and parenthesized specs.
    3. Splits on clause delimiters (commas, dashes, slashes, pipes).
    4. Filters out noise phrases and deduplicates case-insensitively.
    """
    candidates = []
    stop_phrases = {"results", "sponsored", "featured from our brands", "check each product page", "best seller"}

    for raw_title in titles:
        t = html.unescape(raw_title)
        t = re.sub(r'\(.*?\)', ' ', t)
        t = re.sub(r'\[.*?\]', ' ', t)

        parts = re.split(r'[,|/\-\\]', t)

        for p in parts:
            p_clean = re.sub(r'[^\w\s]', ' ', p)
            p_clean = re.sub(r'\s+', ' ', p_clean).strip()

            if not p_clean or p_clean.lower() in stop_phrases:
                continue

            words = p_clean.split()
            if 2 <= len(words) <= 5:
                if not all(w.isdigit() for w in words):
                    if p_clean.lower() not in [c.lower() for c in candidates]:
                        candidates.append(p_clean)

    return candidates

def fetch_amazon_serp_data(seed: str, target_asin: str, browser) -> Tuple[bool, List[str], List[str], str]:
    """
    Fetch product titles and ASINs from Amazon search result cards using Playwright.
    Returns: (page_loaded: bool, titles: List[str], asins: List[str], error: str)
    """
    encoded_seed = urllib.parse.quote_plus(seed)
    url = f"https://www.amazon.in/s?k={encoded_seed}"

    context = None
    try:
        context = browser.new_context(
            user_agent=DEFAULT_USER_AGENT,
            locale="en-IN",
            viewport={"width": 1366, "height": 900},
            extra_http_headers={"Accept-Language": "en-US,en;q=0.9,en-IN;q=0.8"}
        )
        context.set_default_timeout(25000)
        page = context.new_page()

        page.goto(url, wait_until="domcontentloaded")
        page.wait_for_timeout(3000)

        # Locate search result item containers
        item_locators = page.locator("div[data-component-type='s-search-result']").all()

        titles = []
        asins = []

        for item in item_locators:
            asin_val = item.get_attribute("data-asin")
            if asin_val:
                asin_val = asin_val.strip()

            # Extract title from within the item container
            heading = item.locator("h2").first
            title_text = ""
            if heading.count() > 0:
                title_text = heading.inner_text().strip()

            if not title_text:
                span_title = item.locator("span.a-size-base-plus, span.a-size-medium").first
                if span_title.count() > 0:
                    title_text = span_title.inner_text().strip()

            if title_text:
                # Clean up newlines from title
                title_clean = " ".join(title_text.split())
                titles.append(title_clean)
                if asin_val and asin_val != target_asin:
                    if asin_val not in asins:
                        asins.append(asin_val)

        return True, titles, asins, ""

    except Exception as e:
        return False, [], [], str(e)
    finally:
        if context:
            context.close()

def main():
    db = SessionLocal()
    try:
        all_failed = db.query(Product).filter(Product.status == "failed").all()

        # Pick 5 distinct failed products
        seen_names = set()
        test_products = []
        for p in all_failed:
            if p.product_name not in seen_names:
                seen_names.add(p.product_name)
                test_products.append(p)
            if len(test_products) == 5:
                break

        print("=" * 85)
        print("READ-ONLY PROTOTYPE: 5-PRODUCT AMAZON SERP FALLBACK TEST")
        print("=" * 85 + "\n")

        successful_searches = 0
        failed_searches = 0
        total_results_extracted = 0
        total_keywords_extracted = 0

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)

            for idx, prod in enumerate(test_products, 1):
                seeds = clean_product_title_to_seeds(prod.product_name, prod.category)
                seed = seeds[0] if seeds else prod.product_name
                search_url = f"https://www.amazon.in/s?k={urllib.parse.quote_plus(seed)}"

                page_loaded, titles, asins, err = fetch_amazon_serp_data(seed, prod.asin, browser)
                candidates = extract_keyword_candidates_from_titles(titles) if titles else []

                if page_loaded and titles:
                    successful_searches += 1
                    total_results_extracted += len(titles)
                    total_keywords_extracted += len(candidates)
                else:
                    failed_searches += 1

                print(f"Product ID: {prod.id}")
                print(f"Product Name: {prod.product_name}")
                print(f"Category: {prod.category}")
                print(f"Target ASIN: {prod.asin}")
                print(f"Generated Seeds: {seeds}")
                print(f"Amazon Search URL: {search_url}")
                print(f"Search Page Loaded: {'Yes' if page_loaded else 'No'}")
                print(f"Search Results Found: {len(titles)}")
                print(f"Extracted Product Titles ({len(titles)}): {titles[:3]}")
                print(f"Extracted ASINs ({len(asins)}): {asins[:5]}")
                print(f"Keyword Candidates ({len(candidates)}): {candidates[:5]}")
                print(f"Errors, if any: {err if err else 'None'}")
                print("-" * 85 + "\n")

            browser.close()

        print("=== FALLBACK TEST SUMMARY ===")
        print(f"Products Tested: {len(test_products)}")
        print(f"Amazon Search Successful: {successful_searches}")
        print(f"Amazon Search Failed: {failed_searches}")
        print(f"Total Product Results Extracted: {total_results_extracted}")
        print(f"Total Keyword Candidates Extracted: {total_keywords_extracted}")
        print("=" * 85)

    finally:
        db.close()

if __name__ == "__main__":
    main()
