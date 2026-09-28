import sys
import os
import time
import argparse

# Ensure UTF-8 output on Windows consoles
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.database import SessionLocal, init_db
from app.models.product import Product
from app.models.keyword import Keyword
from app.models.competitor import CompetitorProduct, CompetitorKeyword
from app.services.competitor_analysis import get_product_keywords, analyze_product_keyword

def run_remaining_competitor_scraping(batch_size: int = 1, delay_seconds: float = 1.0):
    init_db()
    db = SessionLocal()
    try:
        # Step 1: Query all products from MySQL database
        all_products = db.query(Product).order_by(Product.id.asc()).all()
        total_products_count = len(all_products)

        # Step 2: Identify already completed products from MySQL database
        existing_cp_asins = set(
            r[0] for r in db.query(CompetitorProduct.source_product_asin).distinct().all()
        )
        existing_ck_asins = set(
            r[0] for r in db.query(CompetitorKeyword.source_product_asin).distinct().all()
        )
        already_completed_asins = existing_cp_asins.union(existing_ck_asins)

        # Filter remaining products missing competitor data
        remaining_products = [p for p in all_products if p.asin not in already_completed_asins]

        print("=" * 90, flush=True)
        print("AUTOMATED COMPETITOR SCRAPING - REMAINING PRODUCTS", flush=True)
        print("=" * 90, flush=True)
        print(f"Total Products in Database                  : {total_products_count}", flush=True)
        print(f"Already Completed Products (Skipped)         : {len(already_completed_asins)}", flush=True)
        print(f"Remaining Products Missing Competitor Data : {len(remaining_products)}", flush=True)
        print(f"Configured Batch Size for this Run         : {batch_size}", flush=True)
        print("=" * 90, flush=True)

        if not remaining_products:
            print("\n[INFO] All products have completed competitor data! Nothing left to process.", flush=True)
            return {
                "total_products": total_products_count,
                "already_completed": len(already_completed_asins),
                "remaining_before": 0,
                "processed_count": 0,
                "successful_count": 0,
                "failed_count": 0
            }

        # Select only the next batch_size remaining products
        target_batch = remaining_products[:batch_size]

        successful_count = 0
        failed_count = 0
        total_cp_inserted = 0
        total_cp_updated = 0
        total_ck_inserted = 0

        for idx, product in enumerate(target_batch, 1):
            print(
                f"\n[{idx}/{len(target_batch)}] Processing Product ID {product.id} | ASIN: {product.asin} | Name: {product.product_name[:50]}...",
                flush=True
            )

            # Retrieve existing seed keyword for product or fallback
            keywords = get_product_keywords(db, product, limit=1)
            if not keywords:
                # If no keyword record exists in keywords table, create a temporary Keyword object for scraping
                kw_text = product.product_name[:60]
                kw = Keyword(
                    id=0,
                    keyword=kw_text,
                    source="auto_fallback",
                    source_product_asin=product.asin,
                    category=product.category
                )
                print(f"   [INFO] No stored keyword found. Using product title seed: '{kw.keyword}'", flush=True)
            else:
                kw = keywords[0]
                print(f"   Using Stored Keyword: '{kw.keyword}'", flush=True)

            success = False
            for attempt in range(1, 3):
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
                    cp_ins = db_stats.get("competitor_products_inserted", 0)
                    cp_upd = db_stats.get("competitor_products_updated", 0)
                    ck_ins = db_stats.get("competitor_keywords_inserted", 0)

                    total_cp_inserted += cp_ins
                    total_cp_updated += cp_upd
                    total_ck_inserted += ck_ins

                    top_comp_count = res.get("top_competitors_count", 0)

                    print(
                        f"   [SUCCESS] ID: {product.id} | ASIN: {product.asin} | "
                        f"Top Competitors Scraped: {top_comp_count} | Competitor Products Inserted: {cp_ins} | "
                        f"Competitor Keywords Inserted: {ck_ins}",
                        flush=True
                    )
                    successful_count += 1
                    success = True
                    break
                except Exception as exc:
                    db.rollback()
                    print(f"   [ATTEMPT {attempt}/2 FAILED] Error: {exc}", flush=True)
                    if attempt < 2:
                        time.sleep(2.0)

            if not success:
                print(
                    f"   [FAILED] Product ID {product.id} (ASIN: {product.asin}) failed after 2 attempts.",
                    flush=True
                )
                failed_count += 1

            time.sleep(delay_seconds)

        print("\n" + "=" * 90, flush=True)
        print("SUMMARY REPORT FOR THIS RUN", flush=True)
        print("=" * 90, flush=True)
        print(f"Batch Size Processed              : {len(target_batch)}", flush=True)
        print(f"Successfully Scraped              : {successful_count}", flush=True)
        print(f"Failed Products                   : {failed_count}", flush=True)
        print(f"Total Competitor Products Inserted: {total_cp_inserted}", flush=True)
        print(f"Total Competitor Products Updated : {total_cp_updated}", flush=True)
        print(f"Total Competitor Keywords Inserted: {total_ck_inserted}", flush=True)
        print("=" * 90 + "\n", flush=True)

        return {
            "total_products": total_products_count,
            "already_completed": len(already_completed_asins),
            "remaining_before": len(remaining_products),
            "processed_count": len(target_batch),
            "successful_count": successful_count,
            "failed_count": failed_count,
            "total_cp_inserted": total_cp_inserted,
            "total_ck_inserted": total_ck_inserted
        }

    finally:
        db.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Automated Remaining Competitor Products Scraper")
    parser.add_argument("--batch-size", type=int, default=1, help="Number of remaining products to process in this run")
    parser.add_argument("--delay", type=float, default=1.0, help="Delay between requests in seconds")
    args = parser.parse_args()

    run_remaining_competitor_scraping(batch_size=args.batch_size, delay_seconds=args.delay)
