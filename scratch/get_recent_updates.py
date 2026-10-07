import os
import sys
from sqlalchemy import create_engine, text

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.database import MYSQL_DATABASE_URL

def get_recent():
    engine = create_engine(MYSQL_DATABASE_URL)
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT p.id, p.asin, p.product_name, fpd.final_product_title
            FROM products p
            JOIN final_product_data fpd ON p.asin = fpd.sku_id
            WHERE p.id >= 480 AND p.id <= 590
            ORDER BY p.id ASC
        """)).fetchall()

        print("=== PRODUCTS IN RANGE 480 - 590 ===")
        for r in rows:
            p_id, asin, name, title = r
            status_str = "GROQ_SUCCESS" if ("|" not in title and title != "MANUAL_REVIEW_REQUIRED") else ("FAILED" if title == "MANUAL_REVIEW_REQUIRED" else "PENDING_LEGACY_PIPE")
            print(f"ID: {p_id:4d} | SKU: {asin:15s} | Status: {status_str:20s} | Title: {title}")

if __name__ == "__main__":
    get_recent()
