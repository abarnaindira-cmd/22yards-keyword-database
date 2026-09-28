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
        # Query products strictly in range IDs 901 to 1200
        batch_products = (
            db.query(Product)
            .filter(Product.id >= 901, Product.id <= 1200)
            .order_by(Product.id.asc())
            .all()
        )
        total_in_range = len(batch_products)

        # Identify already completed products from MySQL database
        existing_cp_asins = set(
            r[0] for r in db.query(CompetitorProduct.source_product_asin).distinct().all()
        )
        existing_ck_asins = set(
            r[0] for r in db.query(CompetitorKeyword.source_product_asin).distinct().all()
        )
        already_completed_asins = existing_cp_asins.union(existing_ck_asins)

        already_done_initial = [p for p in batch_products if p.asin in already_completed_asins]
        to_process_initial = [p for p in batch_products if p.asin not in already_completed_asins]

        print("=" * 90, flush=True)
        print("COMPETITOR SCRAPING - PRODUCT RANGE (IDs 901 - 1200)", flush=True)
        print("=" * 90, flush=True)
        print(f"Total Products in Range (IDs 901-1200)       : {total_in_range}", flush=True)
        print(f"Already Completed Products in DB (Skipping)  : {len(already_done_initial)}", flush=True)
        print(f"Pending Products to Process                  : {len(to_process_initial)}", flush=True)
        print("=" * 90 + "\n", flush=True)

        skipped_count = 0
        newly_completed_count = 0
        failed_count = 0
        total_cp_inserted = 0
        total_ck_inserted = 0

        # Process products sequentially
        for idx, product in enumerate(batch_products, 1):
            # Check existing competitor data directly from DB before processing each product
            cp_count = db.query(CompetitorProduct).filter(CompetitorProduct.source_product_asin == product.asin).count()
            ck_count = db.query(CompetitorKeyword).filter(CompetitorKeyword.source_product_asin == product.asin).count()

            if cp_count > 0 or ck_count > 0:
                print(
                    f"[{idx}/{total_in_range}] Product ID: {product.id} | ASIN: {product.asin} | status: SKIPPED (Already Completed) | competitor products: {cp_count} | competitor keywords: {ck_count}",
                    flush=True
                )
                skipped_count += 1
                continue

            print(
                f"[{idx}/{total_in_range}] Processing Product ID: {product.id} | ASIN: {product.asin} | Name: {product.product_name[:45]}...",
                flush=True
            )

            keywords = get_product_keywords(db, product)
            if not keywords:
                # Fallback to product name if no keyword stored in database
                kw_text = product.product_name[:60]
                keywords = [Keyword(
                    id=0,
                    keyword=kw_text,
                    source="auto_fallback",
                    source_product_asin=product.asin,
                    category=product.category
                )]
                print(f"   [INFO] No stored keyword found. Using title fallback: '{kw_text}'", flush=True)

            success = False
            cp_ins = 0
            ck_ins = 0

            # Try up to first 3 keywords available for the product
            for kw in keywords[:3]:
                # Retry up to 2 times per keyword
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
                        ck_ins = db_stats.get("competitor_keywords_inserted", 0)
                        top_comp_count = res.get("top_competitors_count", 0)

                        if top_comp_count > 0 or cp_ins > 0:
                            total_cp_inserted += cp_ins
                            total_ck_inserted += ck_ins
                            print(
                                f"[{idx}/{total_in_range}] Product ID: {product.id} | ASIN: {product.asin} | status: SUCCESS | competitor products inserted: {cp_ins} | competitor keywords inserted: {ck_ins}",
                                flush=True
                            )
                            newly_completed_count += 1
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
                    f"[{idx}/{total_in_range}] Product ID: {product.id} | ASIN: {product.asin} | status: FAILED | competitor products: 0 | competitor keywords: 0",
                    flush=True
                )
                failed_count += 1

            # Pause between scraping calls to avoid throttling
            time.sleep(1.0)

        # Final MySQL Verification and Summary Report
        print("\n" + "=" * 90, flush=True)
        print("VERIFYING MYSQL DATA FOR PRODUCT IDs 901 - 1200", flush=True)
        print("=" * 90, flush=True)

        asins_in_range = [p.asin for p in batch_products]
        cp_asins_final = set(
            r[0] for r in db.query(CompetitorProduct.source_product_asin).filter(CompetitorProduct.source_product_asin.in_(asins_in_range)).distinct().all()
        )
        ck_asins_final = set(
            r[0] for r in db.query(CompetitorKeyword.source_product_asin).filter(CompetitorKeyword.source_product_asin.in_(asins_in_range)).distinct().all()
        )
        completed_asins_final = cp_asins_final.union(ck_asins_final)
        
        total_completed = len(completed_asins_final)
        total_pending = total_in_range - total_completed

        print("=" * 90, flush=True)
        print("FINAL COMPETITOR SCRAPING SUMMARY REPORT (PRODUCT IDs 901 - 1200)", flush=True)
        print("=" * 90, flush=True)
        print(f"Total Products                    : {total_in_range}", flush=True)
        print(f"Completed Products                : {total_completed}", flush=True)
        print(f"Pending Products                  : {total_pending}", flush=True)
        print(f"Failed Products (in this run)     : {failed_count}", flush=True)
        print(f"Competitor Products Inserted (Run): {total_cp_inserted}", flush=True)
        print(f"Competitor Keywords Inserted (Run): {total_ck_inserted}", flush=True)
        print("=" * 90 + "\n", flush=True)

    finally:
        db.close()


if __name__ == "__main__":
    main()
