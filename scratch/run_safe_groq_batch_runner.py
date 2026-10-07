import os
import sys
import time
import argparse
from typing import List, Dict, Any
from sqlalchemy import text
from sqlalchemy.orm import Session

# Ensure project root is in sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal
from app.models.product import Product
from app.models.final_product_data import FinalProductData
from app.services.title_generator import process_final_product_data_for_asin

def is_valid_groq_title(title: str, product_name: str) -> bool:
    """
    Check if an existing title is a valid Groq AI-generated title.
    Returns True if:
    - title is non-empty
    - title does NOT contain legacy fallback pipe '|'
    - title is NOT 'MANUAL_REVIEW_REQUIRED'
    - title does NOT match original product_name (case-insensitive normalized check)
    """
    if not title or not title.strip():
        return False
    t_clean = title.strip()
    if "|" in t_clean:
        return False
    if t_clean == "MANUAL_REVIEW_REQUIRED":
        return False
    if product_name and t_clean.casefold() == product_name.strip().casefold():
        return False
    return True

def run_safe_groq_batch(start_id: int = 214, limit: int = 2000, batch_size: int = 100, delay_seconds: float = 1.0):
    db: Session = SessionLocal()
    sys.stdout.reconfigure(encoding='utf-8')

    print("=" * 85)
    print(f"FULL SAFE GROQ TITLE GENERATOR BATCH RUNNER")
    print(f"Start Product ID : {start_id}")
    print(f"Limit (Total)    : {limit}")
    print(f"Batch Size       : {batch_size}")
    print(f"Per-Call Delay   : {delay_seconds}s")
    print("=" * 85)

    # Fetch candidate products starting from start_id
    products = db.query(Product).filter(
        Product.id >= start_id
    ).order_by(Product.id.asc()).limit(limit).all()

    total_candidates = len(products)
    print(f"Total Candidate Products Fetched: {total_candidates}\n")

    if total_candidates == 0:
        print("No products found matching criteria.")
        db.close()
        return

    successful_count = 0
    failed_count = 0
    skipped_count = 0

    current_batch_num = 1
    batch_items_processed = 0
    batch_start_id = products[0].id
    batch_successful = 0
    batch_failed = 0
    batch_skipped = 0

    print(f"--- STARTING BATCH #{current_batch_num} (Starting ID: {batch_start_id}) ---")

    for idx, prod in enumerate(products, 1):
        p_id = prod.id
        sku_id = prod.asin
        p_name = prod.product_name

        # Check existing final_product_data
        existing_fpd = db.query(FinalProductData).filter(FinalProductData.sku_id == sku_id).first()
        existing_title = existing_fpd.final_product_title if existing_fpd else ""

        if is_valid_groq_title(existing_title, p_name):
            skipped_count += 1
            batch_skipped += 1
            batch_items_processed += 1
            print(f"[{idx}/{total_candidates}] [SKIPPED] ID: {p_id:4d} | SKU: {sku_id:16s} | Existing Groq Title Present")

            if batch_items_processed >= batch_size or idx == total_candidates:
                batch_end_id = p_id
                remaining = total_candidates - idx
                print("\n" + "-" * 85)
                print(f"BATCH #{current_batch_num} SUMMARY (IDs {batch_start_id} to {batch_end_id}):")
                print(f"  IDs Processed Range : {batch_start_id} - {batch_end_id} ({batch_items_processed} products)")
                print(f"  Groq Success Count  : {batch_successful}")
                print(f"  Failed Count        : {batch_failed}")
                print(f"  Skipped Count       : {batch_skipped}")
                print(f"  Remaining Count     : {remaining}")
                print("-" * 85 + "\n")

                if idx < total_candidates:
                    current_batch_num += 1
                    batch_items_processed = 0
                    batch_start_id = products[idx].id
                    batch_successful = 0
                    batch_failed = 0
                    batch_skipped = 0
                    print(f"--- STARTING BATCH #{current_batch_num} (Starting ID: {batch_start_id}) ---")
            continue

        # Process through existing Groq title generator service
        try:
            res = process_final_product_data_for_asin(db, sku_id)
            gen_method = res.get("generation_method")
            final_title = res.get("final_product_title", "")

            if gen_method == "groq" and final_title and "|" not in final_title and final_title != "MANUAL_REVIEW_REQUIRED":
                successful_count += 1
                batch_successful += 1
                print(f"[{idx}/{total_candidates}] [SUCCESS] ID: {p_id:4d} | SKU: {sku_id:16s} | Groq Title: {final_title}")
            else:
                failed_count += 1
                batch_failed += 1
                reason = res.get("error") or f"Groq generation returned method '{gen_method}' or title '{final_title}'"
                print(f"[{idx}/{total_candidates}] [FAILED]  ID: {p_id:4d} | SKU: {sku_id:16s} | Reason: {reason}")
        except Exception as e:
            failed_count += 1
            batch_failed += 1
            print(f"[{idx}/{total_candidates}] [EXCEPTION] ID: {p_id:4d} | SKU: {sku_id:16s} | Exception: {str(e)}")

        batch_items_processed += 1

        # Rate limit delay between Groq API calls
        if delay_seconds > 0:
            time.sleep(delay_seconds)

        if batch_items_processed >= batch_size or idx == total_candidates:
            batch_end_id = p_id
            remaining = total_candidates - idx
            print("\n" + "-" * 85)
            print(f"BATCH #{current_batch_num} SUMMARY (IDs {batch_start_id} to {batch_end_id}):")
            print(f"  IDs Processed Range : {batch_start_id} - {batch_end_id} ({batch_items_processed} products)")
            print(f"  Groq Success Count  : {batch_successful}")
            print(f"  Failed Count        : {batch_failed}")
            print(f"  Skipped Count       : {batch_skipped}")
            print(f"  Remaining Count     : {remaining}")
            print("-" * 85 + "\n")

            if idx < total_candidates:
                current_batch_num += 1
                batch_items_processed = 0
                batch_start_id = products[idx].id
                batch_successful = 0
                batch_failed = 0
                batch_skipped = 0
                print(f"--- STARTING BATCH #{current_batch_num} (Starting ID: {batch_start_id}) ---")

    print("\n" + "=" * 85)
    print("FULL RUN COMPLETE SUMMARY")
    print("=" * 85)
    print(f"Total Products Evaluated : {total_candidates}")
    print(f"Successful Groq Titles   : {successful_count}")
    print(f"Failed Products          : {failed_count}")
    print(f"Skipped Products         : {skipped_count}")
    print("=" * 85)

    db.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Full Safe Groq Title Generator Batch Runner")
    parser.add_argument("--start-id", type=int, default=214, help="Starting Product ID (default: 214)")
    parser.add_argument("--limit", type=int, default=2000, help="Total products to process in this run (default: 2000)")
    parser.add_argument("--batch-size", type=int, default=100, help="Batch size for summary output (default: 100)")
    parser.add_argument("--delay", type=float, default=1.0, help="Delay in seconds between Groq API calls (default: 1.0)")
    args = parser.parse_args()

    run_safe_groq_batch(start_id=args.start_id, limit=args.limit, batch_size=args.batch_size, delay_seconds=args.delay)
