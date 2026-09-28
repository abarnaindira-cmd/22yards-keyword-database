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

TARGET_PRODUCT_IDS = [804, 832, 841, 860, 861, 864, 865]


def verify_initial_state(db, products):
    print("=" * 90, flush=True)
    print("INITIAL MYSQL VERIFICATION FOR 7 TARGET PENDING PRODUCTS", flush=True)
    print("=" * 90, flush=True)
    print(f"{'ID':<6} | {'ASIN':<16} | {'Product Name':<35} | {'Existing CP':<12} | {'Existing CK':<12}", flush=True)
    print("-" * 90, flush=True)
    
    clean = True
    for p in products:
        cp_count = db.query(CompetitorProduct).filter(CompetitorProduct.source_product_asin == p.asin).count()
        ck_count = db.query(CompetitorKeyword).filter(CompetitorKeyword.source_product_asin == p.asin).count()
        print(f"{p.id:<6} | {p.asin:<16} | {p.product_name[:35]:<35} | {cp_count:<12} | {ck_count:<12}", flush=True)
        if cp_count > 0:
            clean = False
            
    print("=" * 90, flush=True)
    if clean:
        print("[CONFIRMED] All 7 target products currently have 0 records in competitor_products.", flush=True)
    else:
        print("[INFO] Checking current records in competitor_products before starting.", flush=True)
    print("=" * 90 + "\n", flush=True)
    return clean


def main():
    init_db()
    db = SessionLocal()
    try:
        # Query target products
        target_products = (
            db.query(Product)
            .filter(Product.id.in_(TARGET_PRODUCT_IDS))
            .order_by(Product.id.asc())
            .all()
        )
        
        if len(target_products) != len(TARGET_PRODUCT_IDS):
            print(f"Warning: Expected {len(TARGET_PRODUCT_IDS)} products, but found {len(target_products)} in database.")
            
        # Step 1: Initial verification in MySQL
        verify_initial_state(db, target_products)
        
        print("=" * 90, flush=True)
        print("STARTING COMPETITOR SCRAPING WORKFLOW FOR 7 PENDING PRODUCTS", flush=True)
        print("=" * 90, flush=True)

        # Step 2: Process products sequentially
        for idx, product in enumerate(target_products, 1):
            # Check if product is already completed in DB
            cp_count_db = db.query(CompetitorProduct).filter(CompetitorProduct.source_product_asin == product.asin).count()
            ck_count_db = db.query(CompetitorKeyword).filter(CompetitorKeyword.source_product_asin == product.asin).count()
            if cp_count_db > 0 or ck_count_db > 0:
                print(
                    f"[{idx}/{len(target_products)}] Product ID: {product.id} | ASIN: {product.asin} | status: ALREADY COMPLETED | competitor products: {cp_count_db} | competitor keywords: {ck_count_db}",
                    flush=True
                )
                continue

            print(
                f"\n[{idx}/{len(target_products)}] Processing Product ID: {product.id} | ASIN: {product.asin} | Name: {product.product_name[:45]}...",
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
            for kw in keywords[:3]: # Try up to first 3 keywords available for the product
                print(f"   Trying Keyword: '{kw.keyword}'", flush=True)
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
                            print(
                                f"[{idx}/{len(target_products)}] Product ID: {product.id} | ASIN: {product.asin} | status: SUCCESS | competitor products inserted: {cp_ins} | competitor keywords inserted: {ck_ins}",
                                flush=True
                            )
                            success = True
                            break
                        else:
                            print(f"   [INFO] Keyword '{kw.keyword}' returned 0 competitor results. Trying next...", flush=True)
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
                    f"[{idx}/{len(target_products)}] Product ID: {product.id} | ASIN: {product.asin} | status: FAILED | competitor products: 0 | competitor keywords: 0",
                    flush=True
                )

            # Pause between scraping calls to avoid throttling
            time.sleep(1.5)

        # Step 3: Post-processing MySQL Verification for all 7 products
        print("\n" + "=" * 90, flush=True)
        print("POST-PROCESSING MYSQL VERIFICATION REPORT FOR ALL 7 PRODUCTS", flush=True)
        print("=" * 90, flush=True)
        print(f"{'Product ID':<10} | {'ASIN':<16} | {'Competitor Products':<20} | {'Competitor Keywords':<20} | {'Status':<10}", flush=True)
        print("-" * 85, flush=True)

        final_success_count = 0
        final_failed_count = 0

        for p in target_products:
            cp_cnt = db.query(CompetitorProduct).filter(CompetitorProduct.source_product_asin == p.asin).count()
            ck_cnt = db.query(CompetitorKeyword).filter(CompetitorKeyword.source_product_asin == p.asin).count()
            
            p_status = "SUCCESS" if (cp_cnt > 0 or ck_cnt > 0) else "FAILED"
            if p_status == "SUCCESS":
                final_success_count += 1
            else:
                final_failed_count += 1

            print(f"{p.id:<10} | {p.asin:<16} | {cp_cnt:<20} | {ck_cnt:<20} | {p_status:<10}", flush=True)

        # Step 4: Final Summary Report
        print("\n" + "=" * 90, flush=True)
        print("FINAL SCRAPING SUMMARY REPORT", flush=True)
        print("=" * 90, flush=True)
        print(f"Total targeted         : {len(target_products)}", flush=True)
        print(f"Successfully completed : {final_success_count}", flush=True)
        print(f"Still pending/failed   : {final_failed_count}", flush=True)
        print("=" * 90 + "\n", flush=True)

    finally:
        db.close()


if __name__ == "__main__":
    main()
