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
from app.services.keyword_collector import (
    clean_product_title_to_seeds,
    fetch_amazon_suggestions_api,
    DEFAULT_USER_AGENT
)

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
        # Target ONLY remaining failed products
        failed_products = db.query(Product).filter(Product.status == "failed").all()
        total_failed = len(failed_products)
        
        initial_completed = db.query(Product).filter(Product.status == "completed").count()
        initial_keywords = db.query(Keyword).count()

        print("=" * 80, flush=True)
        print(f"PROCESSING FINAL {total_failed} FAILED PRODUCTS WITH ENHANCED SEEDS", flush=True)
        print("=" * 80, flush=True)
        print(f"Target Failed Products  : {total_failed}", flush=True)
        print(f"Already Completed       : {initial_completed}", flush=True)
        print(f"Existing Keywords in DB : {initial_keywords}", flush=True)
        print("=" * 80, flush=True)

        processed_count = 0
        successful_count = 0
        still_failed_count = 0
        newly_inserted_keywords = 0

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)

            for idx, product in enumerate(failed_products, 1):
                processed_count += 1
                seeds = clean_product_title_to_seeds(product.product_name, product.category)

                collected_kws = []
                
                # 1. Try Autocomplete API with core product type seeds
                for seed in seeds:
                    suggs = fetch_amazon_suggestions_api(seed)
                    for s_text in suggs:
                        if s_text and s_text.lower() not in [x[0].lower() for x in collected_kws]:
                            collected_kws.append((s_text, "search_suggestions"))

                # 2. Fallback to SERP scraping if autocomplete yielded < 3 keywords
                if len(collected_kws) < 3 and seeds:
                    primary_seed = seeds[0]
                    serp_titles = fetch_amazon_serp_titles(primary_seed, browser)
                    serp_candidates = extract_keyword_candidates_from_titles(serp_titles)
                    for c_text in serp_candidates:
                        if c_text and c_text.lower() not in [x[0].lower() for x in collected_kws]:
                            collected_kws.append((c_text, "amazon_search_results"))

                inserted_for_product = 0
                for kw_text, src in collected_kws:
                    existing = db.query(Keyword).filter(
                        Keyword.keyword == kw_text,
                        Keyword.source_product_asin == product.asin,
                        Keyword.source == src
                    ).first()

                    if not existing:
                        new_kw = Keyword(
                            keyword=kw_text,
                            source=src,
                            source_product_asin=product.asin,
                            category=product.category,
                            relevance_score=0.0
                        )
                        db.add(new_kw)
                        inserted_for_product += 1

                if collected_kws and inserted_for_product > 0:
                    product.status = "completed"
                    successful_count += 1
                    newly_inserted_keywords += inserted_for_product
                    db.commit()
                elif collected_kws:
                    product.status = "completed"
                    successful_count += 1
                    db.commit()
                else:
                    product.status = "failed"
                    still_failed_count += 1
                    db.commit()

                print(
                    f"Processed {processed_count}/{total_failed} | "
                    f"Successful: {successful_count} | "
                    f"Still Failed: {still_failed_count} | "
                    f"New Keywords: {newly_inserted_keywords}",
                    flush=True
                )

            browser.close()

        print("\n" + "=" * 80, flush=True)
        print("FINAL RETRY COMPLETE", flush=True)
        print("=" * 80, flush=True)
        total_products_db = db.query(Product).count()
        completed_products_db = db.query(Product).filter(Product.status == "completed").count()
        failed_products_db = db.query(Product).filter(Product.status == "failed").count()
        total_keywords_db = db.query(Keyword).count()
        distinct_asins_with_kw = set(r[0] for r in db.query(Keyword.source_product_asin).distinct().all())
        products_with_keywords_db = db.query(Product).filter(Product.asin.in_(distinct_asins_with_kw)).count()

        print(f"- Total products                 : {total_products_db}", flush=True)
        print(f"- Completed products             : {completed_products_db}", flush=True)
        print(f"- Failed products                : {failed_products_db}", flush=True)
        print(f"- Total keyword records          : {total_keywords_db}", flush=True)
        print(f"- Products with keywords         : {products_with_keywords_db}", flush=True)
        print("=" * 80, flush=True)

    finally:
        db.close()

if __name__ == "__main__":
    main()
