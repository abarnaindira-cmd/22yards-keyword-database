import sys
import os
import time
import re
import json
import asyncio

sys.path.insert(0, r"d:\22yards_keyword_database_competitor_ready\22yards_keyword_database")

from app.database import SessionLocal, SessionFlipkart
from app.models.product import Product
from app.models.keyword import Keyword
from app.services.flipkart_suggestion_runner import clean_flipkart_title_to_seeds

TARGET_PRODUCT_IDS = [383, 384, 385, 386, 387]

def print_selected_products():
    db = SessionLocal()
    products = db.query(Product).filter(Product.id.in_(TARGET_PRODUCT_IDS)).order_by(Product.id.asc()).all()
    print("==================================================")
    print(" SELECTED TEST PRODUCTS BEFORE COLLECTION START")
    print("==================================================")
    for p in products:
        print(f"- ID: {p.id}")
        print(f"  Product Name: {p.product_name}")
        print(f"  ASIN/FSN: {p.asin}\n")
    print("==================================================\n")
    db.close()
    return products

async def collect_suggestions_via_playwright(page, seed_text):
    suggestions = []
    try:
        # Navigate to Flipkart home if needed or focus search input
        if "flipkart.com" not in page.url:
            await page.goto("https://www.flipkart.com", wait_until="domcontentloaded", timeout=15000)
            await asyncio.sleep(1)

        # Close login popup if present
        try:
            close_btn = page.locator("span._30XB9F, button._2KpZ6l._2doB4z, span._2dBwL-")
            if await close_btn.count() > 0:
                await close_btn.first.click(timeout=2000)
        except Exception:
            pass

        # Locate search input
        search_input = page.locator("input[name='q'], input[title='Search for Products, Brands and More'], input[placeholder*='Search']")
        if await search_input.count() > 0:
            await search_input.first.click()
            await search_input.first.fill("")
            await search_input.first.fill(seed_text)
            await asyncio.sleep(1.5)

            # Extract dropdown suggestion items
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
                cnt = await elems.count()
                if cnt > 0:
                    for i in range(cnt):
                        txt = await elems.nth(i).inner_text()
                        if txt and txt.strip():
                            # Remove non-text noise
                            cleaned = txt.strip().split("\n")[0].strip()
                            if cleaned and cleaned not in suggestions:
                                suggestions.append(cleaned)
                    if suggestions:
                        break

    except Exception as err:
        print(f"  [Playwright Warning] Page interaction error for seed '{seed_text}': {err}")

    # Fallback to direct Flipkart Autosuggest API if DOM dropdown is empty
    if not suggestions:
        try:
            import urllib.request
            url = "https://2.rome.api.flipkart.com/4/discover/autosuggest"
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
                "Content-Type": "application/json",
                "Origin": "https://www.flipkart.com",
                "Referer": "https://www.flipkart.com/"
            }
            payload = json.dumps({"queries": [{"query": seed_text, "context": {}}]}).encode("utf-8")
            req = urllib.request.Request(url, data=payload, headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=5) as resp:
                res_data = json.loads(resp.read().decode("utf-8"))
                timeline = res_data.get("RESPONSE", {}).get("timeline", [])
                for widget in timeline:
                    sug_list = widget.get("widget", {}).get("data", {}).get("suggestions", [])
                    for sug in sug_list:
                        kw = sug.get("value") or sug.get("text") or (sug.get("searchQuery", {}).get("value") if isinstance(sug.get("searchQuery"), dict) else None)
                        if kw and isinstance(kw, str):
                            kw_clean = re.sub(r'\s+', ' ', kw).strip()
                            if kw_clean and kw_clean not in suggestions:
                                suggestions.append(kw_clean)
        except Exception as exc:
            print(f"  [API Fallback Error] {exc}")

    return suggestions

async def main():
    # Step 1 & 2: Print selected products FIRST before collection start
    print_selected_products()

    # Step 3: Start Playwright collection
    from playwright.async_api import async_playwright
    
    db_main = SessionLocal()
    db_fk = SessionFlipkart()

    results_summary = []

    print("Starting Playwright Flipkart Autocomplete Collection for the 5 selected products...\n")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 800}
        )
        page = await context.new_page()

        for pid in TARGET_PRODUCT_IDS:
            prod_main = db_main.query(Product).filter(Product.id == pid).first()
            if not prod_main:
                continue

            prod_fk = db_fk.query(Product).filter(Product.id == pid).first()

            seeds = clean_flipkart_title_to_seeds(prod_main.product_name, prod_main.category)
            if not seeds:
                seeds = [prod_main.product_name]

            print("--------------------------------------------------")
            print(f"Product ID:                     {prod_main.id}")
            print(f"Product Name:                   {prod_main.product_name}")
            print(f"ASIN/FSN:                       {prod_main.asin}")
            print(f"Search Seeds:                   {seeds}")

            collected_keywords_set = set()
            all_found_suggestions = []

            for seed in seeds:
                suggestions = await collect_suggestions_via_playwright(page, seed)
                print(f"Search Seed:                    '{seed}'")
                print(f"Autocomplete Suggestions Found: {suggestions}")
                for kw in suggestions:
                    kw_clean = re.sub(r'\s+', ' ', kw).strip()
                    if kw_clean:
                        collected_keywords_set.add(kw_clean)
                        if kw_clean not in all_found_suggestions:
                            all_found_suggestions.append(kw_clean)

            total_kws = len(collected_keywords_set)
            print(f"Number of Keywords:             {total_kws}")

            # Store keywords if found and update status
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

        await browser.close()

    db_main.close()
    db_fk.close()

    # Step 5: Final Summary showing exactly those same 5 product IDs
    print("\n==================================================")
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
    asyncio.run(main())
