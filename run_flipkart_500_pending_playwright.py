import sys
import os
import time
import re
import logging

sys.path.insert(0, r"d:\22yards_keyword_database_competitor_ready\22yards_keyword_database")

from app.database import SessionLocal, SessionFlipkart
from app.models.product import Product
from app.models.keyword import Keyword
from app.services.flipkart_suggestion_runner import clean_flipkart_title_to_seeds
from app.services.flipkart_keyword_collector import collect_flipkart_keywords

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("flipkart_500_pending")

METRICS = {
    "products_processed": 0,
    "successfully_completed": 0,
    "failed": 0,
    "total_keywords_collected": 0,
    "retry_timeout_errors": 0
}

def safe_goto(page, url, max_retries=3, backoff=2):
    for attempt in range(1, max_retries + 1):
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=25000)
            return True
        except Exception as e:
            METRICS["retry_timeout_errors"] += 1
            logger.warning(f"Page goto attempt {attempt}/{max_retries} failed for {url}: {e}")
            if attempt < max_retries:
                time.sleep(backoff * attempt)
    return False

def collect_playwright_suggestions(page, seed_text, max_retries=2):
    suggestions = []
    for attempt in range(1, max_retries + 1):
        try:
            if "flipkart.com" not in page.url:
                if not safe_goto(page, "https://www.flipkart.com"):
                    continue

            try:
                page.keyboard.press("Escape")
                time.sleep(0.3)
            except Exception:
                pass

            search_input = page.locator("input[name='q'], input[title*='Search'], input[placeholder*='Search']")
            if search_input.count() > 0:
                search_input.first.evaluate("el => el.focus()")
                search_input.first.fill("")
                search_input.first.fill(seed_text)
                time.sleep(1.5)

                selectors = [
                    "ul._1sB9Bx li", 
                    "ul._3D2Eav li", 
                    "div._1AMrR3 div", 
                    "form._2rslOn ul li", 
                    "ul[class*='suggest'] li", 
                    "div[class*='suggestion']", 
                    "li[class*='suggest']",
                    "a[class*='_3qv22d']", 
                    "ul._1cdP2B li", 
                    "div._3q2v2d"
                ]
                for sel in selectors:
                    elems = page.locator(sel)
                    cnt = elems.count()
                    if cnt > 0:
                        for i in range(cnt):
                            txt = elems.nth(i).inner_text().strip()
                            if txt:
                                cleaned = txt.split('\n')[0].strip()
                                if cleaned and cleaned not in suggestions:
                                    suggestions.append(cleaned)
                        if suggestions:
                            break
            if suggestions:
                break
        except Exception as err:
            METRICS["retry_timeout_errors"] += 1
            logger.warning(f"Playwright DOM exception on seed '{seed_text}' (Attempt {attempt}): {err}")
            time.sleep(1)

    # API fallback if DOM search overlay didn't yield keywords
    if not suggestions:
        try:
            api_results = collect_flipkart_keywords(seed_text)
            for kw in api_results:
                kw_clean = re.sub(r'\s+', ' ', kw).strip()
                if kw_clean and kw_clean not in suggestions:
                    suggestions.append(kw_clean)
        except Exception as api_err:
            METRICS["retry_timeout_errors"] += 1
            logger.warning(f"API fallback exception for seed '{seed_text}': {api_err}")

    return suggestions

def main():
    db_main = SessionLocal()
    db_fk = SessionFlipkart()

    pending_products = (
        db_main.query(Product)
        .filter(Product.flipkart_status == 'pending')
        .order_by(Product.id.asc())
        .limit(500)
        .all()
    )

    print("=" * 85)
    print(f" TARGET PRODUCTS FOR COLLECTION: EXACTLY {len(pending_products)} PENDING PRODUCTS")
    print("=" * 85)
    for idx, p in enumerate(pending_products, 1):
        print(f"{idx:3d}. ID: {p.id:<5d} | ASIN/FSN: {p.asin:<18s} | Name: {p.product_name}")
    print("=" * 85)
    print("CONFIRMATION: Only these 500 pending products will be processed.")
    print("Completed products (585) and Failed products (0) will NOT be touched.")
    print("Amazon status, marketplace, and keywords remain completely untouched.")
    print("=" * 85 + "\n")

    if not pending_products:
        print("No pending products found to process.")
        db_main.close()
        db_fk.close()
        return

    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
            viewport={'width': 1280, 'height': 800}
        )
        page = context.new_page()
        safe_goto(page, "https://www.flipkart.com")

        for idx, prod_main in enumerate(pending_products, 1):
            METRICS["products_processed"] += 1
            prod_fk = db_fk.query(Product).filter(Product.id == prod_main.id).first()

            seeds = clean_flipkart_title_to_seeds(prod_main.product_name, prod_main.category)
            if not seeds:
                seeds = [prod_main.product_name]

            print(f"[{idx:3d}/500] Product ID: {prod_main.id:<5d} | ASIN/FSN: {prod_main.asin:<18s} | Name: {prod_main.product_name}")
            print(f"        Seeds: {seeds}")

            collected_keywords_set = set()
            for seed in seeds:
                suggs = collect_playwright_suggestions(page, seed)
                for kw in suggs:
                    kw_clean = re.sub(r'\s+', ' ', kw).strip()
                    if kw_clean:
                        collected_keywords_set.add(kw_clean)
                time.sleep(0.2)

            total_kws = len(collected_keywords_set)
            print(f"        Keywords Found: {total_kws}")

            if total_kws > 0:
                inserted_count = 0
                for kw_text in collected_keywords_set:
                    # db_fk
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
                        inserted_count += 1

                    # db_main
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

                METRICS["successfully_completed"] += 1
                METRICS["total_keywords_collected"] += total_kws
                print(f"        Result: COMPLETED ({inserted_count} new keywords added)\n")
            else:
                prod_main.flipkart_status = "failed"
                if prod_fk:
                    prod_fk.flipkart_status = "failed"
                METRICS["failed"] += 1
                print("        Result: FAILED (No valid autocomplete suggestions found across seeds)\n")

            db_main.commit()
            if prod_fk:
                db_fk.commit()

        browser.close()

    # Final DB counts verification
    final_completed = db_main.query(Product).filter(Product.flipkart_status == 'completed').count()
    final_failed = db_main.query(Product).filter(Product.flipkart_status == 'failed').count()
    final_pending = db_main.query(Product).filter(Product.flipkart_status == 'pending').count()

    print("=" * 85)
    print(" 500 PENDING BATCH COLLECTION FINAL REPORT")
    print("=" * 85)
    print(f"- Products processed:           {METRICS['products_processed']}")
    print(f"- Successfully completed:       {METRICS['successfully_completed']}")
    print(f"- Failed:                       {METRICS['failed']}")
    print(f"- Total keywords collected:     {METRICS['total_keywords_collected']}")
    print(f"- Remaining pending:            {final_pending}")
    print(f"- Retry/timeout errors:         {METRICS['retry_timeout_errors']}")
    print("-" * 85)
    print(" MYSQL DATABASE STATUS SUMMARY:")
    print(f" - Flipkart Completed:          {final_completed}")
    print(f" - Flipkart Failed:             {final_failed}")
    print(f" - Flipkart Pending:            {final_pending}")
    print(f" - Total Products:              {final_completed + final_failed + final_pending}")
    print("=" * 85 + "\n")

    db_main.close()
    db_fk.close()

if __name__ == "__main__":
    main()
