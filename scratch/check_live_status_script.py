import os
import sys
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# Ensure project root is in sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import MYSQL_DATABASE_URL

def check_status():
    engine = create_engine(MYSQL_DATABASE_URL)
    with engine.connect() as conn:
        # Check products table total
        total_products = conn.execute(text("SELECT COUNT(*) FROM products")).scalar()
        min_id = conn.execute(text("SELECT MIN(id) FROM products")).scalar()
        max_id = conn.execute(text("SELECT MAX(id) FROM products")).scalar()

        # Check final_product_data table total
        total_fpd = conn.execute(text("SELECT COUNT(*) FROM final_product_data")).scalar()

        # Valid Groq AI titles: not null, not empty, no '|', not MANUAL_REVIEW_REQUIRED
        groq_success = conn.execute(text("""
            SELECT COUNT(*) FROM final_product_data 
            WHERE final_product_title IS NOT NULL 
              AND TRIM(final_product_title) != '' 
              AND final_product_title NOT LIKE '%|%' 
              AND final_product_title != 'MANUAL_REVIEW_REQUIRED'
        """)).scalar()

        # Manual review / failed: 'MANUAL_REVIEW_REQUIRED'
        manual_review_count = conn.execute(text("""
            SELECT COUNT(*) FROM final_product_data 
            WHERE final_product_title = 'MANUAL_REVIEW_REQUIRED'
        """)).scalar()

        # Legacy pipe fallback titles if any
        legacy_pipe_count = conn.execute(text("""
            SELECT COUNT(*) FROM final_product_data 
            WHERE final_product_title LIKE '%|%'
        """)).scalar()

        # Null or empty titles
        empty_title_count = conn.execute(text("""
            SELECT COUNT(*) FROM final_product_data 
            WHERE final_product_title IS NULL OR TRIM(final_product_title) = ''
        """)).scalar()

        # Get all products with their final_product_data status ordered by product id
        rows = conn.execute(text("""
            SELECT p.id, p.asin, p.product_name, p.updated_at, fpd.final_product_title
            FROM products p
            LEFT JOIN final_product_data fpd ON p.asin = fpd.sku_id
            ORDER BY p.id ASC
        """)).fetchall()

        processed_products = []
        pending_products = []
        
        last_processed_prod = None
        last_groq_prod = None

        for r in rows:
            p_id, asin, p_name, updated_at, title = r
            if title is not None and title.strip() != "":
                processed_products.append(r)
                last_processed_prod = r
                if "|" not in title and title != "MANUAL_REVIEW_REQUIRED":
                    last_groq_prod = r
            else:
                pending_products.append(r)

        print("=== DATABASE EXECUTION STATUS SUMMARY ===")
        print(f"Total Products in DB (`products` table): {total_products} (IDs {min_id} to {max_id})")
        print(f"Total Entries in `final_product_data`: {total_fpd}")
        print(f"1. Successful Groq AI Titles : {groq_success}")
        print(f"2. Failed (MANUAL_REVIEW_REQUIRED) : {manual_review_count}")
        print(f"3. Legacy Fallback (| pipe) : {legacy_pipe_count}")
        print(f"4. Empty / Null Titles : {empty_title_count}")
        print(f"Total Processed So Far (with title entry) : {len(processed_products)}")
        print(f"Total Still Pending (no title entry) : {len(pending_products)}")
        print("\n=== LATEST PROCESSED PRODUCT ===")
        if last_processed_prod:
            print(f"Product ID   : {last_processed_prod[0]}")
            print(f"ASIN / SKU   : {last_processed_prod[1]}")
            print(f"Product Name : {last_processed_prod[2]}")
            print(f"Updated At   : {last_processed_prod[3]}")
            print(f"Title Snippet: {last_processed_prod[4][:80]}...")
        
        print("\n=== LATEST SUCCESSFUL GROQ AI TITLE ===")
        if last_groq_prod:
            print(f"Product ID   : {last_groq_prod[0]}")
            print(f"ASIN / SKU   : {last_groq_prod[1]}")
            print(f"Product Name : {last_groq_prod[2]}")
            print(f"Updated At   : {last_groq_prod[3]}")
            print(f"Groq Title   : {last_groq_prod[4]}")

if __name__ == "__main__":
    check_status()
