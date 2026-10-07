import os
import sys
import time
from sqlalchemy import create_engine, text

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.database import MYSQL_DATABASE_URL

def detailed_audit():
    engine = create_engine(MYSQL_DATABASE_URL)
    with engine.connect() as conn:
        # 1. Total products in database
        total_products = conn.execute(text("SELECT COUNT(*) FROM products")).scalar()
        min_id = conn.execute(text("SELECT MIN(id) FROM products")).scalar()
        max_id = conn.execute(text("SELECT MAX(id) FROM products")).scalar()

        # 2. Detailed classification of all 2153 products
        rows = conn.execute(text("""
            SELECT p.id, p.asin, p.product_name, fpd.final_product_title
            FROM products p
            LEFT JOIN final_product_data fpd ON p.asin = fpd.sku_id
            ORDER BY p.id ASC
        """)).fetchall()

        groq_success = []
        manual_review = []
        legacy_pipe = []
        empty_title = []

        for r in rows:
            p_id, asin, p_name, title = r
            if title is None or title.strip() == "":
                empty_title.append(r)
            elif title == "MANUAL_REVIEW_REQUIRED":
                manual_review.append(r)
            elif "|" in title:
                legacy_pipe.append(r)
            else:
                groq_success.append(r)

        print("=== DETAILED DATABASE BREAKDOWN ===")
        print(f"Total Products in DB                : {total_products} (IDs {min_id} to {max_id})")
        print(f"Groq AI Titles (Success)           : {len(groq_success)}")
        print(f"Manual Review Required (Failed)    : {len(manual_review)}")
        print(f"Legacy Pipe Fallbacks (Pending Groq): {len(legacy_pipe)}")
        print(f"Empty/Null Titles (Pending)        : {len(empty_title)}")
        
        # Let's inspect the first 20 legacy pipe titles and last 20 legacy pipe titles to see which IDs are pending
        print("\n=== LEGACY PIPE TITLES RANGE (Pending Groq replacement) ===")
        if legacy_pipe:
            print(f"Count of legacy pipe titles: {len(legacy_pipe)}")
            print(f"First 5 legacy pipe IDs: {[r[0] for r in legacy_pipe[:5]]}")
            print(f"Last 5 legacy pipe IDs: {[r[0] for r in legacy_pipe[-5:]]}")
        else:
            print("No legacy pipe titles remain!")

        print("\n=== GROQ AI TITLES RANGE ===")
        if groq_success:
            print(f"First 5 Groq success IDs: {[r[0] for r in groq_success[:5]]}")
            print(f"Last 10 Groq success IDs: {[r[0] for r in groq_success[-10:]]}")
            print("\nLatest 3 Groq Titles generated:")
            for r in groq_success[-3:]:
                print(f"  - ID {r[0]:4d} | SKU: {r[1]:15s} | Title: {r[3]}")

if __name__ == "__main__":
    detailed_audit()
