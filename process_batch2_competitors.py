import sys
import os
import time

# Ensure UTF-8 output on Windows consoles
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.database import SessionLocal, init_db
from app.models.product import Product
from app.models.competitor import CompetitorProduct, CompetitorKeyword
from app.services.competitor_analysis import get_product_keywords, analyze_product_keyword


def main():
    init_db()
    db = SessionLocal()
    try:
        # Step 1: Query products in batch range (IDs 101 to 300)
        batch_products = (
            db.query(Product)
            .filter(Product.id >= 101, Product.id <= 300)
            .order_by(Product.id.asc())
            .all()
        )
        total_in_batch = len(batch_products)

        # Step 2: Identify already completed products from MySQL database
        existing_cp_asins = set(
            r[0] for r in db.query(CompetitorProduct.source_product_asin).distinct().all()
        )

        completed_products = [p for p in batch_products if p.asin in existing_cp_asins]
        remaining_products = [p for p in batch_products if p.asin not in existing_cp_asins]

        print("=" * 90, flush=True)
        print("COMPETITOR SCRAPING - BATCH 2 (PRODUCTS 101 - 300) CONTINUATION", flush=True)
        print("=" * 90, flush=True)
        print(f"Total Products in Batch 2 (IDs 101-300): {total_in_batch}", flush=True)
        print(f"Already Completed Products              : {len(completed_products)} (Skipping)", flush=True)
        print(f"Remaining Products to Scrape            : {len(remaining_products)}", flush=True)
        print("=" * 90, flush=True)

        if not remaining_products:
            print("All products in Batch 2 are already completed! Nothing to process.", flush=True)
            return

        print(f"\nStarting scraping for {len(remaining_products)} remaining products...\n", flush=True)

        successful_count = 0
        failed_count = 0
        total_cp_inserted = 0
        total_cp_updated = 0
        total_ck_inserted = 0

        for idx, product in enumerate(remaining_products, 1):
            print(f"[{idx}/{len(remaining_products)}] Processing Product ID {product.id} | ASIN: {product.asin} | Name: {product.product_name[:50]}...", flush=True)

            keywords = get_product_keywords(db, product, limit=1)
            if not keywords:
                print(f"   [WARNING] No keywords found for product ASIN {product.asin} in MySQL database.", flush=True)
                failed_count += 1
                continue

            kw = keywords[0]
            print(f"   Using Keyword: '{kw.keyword}'", flush=True)

            # Retry up to 2 times for transient network/scraping failures
            success = False
            for attempt in range(1, 3):
                try:
                    res = analyze_product_keyword(
                        db,
                        product,
                        kw,
                        top_competitors=20,
                        max_pages=2,
                        delay_seconds=1.0,
                        write_db=True,
                    )
                    db_stats = res.get("db_stats", {})
                    cp_ins = db_stats.get("competitor_products_inserted", 0)
                    cp_upd = db_stats.get("competitor_products_updated", 0)
                    ck_ins = db_stats.get("competitor_keywords_inserted", 0)

                    total_cp_inserted += cp_ins
                    total_cp_updated += cp_upd
                    total_ck_inserted += ck_ins

                    print(
                        f"   [SUCCESS] Collected {res.get('top_competitors_count', 0)} competitor products, "
                        f"{len(res.get('extracted_competitor_keywords', []))} extracted keywords. "
                        f"(MySQL: +{cp_ins} comp products, +{ck_ins} comp keywords)",
                        flush=True
                    )
                    successful_count += 1
                    success = True
                    break
                except Exception as exc:
                    print(f"   [ATTEMPT {attempt}/2 FAILED] Error: {exc}", flush=True)
                    if attempt < 2:
                        time.sleep(3.0)

            if not success:
                print(f"   [FAILED] Product ID {product.id} (ASIN: {product.asin}) failed after 2 attempts.", flush=True)
                failed_count += 1

            # Brief pause between products
            time.sleep(1.0)

        # Step 3: Final Verification Report
        print("\n" + "=" * 90, flush=True)
        print("BATCH 2 SCRAPING SUMMARY", flush=True)
        print("=" * 90, flush=True)
        print(f"Target Remaining Products : {len(remaining_products)}", flush=True)
        print(f"Successfully Scraped       : {successful_count}", flush=True)
        print(f"Failed / Skipped           : {failed_count}", flush=True)
        print(f"Total Competitor Products Inserted : {total_cp_inserted}", flush=True)
        print(f"Total Competitor Products Updated  : {total_cp_updated}", flush=True)
        print(f"Total Competitor Keywords Inserted : {total_ck_inserted}", flush=True)
        print("=" * 90, flush=True)

        # DB Overall Check
        total_comp_products = db.query(CompetitorProduct).count()
        total_comp_keywords = db.query(CompetitorKeyword).count()
        distinct_asins_in_cp = set(
            r[0] for r in db.query(CompetitorProduct.source_product_asin).distinct().all()
        )
        batch2_completed_now = len([p for p in batch_products if p.asin in distinct_asins_in_cp])

        print("\n" + "=" * 90, flush=True)
        print("MYSQL DATABASE FINAL VERIFICATION", flush=True)
        print("=" * 90, flush=True)
        print(f"Total Competitor Product Rows in MySQL : {total_comp_products}", flush=True)
        print(f"Total Competitor Keyword Rows in MySQL : {total_comp_keywords}", flush=True)
        print(f"Distinct Source ASINs with Competitors  : {len(distinct_asins_in_cp)}", flush=True)
        print(f"Batch 2 Progress (IDs 101-300)          : {batch2_completed_now} / 200 Completed", flush=True)
        print("=" * 90 + "\n", flush=True)

    finally:
        db.close()


if __name__ == "__main__":
    main()
