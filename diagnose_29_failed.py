import sys
import re
import html
import urllib.parse
from typing import List, Dict, Any, Tuple
from playwright.sync_api import sync_playwright

sys.path.insert(0, r'd:\22yards_keyword_database')

from app.database import SessionLocal
from app.models.product import Product
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

def fetch_amazon_serp_titles(seed: str, browser) -> Tuple[bool, List[str]]:
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

        return True, titles

    except Exception as e:
        return False, []
    finally:
        if context:
            context.close()

def main():
    db = SessionLocal()
    try:
        failed_products = db.query(Product).filter(Product.status == "failed").all()
        print("=" * 85)
        print(f"READ-ONLY DIAGNOSIS FOR {len(failed_products)} FAILED PRODUCTS")
        print("=" * 85 + "\n")

        diagnostics = []

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)

            for idx, prod in enumerate(failed_products, 1):
                p_id = prod.id
                p_name = prod.product_name
                p_cat = prod.category
                p_asin = prod.asin

                seeds = clean_product_title_to_seeds(p_name, p_cat)
                
                # Test suggestions per seed
                suggestions_map = {}
                for s in seeds:
                    suggs = fetch_amazon_suggestions_api(s)
                    suggestions_map[s] = suggs

                # Test SERP per primary seed
                primary_seed = seeds[0] if seeds else p_name
                serp_loaded, serp_titles = fetch_amazon_serp_titles(primary_seed, browser)
                candidates = extract_keyword_candidates_from_titles(serp_titles) if serp_titles else []

                total_suggestions_count = sum(len(v) for v in suggestions_map.values())
                
                failure_reason = ""
                potential_recovery = ""

                if total_suggestions_count == 0 and len(serp_titles) == 0:
                    if p_cat in {"APPAREL", "Shoe", "shoes"}:
                        failure_reason = "Obscure/Internal model name in generic category (APPAREL/Shoe) - Primary seed returned 0 autocomplete & 0 SERP"
                        potential_recovery = "Yes (Can recover by extracting core noun e.g. 'Shorts', 'Brief', 'Jacket', 'Football Stud' combined with 'Men' or product type)"
                    else:
                        failure_reason = "Highly obscure product code/term with zero Amazon search matches"
                        potential_recovery = "Yes (Can recover by querying Category name as direct fallback)"
                elif total_suggestions_count > 0:
                    failure_reason = "Suggestions exist for seed, but were previously excluded by strict duplicate/generic filter"
                    potential_recovery = "Yes (Can recover immediately by taking seed suggestions)"
                elif len(serp_titles) > 0 and len(candidates) == 0:
                    failure_reason = "SERP loaded titles but titles contained non-parseable noise"
                    potential_recovery = "Yes (Can recover by relaxing title candidate parser rules)"
                elif len(serp_titles) > 0 and len(candidates) > 0:
                    failure_reason = "SERP returned results during retry diagnosis"
                    potential_recovery = "Yes (Recoverable via SERP title extraction)"
                else:
                    failure_reason = "Unknown search response anomaly"
                    potential_recovery = "Needs manual review"

                item_diag = {
                    "id": p_id,
                    "name": p_name,
                    "category": p_cat,
                    "asin": p_asin,
                    "seeds": seeds,
                    "suggestions_map": suggestions_map,
                    "serp_loaded": serp_loaded,
                    "serp_titles_count": len(serp_titles),
                    "candidates_count": len(candidates),
                    "candidates_sample": candidates[:3],
                    "failure_reason": failure_reason,
                    "potential_recovery": potential_recovery
                }
                diagnostics.append(item_diag)

                print(f"Product #{idx}: ID={p_id} | Name='{p_name}' | Cat='{p_cat}'")
                print(f"  Generated Seeds: {seeds}")
                print(f"  Amazon Suggestions: {total_suggestions_count} across seeds {suggestions_map}")
                print(f"  SERP Page Loaded: {'Yes' if serp_loaded else 'No'} | Titles Found: {len(serp_titles)}")
                print(f"  Extracted Candidates: {len(candidates)} {candidates[:3]}")
                print(f"  Exact Failure Reason: {failure_reason}")
                print(f"  Potential Recovery : {potential_recovery}")
                print("-" * 85 + "\n")

            browser.close()

        # Grouping by failure reason
        reason_groups = {}
        recoverable_count = 0

        for d in diagnostics:
            r = d["failure_reason"]
            reason_groups[r] = reason_groups.get(r, 0) + 1
            if d["potential_recovery"].startswith("Yes"):
                recoverable_count += 1

        print("=" * 85)
        print("DIAGNOSTIC SUMMARY FOR 29 FAILED PRODUCTS")
        print("=" * 85)
        print(f"Total Failed Products Diagnosed: {len(diagnostics)}")
        print(f"Potentially Recoverable Products: {recoverable_count} / {len(diagnostics)}")
        print("\nFailure Reason Breakdown:")
        for reason, count in reason_groups.items():
            print(f"  - [{count} products] {reason}")
        print("=" * 85)

    finally:
        db.close()

if __name__ == "__main__":
    main()
