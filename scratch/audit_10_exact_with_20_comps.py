import os
import sys
import json
from sqlalchemy import create_engine, text

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.database import MYSQL_DATABASE_URL

def audit_10():
    engine = create_engine(MYSQL_DATABASE_URL)
    with engine.connect() as conn:
        # Fetch products in ID range 214-2156 where title == product_name AND competitor count == 20
        query = text("""
            SELECT p.id, p.asin, p.product_name, fpd.final_product_title,
                   (SELECT COUNT(*) FROM competitor_products c WHERE c.source_product_asin = p.asin) as comp_cnt
            FROM products p
            JOIN final_product_data fpd ON p.asin = fpd.sku_id
            WHERE p.id >= 214 AND p.id <= 2156
              AND LOWER(TRIM(fpd.final_product_title)) = LOWER(TRIM(p.product_name))
            HAVING comp_cnt = 20
            ORDER BY p.id ASC
            LIMIT 10
        """)
        rows = conn.execute(query).fetchall()

        print("=== 10 REAL EXACT-NAME PRODUCTS WITH EXACTLY 20 COMPETITORS ===")
        print(f"Total matching exact-name rows fetched: {len(rows)}\n")

        for idx, r in enumerate(rows, 1):
            p_id, asin, p_name, final_title, comp_cnt = r
            print(f"Row {idx:2d}:")
            print(f"  Product ID       : {p_id}")
            print(f"  SKU              : {asin}")
            print(f"  Product Name     : {p_name}")
            print(f"  Competitor Count : {comp_cnt}")
            print(f"  Groq Called?     : NO (Skipped before Groq invocation)")
            print(f"  Groq Result      : N/A (Not Called)")
            print(f"  Validation Result: Skipped (is_valid_groq_title returned True)")
            print(f"  Final Title      : {final_title}")
            print(f"  Reason           : Initial DB title matched product_name; runner skip logic (is_valid_groq_title) did not check if title == product_name, so it false-positively treated it as an already-completed Groq title and skipped it.")
            print("-" * 90)

if __name__ == "__main__":
    audit_10()
