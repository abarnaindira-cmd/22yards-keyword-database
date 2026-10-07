import sys
import os
import argparse
import logging

# Ensure workspace root is in python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.database import SessionLocal, SessionFlipkart
from app.models.product import Product
from app.models.keyword import Keyword
from app.services.flipkart_suggestion_runner import (
    collect_flipkart_keywords_for_product,
    RETRIES_STATS
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("flipkart_batch_runner")

def run_controlled_flipkart_batch(batch_limit: int = 50, delay_seconds: float = 0.5):
    db_main = SessionLocal()
    db_fk = SessionFlipkart()

    try:
        # 1. Verify current status before starting
        total_prods = db_main.query(Product).count()
        completed_prods = db_main.query(Product).filter(Product.flipkart_status == 'completed').count()
        failed_prods = db_main.query(Product).filter(Product.flipkart_status == 'failed').count()
        pending_prods = db_main.query(Product).filter(Product.flipkart_status == 'pending').count()

        print("\n==================================================")
        print(" INITIAL MYSQL FLIPKART DATABASE STATUS VERIFICATION")
        print("==================================================")
        print(f" Total Products:                     {total_prods:,}")
        print(f" Already Completed (Skipped):        {completed_prods:,}")
        print(f" Previously Failed (Skipped):        {failed_prods:,}")
        print(f" Flipkart Pending (To Process):      {pending_prods:,}")
        print("==================================================\n")

        if pending_prods == 0:
            print("No pending Flipkart products found to process.")
            return

        # Reset retry stats for this batch
        RETRIES_STATS["403_responses"] = 0
        RETRIES_STATS["total_retries"] = 0

        # Query ONLY pending products ordered by ID asc
        pending_list = (
            db_main.query(Product)
            .filter(Product.flipkart_status == "pending")
            .order_by(Product.id.asc())
            .limit(batch_limit)
            .all()
        )

        batch_count = len(pending_list)
        print(f"Starting controlled batch execution for {batch_count} pending Flipkart product(s)...\n")

        successful_in_batch = 0
        failed_in_batch = 0
        keywords_in_batch = 0

        for idx, prod_main in enumerate(pending_list, start=1):
            prod_fk = db_fk.query(Product).filter(Product.id == prod_main.id).first()
            if not prod_fk:
                prod_fk = db_fk.query(Product).filter(Product.asin == prod_main.asin).first()

            try:
                # Run collection on db_fk
                kws = collect_flipkart_keywords_for_product(db_fk, prod_fk or prod_main, delay_seconds=delay_seconds)
                kw_cnt = len(kws)

                # Sync status and keywords to main DB as well
                if kw_cnt > 0:
                    prod_main.flipkart_status = "completed"
                    if prod_fk:
                        prod_fk.flipkart_status = "completed"
                    successful_in_batch += 1
                    keywords_in_batch += kw_cnt

                    # Ensure keywords are also stored in db_main if missing
                    for kw_item in kws:
                        ex_main = db_main.query(Keyword).filter(
                            Keyword.keyword == kw_item.keyword,
                            Keyword.source_product_asin == prod_main.asin,
                            Keyword.marketplace == "flipkart",
                            Keyword.source == "flipkart_search_suggestions"
                        ).first()
                        if not ex_main:
                            new_main_kw = Keyword(
                                keyword=kw_item.keyword,
                                source="flipkart_search_suggestions",
                                source_product_asin=prod_main.asin,
                                category=prod_main.category,
                                marketplace="flipkart",
                                relevance_score=kw_item.relevance_score
                            )
                            db_main.add(new_main_kw)
                else:
                    prod_main.flipkart_status = "failed"
                    if prod_fk:
                        prod_fk.flipkart_status = "failed"
                    failed_in_batch += 1

                db_main.commit()
                if prod_fk:
                    db_fk.commit()

                status_label = "Completed" if kw_cnt > 0 else "Failed/No-Keywords"
                print(f"[{idx}/{batch_count}] Product ID {prod_main.id} ({prod_main.asin}) - {status_label}: {kw_cnt} keywords collected.")

            except Exception as err:
                db_main.rollback()
                db_fk.rollback()
                prod_main.flipkart_status = "failed"
                if prod_fk:
                    prod_fk.flipkart_status = "failed"
                try:
                    db_main.commit()
                    if prod_fk:
                        db_fk.commit()
                except Exception:
                    pass
                failed_in_batch += 1
                print(f"[{idx}/{batch_count}] Product ID {prod_main.id} ({prod_main.asin}) - Error: {err}")

        # Compute remaining pending products
        rem_pending = db_main.query(Product).filter(Product.flipkart_status == 'pending').count()
        tot_completed = db_main.query(Product).filter(Product.flipkart_status == 'completed').count()

        print("\n==================================================")
        print(" BATCH EXECUTION SUMMARY REPORT")
        print("==================================================")
        print(f" Products Processed in Batch:        {batch_count}")
        print(f" Successful Products (Completed):    {successful_in_batch}")
        print(f" Failed / No-Keyword Products:      {failed_in_batch}")
        print(f" Keywords Collected in Batch:        {keywords_in_batch}")
        print(f" HTTP 403 Responses:                 {RETRIES_STATS['403_responses']}")
        print(f" Total Retry Count:                  {RETRIES_STATS['total_retries']}")
        print(f" Remaining Flipkart Pending:         {rem_pending:,}")
        print(f" Total Completed in Database:        {tot_completed:,}")
        print("==================================================\n")

    finally:
        db_main.close()
        db_fk.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run controlled Flipkart keyword collection batch.")
    parser.add_argument("--limit", type=int, default=50, help="Number of pending products to process in this batch (default: 50)")
    parser.add_argument("--delay", type=float, default=0.5, help="Delay in seconds between request seeds (default: 0.5)")
    args = parser.parse_args()

    run_controlled_flipkart_batch(batch_limit=args.limit, delay_seconds=args.delay)
