import sys
import os
import time
import argparse
from datetime import datetime

# Ensure UTF-8 output on Windows consoles
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.database import SessionLocal, init_db
from app.models.product import Product
from app.models.keyword import Keyword
from app.models.competitor import CompetitorProduct, CompetitorKeyword
from app.services.competitor_analysis import get_product_keywords, analyze_product_keyword


def get_competitor_completion_status(db):
    """Query MySQL database to get exact completed and pending ASIN sets."""
    cp_asins = set(
        r[0] for r in db.query(CompetitorProduct.source_product_asin).distinct().all()
    )
    ck_asins = set(
        r[0] for r in db.query(CompetitorKeyword.source_product_asin).distinct().all()
    )
    completed_asins = cp_asins.union(ck_asins)
    return completed_asins


def process_pending_competitors(batch_size: int = 50, delay_seconds: float = 1.0, max_products: int = 0):
    init_db()
    db = SessionLocal()

    start_time = time.time()
    print("=" * 90, flush=True)
    print(f"AUTOMATED COMPETITOR SCRAPING FOR PENDING PRODUCTS - STARTED AT {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", flush=True)
    print("=" * 90, flush=True)

    try:
        # Step 1: Query MySQL for initial counts and identify pending products
        all_products = db.query(Product).order_by(Product.id.asc()).all()
        total_products_count = len(all_products)

        completed_asins_initial = get_competitor_completion_status(db)
        already_completed_count = len(completed_asins_initial)

        pending_products = [p for p in all_products if p.asin not in completed_asins_initial]
        initial_pending_count = len(pending_products)

        print(f"Total Products in Database                  : {total_products_count}", flush=True)
        print(f"Already Completed Products (Skipping)       : {already_completed_count}", flush=True)
        print(f"Remaining Pending Products to Process       : {initial_pending_count}", flush=True)
        print(f"Configured Batch Size                      : {batch_size}", flush=True)
        if max_products > 0:
            print(f"Max Products Cap for this execution        : {max_products}", flush=True)
            pending_products = pending_products[:max_products]
        print("=" * 90 + "\n", flush=True)

        if not pending_products:
            print("[INFO] All products in MySQL database already have competitor data! Nothing to process.", flush=True)
            return

        total_to_process = len(pending_products)
        processed_count = 0
        successful_count = 0
        failed_count = 0

        total_cp_inserted = 0
        total_cp_updated = 0
        total_ck_inserted = 0

        # Process in batches
        for batch_start_idx in range(0, total_to_process, batch_size):
            batch_num = (batch_start_idx // batch_size) + 1
            total_batches = (total_to_process + batch_size - 1) // batch_size
            current_batch = pending_products[batch_start_idx : batch_start_idx + batch_size]

            print("-" * 90, flush=True)
            print(f"--- STARTING BATCH {batch_num}/{total_batches} ({len(current_batch)} Products) ---", flush=True)
            print("-" * 90, flush=True)

            for item_idx, product in enumerate(current_batch, 1):
                global_idx = batch_start_idx + item_idx
                processed_count += 1

                # Re-verify DB status for this ASIN before scraping to ensure safety & skip if completed
                cp_count = db.query(CompetitorProduct).filter(CompetitorProduct.source_product_asin == product.asin).count()
                ck_count = db.query(CompetitorKeyword).filter(CompetitorKeyword.source_product_asin == product.asin).count()

                if cp_count > 0 or ck_count > 0:
                    print(
                        f"[{global_idx}/{total_to_process}] Product ID: {product.id} | ASIN: {product.asin} | STATUS: SKIPPED (Already in DB)",
                        flush=True
                    )
                    successful_count += 1
                    continue

                print(
                    f"[{global_idx}/{total_to_process}] Processing Product ID: {product.id} | ASIN: {product.asin} | Title: {product.product_name[:50]}...",
                    flush=True
                )

                # Fetch stored keywords for the product
                keywords = get_product_keywords(db, product)
                keyword_candidates = list(keywords) if keywords else []

                # Fallback seeds from product title and category if needed
                from app.services.competitor_analysis import competitor_seed_queries
                fallback_seeds = competitor_seed_queries(product.product_name, product.category)
                for seed in fallback_seeds:
                    if seed and seed.lower() not in [k.keyword.lower() for k in keyword_candidates]:
                        keyword_candidates.append(Keyword(
                            id=0,
                            keyword=seed,
                            source="title_fallback",
                            source_product_asin=product.asin,
                            category=product.category
                        ))

                product_success = False
                cp_ins_product = 0
                cp_upd_product = 0
                ck_ins_product = 0

                # Try up to top 4 keyword candidates available for the product
                for kw in keyword_candidates[:4]:
                    for attempt in range(1, 3): # Retry up to 2 attempts per keyword
                        try:
                            res = analyze_product_keyword(
                                db,
                                product,
                                kw,
                                top_competitors=20,
                                max_pages=2,
                                delay_seconds=delay_seconds,
                                write_db=True,
                            )
                            db_stats = res.get("db_stats", {})
                            cp_ins_product = db_stats.get("competitor_products_inserted", 0)
                            cp_upd_product = db_stats.get("competitor_products_updated", 0)
                            ck_ins_product = db_stats.get("competitor_keywords_inserted", 0)
                            top_comp_count = res.get("top_competitors_count", 0)

                            if top_comp_count > 0 or cp_ins_product > 0 or cp_upd_product > 0:
                                total_cp_inserted += cp_ins_product
                                total_cp_updated += cp_upd_product
                                total_ck_inserted += ck_ins_product

                                print(
                                    f"   [SUCCESS] Keyword: '{kw.keyword}' | Top Competitors: {top_comp_count} | "
                                    f"CP Ins: {cp_ins_product} | CP Upd: {cp_upd_product} | CK Ins: {ck_ins_product}",
                                    flush=True
                                )
                                successful_count += 1
                                product_success = True
                                break
                            else:
                                print(f"   [INFO] Keyword '{kw.keyword}' returned 0 results. Trying next keyword if available...", flush=True)
                                break
                        except Exception as exc:
                            db.rollback()
                            print(f"   [ATTEMPT {attempt}/2 FAILED] Keyword '{kw.keyword}' Error: {exc}", flush=True)
                            if attempt < 2:
                                time.sleep(2.0)

                    if product_success:
                        break

                if not product_success:
                    print(f"   [FAILED] Product ID {product.id} (ASIN: {product.asin}) failed after all attempts.", flush=True)
                    failed_count += 1

                # Brief delay between products to avoid throttling
                time.sleep(delay_seconds)

            print(f"\nCompleted Batch {batch_num}/{total_batches}. Cumulative Progress: {processed_count}/{total_to_process} (Success: {successful_count}, Failed: {failed_count})\n", flush=True)

        elapsed_seconds = time.time() - start_time
        elapsed_str = time.strftime("%H:%M:%S", time.gmtime(elapsed_seconds))

        # Query final DB state
        completed_asins_final = get_competitor_completion_status(db)
        final_completed_count = len(completed_asins_final)
        final_pending_count = total_products_count - final_completed_count

        print("=" * 90, flush=True)
        print("FINAL COMPETITOR SCRAPING SUMMARY REPORT", flush=True)
        print("=" * 90, flush=True)
        print(f"Execution Time                           : {elapsed_str}", flush=True)
        print(f"Total Products in Database               : {total_products_count}", flush=True)
        print(f"Initially Completed Products (Skipped)    : {already_completed_count}", flush=True)
        print(f"Initial Pending Products                 : {initial_pending_count}", flush=True)
        print(f"Total Processed in this Execution        : {processed_count}", flush=True)
        print(f"Successfully Completed in this Execution : {successful_count}", flush=True)
        print(f"Failed Products in this Execution        : {failed_count}", flush=True)
        print(f"Total Competitor Products Inserted       : {total_cp_inserted}", flush=True)
        print(f"Total Competitor Products Updated        : {total_cp_updated}", flush=True)
        print(f"Total Competitor Keywords Inserted       : {total_ck_inserted}", flush=True)
        print("-" * 90, flush=True)
        print(f"FINAL MYSQL DATABASE STATE:", flush=True)
        print(f"  - Total Products                       : {total_products_count}", flush=True)
        print(f"  - Total Products WITH Competitor Data  : {final_completed_count} ({(final_completed_count/total_products_count)*100:.1f}%)", flush=True)
        print(f"  - Total Products MISSING Competitor Data: {final_pending_count}", flush=True)
        print("=" * 90 + "\n", flush=True)

    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Automated Remaining Competitor Products Batch Scraper")
    parser.add_argument("--batch-size", type=int, default=50, help="Number of products per batch reporting step")
    parser.add_argument("--delay", type=float, default=1.0, help="Delay between requests in seconds")
    parser.add_argument("--max-products", type=int, default=0, help="Maximum products to process (0 for all remaining)")
    args = parser.parse_args()

    process_pending_competitors(batch_size=args.batch_size, delay_seconds=args.delay, max_products=args.max_products)
