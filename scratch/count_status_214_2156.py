import sys
import os

sys.path.insert(0, r'd:\22yards_keyword_database_competitor_ready\22yards_keyword_database')

from app.database import SessionLocal
from app.models.product import Product
from app.models.final_product_data import FinalProductData

def count_status():
    db = SessionLocal()
    try:
        prods = db.query(Product).filter(Product.id >= 214, Product.id <= 2156).order_by(Product.id.asc()).all()
        fpds = {f.sku_id: f for f in db.query(FinalProductData).all()}

        total = len(prods)
        exact_count = 0
        pipe_count = 0
        groq_count = 0
        missing_fpd = 0

        for p in prods:
            fpd = fpds.get(p.asin)
            if not fpd:
                missing_fpd += 1
                continue
            t = (fpd.final_product_title or "").strip()
            if t == p.product_name.strip():
                exact_count += 1
            elif "|" in t:
                pipe_count += 1
            else:
                groq_count += 1

        print("=" * 60)
        print(f"LIVE DB STATUS FOR PRODUCT IDs 214 - 2156:")
        print("=" * 60)
        print(f"  Total Products in Range       : {total}")
        print(f"  Groq-style AI Generated Titles : {groq_count}")
        print(f"  Legacy Pipe Fallback Titles    : {pipe_count}")
        print(f"  Exact Original Product Names   : {exact_count}")
        print(f"  Missing FPD Records            : {missing_fpd}")
        print("=" * 60)

    finally:
        db.close()

if __name__ == "__main__":
    count_status()
