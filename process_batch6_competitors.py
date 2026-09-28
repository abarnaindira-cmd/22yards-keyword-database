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
from app.models.keyword import Keyword
from app.services.competitor_analysis import get_product_keywords, analyze_product_keyword


def main():
    init_db()
    db = SessionLocal()
    try:
        # Step 1: Query products in batch range (IDs 1201 to 1400)
        batch_products = (
            db.query(Product)
            .filter(Product.id >= 1201, Product.id <= 1400)
            .order_by(Product.id.asc())
            .all()
        )
        total_in_batch = len(batch_products)

        # Step 2: Identify already completed products from MySQL database
        existing_cp_asins = set(
            r[0] for r in db.query(CompetitorProduct.source_product_asin).distinct().all()
        )
        existing_ck_asins = set(
            r[0] for r in db.query(CompetitorKeyword.source_product_asin).distinct().all()
        )
        already_completed_asins = existing_cp_asins.union(existing_ck_asins)

        print("=" * 90, flush=True)
        print("COMPETITOR SCRAPING - BATCH 6 (PRODUCTS 1201 - 1400)", flush=True)
        print("=" * 90, flush=True)
        print(f"Total Products in Batch Range (IDs 1201-1400) : {total_in_batch}", flush=True)

        already_done = [p for p in batch_products if p.asin in already_completed_asins]
        to_process = [p for p in batch_products if p.asin not in already_completed_asins]

        print(f"Already Completed Products in DB (Skipping)  : {len(already_done)}", flush=True)
        print(f"Pending Products to Process                  : {len(to_process)}", flush=True)
        print("=" * 90 + "\n", flush=True)

        successful_count = 0
        failed_count = 0
        skipped_count = len(already_done)
        total_cp_inserted = 0
        total_ck_inserted = 0

        # Step 3: Process products sequentially
        for idx, product in enumerate(batch_products, 1):
            # Check existing competitor data directly from DB before processing each product
            cp_count = db.query(CompetitorProduct).filter(CompetitorProduct.source_product_asin == product.asin).count()
            ck_count = db.query(CompetitorKeyword).filter(CompetitorKeyword.source_product_asin == product.asin).count()

            if cp_count > 0 or ck_count > 0:
                print(
                    f"[{idx}/{total_in_batch}] Product ID: {product.id} | ASIN: {product.asin} | status: SKIPPED (Already Completed) | competitor products: {cp_count} | competitor keywords: {ck_count}",
                    flush=True
                )
                continue

            print(
                f"[{idx}/{total_in_batch}] Processing Product ID: {product.id} | ASIN: {product.asin} | Name: {product.product_name[:45]}...",
                flush=True
            )

            keywords = get_product_keywords(db, product)
            if not keywords:
                # Fallback to product name if no keyword stored
                kw_text = product.product_name[:60]
                keywords = [Keyword(
                    id=0,
                    keyword=kw_text,
                    source="auto_fallback",
                    source_product_asin=product.asin,
                    category=product.category
                )]

            success = False
            cp_ins = 0
            ck_ins = 0

            for kw in keywords[:3]: # Try up to first 3 keywords available for the product
                for attempt in range(1, 3): # Retry up to 2 times per keyword
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
                        ck_ins = db_stats.get("competitor_keywords_inserted", 0)
                        top_comp_count = res.get("top_competitors_count", 0)

                        if top_comp_count > 0 or cp_ins > 0:
                            total_cp_inserted += cp_ins
                            total_ck_inserted += ck_ins
                            print(
                                f"[{idx}/{total_in_batch}] Product ID: {product.id} | ASIN: {product.asin} | status: SUCCESS | competitor products inserted: {cp_ins} | competitor keywords inserted: {ck_ins}",
                                flush=True
                            )
                            successful_count += 1
                            success = True
                            break
                        else:
                            print(f"   [INFO] Keyword '{kw.keyword}' returned 0 competitor results. Trying next keyword...", flush=True)
                            break
                    except Exception as exc:
                        db.rollback()
                        print(f"   [ATTEMPT {attempt}/2 FAILED] Keyword '{kw.keyword}' Error: {exc}", flush=True)
                        if attempt < 2:
                            time.sleep(3.0)

                if success:
                    break

            if not success:
                print(
                    f"[{idx}/{total_in_batch}] Product ID: {product.id} | ASIN: {product.asin} | status: FAILED | competitor products: 0 | competitor keywords: 0",
                    flush=True
                )
                failed_count += 1

            # Pause between scraping calls to avoid throttling
            time.sleep(1.0)

        # Step 4: Final Summary Report
        print("\n" + "=" * 90, flush=True)
        print("FINAL BATCH 6 SCRAPING SUMMARY REPORT (IDs 1201 - 1400)", flush=True)
        print("=" * 90, flush=True)
        print(f"Total Products                     : {total_in_batch}", flush=True)
        print(f"Successfully Scraped               : {successful_count}", flush=True)
        print(f"Already Completed/Skipped          : {skipped_count}", flush=True)
        print(f"Failed                             : {failed_count}", flush=True)
        print(f"Total Competitor Products Inserted : {total_cp_inserted}", flush=True)
        print(f"Total Competitor Keywords Inserted : {total_ck_inserted}", flush=True)
        print("=" * 90 + "\n", flush=True)

    finally:
        db.close()


if __name__ == "__main__":
    main()
