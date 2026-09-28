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
        # Step 1: Query MySQL for products WHERE status = 'failed'
        failed_products = db.query(Product).filter(Product.status == "failed").all()
        actual_failed_count = len(failed_products)

        # Requirement: First print exact count
        print(f"Confirmed failed products to process: {actual_failed_count}", flush=True)

        if actual_failed_count == 0:
            print("No failed products remaining in MySQL. All products are completed.", flush=True)
            return

        processed_count = 0
        successful_count = 0
        still_failed_count = 0
        newly_inserted_keywords = 0

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)

            for idx, product in enumerate(failed_products, 1):
                processed_count += 1
                seeds = clean_product_title_to_seeds(product.product_name, product.category)

                # Broader category seed fallback if primary seeds returned 0
                if product.category and product.category.lower() not in {"apparel", "shoe", "shoes"}:
                    cat_clean = re.sub(r'[^\w\s]', ' ', product.category).strip()
                    if cat_clean and cat_clean.lower() not in [s.lower() for s in seeds]:
                        seeds.append(cat_clean)

                all_candidates = []
                for seed in seeds:
                    titles = fetch_amazon_serp_titles(seed, browser)
                    candidates = extract_keyword_candidates_from_titles(titles)
                    for c in candidates:
                        if c and c.lower() not in [x.lower() for x in all_candidates]:
                            all_candidates.append(c)

                inserted_for_product = 0
                for kw_text in all_candidates:
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
                    newly_inserted_keywords += inserted_for_product
                    db.commit()
                elif all_candidates:
                    product.status = "completed"
                    successful_count += 1
                    db.commit()
                else:
                    product.status = "failed"
                    still_failed_count += 1
                    db.commit()

                print(
                    f"Processed {processed_count}/{actual_failed_count} | "
                    f"Successful: {successful_count} | "
                    f"Still Failed: {still_failed_count} | "
                    f"New Keywords: {newly_inserted_keywords}",
                    flush=True
                )

            browser.close()

        print("\n" + "=" * 80, flush=True)
        print("FINAL MYSQL VERIFICATION REPORT", flush=True)
        print("=" * 80, flush=True)
        total_products_db = db.query(Product).count()
        completed_products_db = db.query(Product).filter(Product.status == "completed").count()
        failed_products_db = db.query(Product).filter(Product.status == "failed").count()
        total_keywords_db = db.query(Keyword).count()
        distinct_asins_with_kw = set(r[0] for r in db.query(Keyword.source_product_asin).distinct().all())
        products_with_keywords_db = db.query(Product).filter(Product.asin.in_(distinct_asins_with_kw)).count()

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
