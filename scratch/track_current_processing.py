import os
import sys
import time
from sqlalchemy import create_engine, text

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.database import MYSQL_DATABASE_URL

def track():
    engine = create_engine(MYSQL_DATABASE_URL)

    with engine.connect() as conn:
        def get_titles_dict():
            rows = conn.execute(text("SELECT sku_id, final_product_title FROM final_product_data")).fetchall()
            return {r[0]: r[1] for r in rows}

        t1 = get_titles_dict()
        print("Monitoring database for 15 seconds to catch live updates...")
        time.sleep(15)
        t2 = get_titles_dict()

        diffs = []
        for sku, title2 in t2.items():
            title1 = t1.get(sku)
            if title1 != title2:
                # Fetch product details
                prod = conn.execute(text("SELECT id, product_name FROM products WHERE asin = :asin"), {"asin": sku}).fetchone()
                diffs.append((prod[0] if prod else None, sku, prod[1] if prod else "", title1, title2))

        print(f"\nCaught {len(diffs)} title updates in the last 15 seconds:")
        for p_id, sku, name, old_t, new_t in diffs:
            print(f"  [UPDATED LIVE] Product ID: {p_id} | SKU: {sku}")
            print(f"    Product Name: {name}")
            print(f"    Old Title   : {old_t[:70]}...")
            print(f"    New Groq Title: {new_t}")
            print("-" * 70)

if __name__ == "__main__":
    track()
