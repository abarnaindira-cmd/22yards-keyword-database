import sys
import time
import re
import html
import urllib.parse
from typing import List
from playwright.sync_api import sync_playwright

sys.path.insert(0, r'd:\22yards_keyword_database')

from app.database import SessionLocal
from app.models.product import Product
from app.models.keyword import Keyword
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

def fetch_amazon_serp_titles(seed: str, browser) -> List[str]:
    """
    Fetch product titles from Amazon search result cards using Playwright.
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
        context.set_default_timeout(20000)
        page = context.new_page()

        page.goto(url, wait_until="domcontentloaded")
        page.wait_for_timeout(2500)

        item_locators = page.locator("div[data-component-type='s-search-result']").all()

        titles = []
        for item in item_locators:
            heading = item.locator("h2").first
            title_text = ""
            if heading.count() > 0:
                title_text = heading.inner_text().strip()

            if not title_text:
                span_title = item.locator("span.a-size-base-plus, span.a-size-medium").first
                if span_title.count() > 0:
                    title_text = span_title.inner_text().strip()

            if title_text:
                title_clean = " ".join(title_text.split())
                if title_clean and not title_clean.lower().startswith("results") and not title_clean.lower().startswith("1-48"):
                    titles.append(title_clean)

        return titles

    except Exception as e:
        print(f"  [Playwright Warning] Search failed for '{seed}': {e}", flush=True)
        return []
    finally:
        if context:
            context.close()

def main():
    db = SessionLocal()
    try:
        # Target ONLY failed products
        failed_products = db.query(Product).filter(Product.status == "failed").all()
        total_failed_before = len(failed_products)
        
        all_products_count = db.query(Product).count()
        completed_products_count = db.query(Product).filter(Product.status == "completed").count()
        initial_keywords_count = db.query(Keyword).count()

        print("=" * 80, flush=True)
        print("STARTING AMAZON SEARCH RESULTS FALLBACK FOR FAILED PRODUCTS", flush=True)
        print("=" * 80, flush=True)
        print(f"Total Products in DB            : {all_products_count}", flush=True)
        print(f"Completed Products              : {completed_products_count}", flush=True)
        print(f"Target Failed Products to Process: {total_failed_before}", flush=True)
        print(f"Existing Keywords in DB         : {initial_keywords_count}", flush=True)
        print("=" * 80, flush=True)

        processed_count = 0
        successful_count = 0
        still_failed_count = 0
        newly_inserted_keywords = 0
        products_with_data = 0
        products_no_data = 0
        error_count = 0

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)

            for idx, product in enumerate(failed_products, 1):
                try:
                    processed_count += 1
                    seeds = clean_product_title_to_seeds(product.product_name, product.category)
                    if not seeds:
                        seeds = [product.product_name]

                    all_candidates = []
                    for seed in seeds:
                        titles = fetch_amazon_serp_titles(seed, browser)
                        candidates = extract_keyword_candidates_from_titles(titles)
                        for c in candidates:
                            if c and c.lower() not in [x.lower() for x in all_candidates]:
                                all_candidates.append(c)

                    inserted_for_product = 0
                    for kw_text in all_candidates:
                        # Check duplicate for this product and source
                        existing = db.query(Keyword).filter(
                            Keyword.keyword == kw_text,
                            Keyword.source_product_asin == product.asin,
                            Keyword.source == "amazon_search_results"
                        ).first()

                        if not existing:
                            new_kw = Keyword(
                                keyword=kw_text,
                                source="amazon_search_results",
                                source_product_asin=product.asin,
                                category=product.category,
                                relevance_score=0.0
                            )
                            db.add(new_kw)
                            inserted_for_product += 1

                    if all_candidates and inserted_for_product > 0:
                        product.status = "completed"
                        successful_count += 1
                        products_with_data += 1
                        newly_inserted_keywords += inserted_for_product
                        db.commit()
                    elif all_candidates:
                        # Candidates extracted but already stored
                        product.status = "completed"
                        successful_count += 1
                        products_with_data += 1
                        db.commit()
                    else:
                        product.status = "failed"
                        still_failed_count += 1
                        products_no_data += 1
                        db.commit()

                    if idx % 10 == 0 or idx == total_failed_before:
                        print(
                            f"Processed {processed_count}/{total_failed_before} | "
                            f"Successful: {successful_count} | "
                            f"Still Failed: {still_failed_count} | "
                            f"New Keywords: {newly_inserted_keywords}",
                            flush=True
                        )

                except Exception as err:
                    db.rollback()
                    error_count += 1
                    product.status = "failed"
                    still_failed_count += 1
                    products_no_data += 1
                    try:
                        db.commit()
                    except Exception:
                        db.rollback()
                    print(f"[ERROR] Product ID {product.id} (ASIN: {product.asin}) failed: {err}", flush=True)

            browser.close()

        print("\n" + "=" * 80, flush=True)
        print("=== AMAZON SEARCH RESULTS FALLBACK COMPLETE ===", flush=True)
        print("=" * 80, flush=True)
        print(f"Total products processed         : {processed_count}", flush=True)
        print(f"Products successfully recovered  : {successful_count}", flush=True)
        print(f"Products still failed            : {still_failed_count}", flush=True)
        print(f"New keyword records inserted     : {newly_inserted_keywords}", flush=True)
        print(f"Products with Amazon Search data : {products_with_data}", flush=True)
        print(f"Products with no usable data     : {products_no_data}", flush=True)
        print("=" * 80 + "\n", flush=True)

        # Verification Queries
        total_products_db = db.query(Product).count()
        completed_products_db = db.query(Product).filter(Product.status == "completed").count()
        failed_products_db = db.query(Product).filter(Product.status == "failed").count()
        total_keywords_db = db.query(Keyword).count()

        distinct_asins_with_kw = set(r[0] for r in db.query(Keyword.source_product_asin).distinct().all())
        products_with_keywords_db = db.query(Product).filter(Product.asin.in_(distinct_asins_with_kw)).count()

        print("=" * 80, flush=True)
        print("MYSQL VERIFICATION REPORT", flush=True)
        print("=" * 80, flush=True)
        print(f"- total products                 : {total_products_db}", flush=True)
        print(f"- completed products             : {completed_products_db}", flush=True)
        print(f"- failed products                : {failed_products_db}", flush=True)
        print(f"- total keyword records          : {total_keywords_db}", flush=True)
        print(f"- products with keywords         : {products_with_keywords_db}", flush=True)
        print("=" * 80, flush=True)

    finally:
        db.close()

if __name__ == "__main__":
    main()
