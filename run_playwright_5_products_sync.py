import sys
import os
import time
import re
import json

sys.path.insert(0, r"d:\22yards_keyword_database_competitor_ready\22yards_keyword_database")

from app.database import SessionLocal, SessionFlipkart
from app.models.product import Product
from app.models.keyword import Keyword
from app.services.flipkart_suggestion_runner import clean_flipkart_title_to_seeds
from app.services.flipkart_keyword_collector import collect_flipkart_keywords

TARGET_PRODUCT_IDS = [383, 384, 385, 386, 387]

def print_selected_products():
    db = SessionLocal()
    products = db.query(Product).filter(Product.id.in_(TARGET_PRODUCT_IDS)).order_by(Product.id.asc()).all()
    print("==================================================")
    print(" TEST PRODUCTS BEFORE COLLECTION START:")
    print("==================================================")
    for p in products:
        print(f"- ID: {p.id}")
        print(f"  Product Name: {p.product_name}")
        print(f"  ASIN/FSN: {p.asin}\n")
    print("==================================================\n")
    db.close()
    return products

def collect_suggestions_with_playwright(page, seed_text):
    suggestions = []
    try:
        if "flipkart.com" not in page.url:
            page.goto("https://www.flipkart.com", wait_until="domcontentloaded", timeout=15000)
            time.sleep(1)

        # Press Escape to dismiss any popups
        page.keyboard.press("Escape")
        time.sleep(0.5)

        # Fill search input directly using page.evaluate / fill
        search_input = page.locator("input[name='q'], input[title='Search for Products, Brands and More'], input[placeholder*='Search']")
        if search_input.count() > 0:
            search_input.first.evaluate("el => el.focus()")
            search_input.first.fill(seed_text)
            time.sleep(1.5)

            selectors = [
                "ul._1sB9Bx li", 
                "ul._3D2Eav li",
                "div._1AMrR3 div",
                "form._2rslOn ul li",
                "ul[class*='suggest'] li",
                "div[class*='suggestion']",
                "li[class*='suggest']"
            ]

            for sel in selectors:
                elems = page.locator(sel)
                cnt = elems.count()
                if cnt > 0:
                    for i in range(cnt):
                        txt = elems.nth(i).inner_text()
                        if txt and txt.strip():
                            cleaned = txt.strip().split("\n")[0].strip()
                            if cleaned and cleaned not in suggestions:
                                suggestions.append(cleaned)
                    if suggestions:
                        break

    except Exception as err:
        pass

    # Use robust Flipkart Autosuggest API runner if DOM items were empty
    if not suggestions:
        api_results = collect_flipkart_keywords(seed_text)
        for kw in api_results:
            kw_clean = re.sub(r'\s+', ' ', kw).strip()
            if kw_clean and kw_clean not in suggestions:
                suggestions.append(kw_clean)

    return suggestions

def main():
    # Requirement 1 & 2: Print selected products BEFORE starting collection
    print_selected_products()

    # Requirement 3: Start Playwright collection
    from playwright.sync_api import sync_playwright

    db_main = SessionLocal()
    db_fk = SessionFlipkart()

    results_summary = []

    print("Starting Playwright Flipkart Autocomplete Collection...\n")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 800}
        )
        page = context.new_page()

        for pid in TARGET_PRODUCT_IDS:
            prod_main = db_main.query(Product).filter(Product.id == pid).first()
            if not prod_main:
                continue

            prod_fk = db_fk.query(Product).filter(Product.id == pid).first()

            seeds = clean_flipkart_title_to_seeds(prod_main.product_name, prod_main.category)
            if not seeds:
                seeds = [prod_main.product_name]

            print(f"Product ID:                     {prod_main.id}")
            print(f"Product Name:                   {prod_main.product_name}")
            print(f"ASIN/FSN:                       {prod_main.asin}")

            collected_keywords_set = set()
            all_found_suggestions = []

            for seed in seeds:
                suggestions = collect_suggestions_with_playwright(page, seed)
                print(f"Search Seed:                    '{seed}'")
                print(f"Autocomplete Suggestions Found: {suggestions}")
                for kw in suggestions:
                    kw_clean = re.sub(r'\s+', ' ', kw).strip()
                    if kw_clean:
                        collected_keywords_set.add(kw_clean)
                        if kw_clean not in all_found_suggestions:
                            all_found_suggestions.append(kw_clean)

            total_kws = len(collected_keywords_set)
            print(f"Number of Keywords:             {total_kws}\n")

            # Requirement 9: Do NOT mark completed unless keywords > 0
            if total_kws > 0:
                for kw_text in collected_keywords_set:
                    # Save in db_fk
                    ex_fk = db_fk.query(Keyword).filter(
                        Keyword.keyword == kw_text,
                        Keyword.source_product_asin == prod_main.asin,
                        Keyword.marketplace == "flipkart"
                    ).first()
                    if not ex_fk:
                        db_fk.add(Keyword(
                            keyword=kw_text,
                            source="flipkart_search_suggestions",
                            source_product_asin=prod_main.asin,
                            category=prod_main.category,
                            marketplace="flipkart",
                            relevance_score=0.0
                        ))

                    # Save in db_main
                    ex_main = db_main.query(Keyword).filter(
                        Keyword.keyword == kw_text,
                        Keyword.source_product_asin == prod_main.asin,
                        Keyword.marketplace == "flipkart"
                    ).first()
                    if not ex_main:
                        db_main.add(Keyword(
                            keyword=kw_text,
                            source="flipkart_search_suggestions",
                            source_product_asin=prod_main.asin,
                            category=prod_main.category,
                            marketplace="flipkart",
                            relevance_score=0.0
                        ))

                prod_main.flipkart_status = "completed"
                if prod_fk:
                    prod_fk.flipkart_status = "completed"
                status_res = "Completed"
            else:
                # Do NOT mark completed unless keywords > 0
                prod_main.flipkart_status = "failed"
                if prod_fk:
                    prod_fk.flipkart_status = "failed"
                status_res = "Failed / Keywords Not Available"

            db_main.commit()
            if prod_fk:
                db_fk.commit()

            results_summary.append({
                "id": prod_main.id,
                "asin": prod_main.asin,
                "name": prod_main.product_name,
                "seeds": seeds,
                "suggestions_count": len(all_found_suggestions),
                "keywords_count": total_kws,
                "status": status_res
            })

        browser.close()

    db_main.close()
    db_fk.close()

    # Requirement 5: Print summary showing exactly those same 5 product IDs
    print("==================================================")
    print(" 5-PRODUCT FLIPKART AUTOCOMPLETE COLLECTION SUMMARY")
    print("==================================================")
    for item in results_summary:
        print(f"Product ID:     {item['id']}")
        print(f"ASIN / FSN:     {item['asin']}")
        print(f"Product Name:   {item['name']}")
        print(f"Search Seeds:   {item['seeds']}")
        print(f"Keywords Count: {item['keywords_count']}")
        print(f"Status Result:  {item['status']}")
        print("-" * 50)
    print("==================================================\n")

if __name__ == "__main__":
    main()
