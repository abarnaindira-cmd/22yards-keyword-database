import os
import sys
import json
from sqlalchemy import create_engine, text

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.database import MYSQL_DATABASE_URL

def get_examples():
    engine = create_engine(MYSQL_DATABASE_URL)
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT p.id, p.asin, p.product_name, fpd.final_product_title, fpd.all_keywords
            FROM products p
            JOIN final_product_data fpd ON p.asin = fpd.sku_id
            WHERE p.id >= 214 AND p.id <= 2156
              AND LOWER(TRIM(fpd.final_product_title)) = LOWER(TRIM(p.product_name))
            ORDER BY p.id ASC
            LIMIT 10
        """)).fetchall()

        for idx, r in enumerate(rows, 1):
            p_id, asin, p_name, final_title, kw_raw = r
            c_cnt = conn.execute(text("SELECT COUNT(*) FROM competitor_products WHERE source_product_asin = :asin"), {"asin": asin}).scalar()
            
            kw_cnt = 0
            if kw_raw is not None:
                if isinstance(kw_raw, list):
                    kw_cnt = len(kw_raw)
                elif isinstance(kw_raw, str):
                    try:
                        kw_cnt = len(json.loads(kw_raw))
                    except:
                        kw_cnt = 0
            else:
                kw_cnt = conn.execute(text("SELECT COUNT(*) FROM keywords WHERE source_product_asin = :asin"), {"asin": asin}).scalar()

            print(f"Example {idx:2d}:")
            print(f"  Product ID            : {p_id}")
            print(f"  SKU                   : {asin}")
            print(f"  Product Name          : {p_name}")
            print(f"  Competitor Title Count: {c_cnt}")
            print(f"  Keyword Count         : {kw_cnt}")
            print(f"  Final Title           : {final_title}")
            print(f"  Actual Reason         : Initial default in DB; skipped by batch runner because is_valid_groq_title() did not check for (title == product_name). Groq API was NEVER called.")
            print("-" * 85)

if __name__ == "__main__":
    get_examples()
