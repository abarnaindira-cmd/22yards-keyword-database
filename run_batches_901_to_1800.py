import sys
import os
import time

# Ensure UTF-8 output on Windows consoles
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import process_range_901_1200_competitors
import process_range_1201_1500_competitors
import process_range_1500_1800_competitors

from app.database import SessionLocal, init_db
from app.models.product import Product
from app.models.competitor import CompetitorProduct, CompetitorKeyword


def overall_summary():
    init_db()
    db = SessionLocal()
    try:
        batch_products = (
            db.query(Product)
            .filter(Product.id >= 901, Product.id <= 1800)
            .order_by(Product.id.asc())
            .all()
        )
        total_in_range = len(batch_products)
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

        total_cp = db.query(CompetitorProduct).filter(CompetitorProduct.source_product_asin.in_(asins_in_range)).count()
        total_ck = db.query(CompetitorKeyword).filter(CompetitorKeyword.source_product_asin.in_(asins_in_range)).count()

        print("\n" + "=" * 90, flush=True)
        print("GRAND TOTAL SUMMARY REPORT (IDs 901 - 1800 COMBINED)", flush=True)
        print("=" * 90, flush=True)
        print(f"Total Products in Range (IDs 901 - 1800)    : {total_in_range}", flush=True)
        print(f"Total Completed Products in DB               : {total_completed} ({(total_completed/total_in_range)*100:.1f}%)", flush=True)
        print(f"Total Pending Products                       : {total_pending}", flush=True)
        print(f"Total Competitor Products Saved in DB        : {total_cp}", flush=True)
        print(f"Total Competitor Keywords Saved in DB        : {total_ck}", flush=True)
        print("=" * 90 + "\n", flush=True)
    finally:
        db.close()


def main():
    print("#" * 90, flush=True)
    print("STARTING AUTOMATED SEQUENTIAL SCRAPING FOR BATCHES: 901-1200 -> 1201-1500 -> 1501-1800", flush=True)
    print("#" * 90 + "\n", flush=True)

    # Batch 1: 901-1200
    print("\n>>> STARTING BATCH 1: PRODUCTS 901 - 1200 <<<", flush=True)
    process_range_901_1200_competitors.main()
    print(">>> COMPLETED BATCH 1: PRODUCTS 901 - 1200 <<<\n", flush=True)
    time.sleep(2.0)

    # Batch 2: 1201-1500
    print("\n>>> STARTING BATCH 2: PRODUCTS 1201 - 1500 <<<", flush=True)
    process_range_1201_1500_competitors.main()
    print(">>> COMPLETED BATCH 2: PRODUCTS 1201 - 1500 <<<\n", flush=True)
    time.sleep(2.0)

    # Batch 3: 1501-1800
    print("\n>>> STARTING BATCH 3: PRODUCTS 1501 - 1800 <<<", flush=True)
    process_range_1500_1800_competitors.main()
    print(">>> COMPLETED BATCH 3: PRODUCTS 1501 - 1800 <<<\n", flush=True)

    # Grand Summary
    overall_summary()
    print("All requested batches (901-1200, 1201-1500, 1501-1800) have completed successfully.", flush=True)


if __name__ == "__main__":
    main()
