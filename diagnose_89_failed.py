import sys
import os

sys.path.insert(0, r"d:\22yards_keyword_database_competitor_ready\22yards_keyword_database")

from app.database import SessionLocal
from app.models.product import Product
from app.services.flipkart_suggestion_runner import clean_flipkart_title_to_seeds

def main():
    db = SessionLocal()
    failed_prods = db.query(Product).filter(Product.flipkart_status == 'failed').order_by(Product.id.asc()).all()

    print(f"TOTAL FAILED PRODUCTS TO DIAGNOSE: {len(failed_prods)}")
    print("=" * 110)
    for idx, p in enumerate(failed_prods, 1):
        seeds = clean_flipkart_title_to_seeds(p.product_name, p.category)
        if not seeds:
            seeds = [p.product_name]
        cat_str = p.category if p.category else "N/A"
        print(f"[{idx:2d}/89] ID: {p.id:<5d} | FSN: {p.asin:<18s} | Category: {cat_str:<18s}")
        print(f"       Name:  {p.product_name}")
        print(f"       Seeds: {seeds}")
        print("-" * 110)
    print("=" * 110)
    db.close()

if __name__ == "__main__":
    main()
