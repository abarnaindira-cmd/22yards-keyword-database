import sys
import os

sys.path.insert(0, r'd:\22yards_keyword_database_competitor_ready\22yards_keyword_database')

from app.database import SessionLocal
from app.models.product import Product
from app.models.final_product_data import FinalProductData
from app.models.competitor import CompetitorProduct
from app.models.keyword import Keyword

def deep_investigate():
    db = SessionLocal()
    try:
        # Range 214 - 2156
        prods = db.query(Product).filter(Product.id >= 214, Product.id <= 2156).order_by(Product.id.asc()).all()
        fpd_dict = {f.sku_id: f for f in db.query(FinalProductData).all()}

        exact_records = []
        for p in prods:
            fpd = fpd_dict.get(p.asin)
            if fpd and fpd.final_product_title == p.product_name:
                exact_records.append((p, fpd))

        print(f"Total Products in Range 214-2156 : {len(prods)}")
        print(f"Total Exact-Name Records        : {len(exact_records)}")
        
        # Check IDs of exact-name records
        exact_ids = [p.id for p, _ in exact_records]
        print(f"ID Range of Exact-Name Records   : Min ID={min(exact_ids)}, Max ID={max(exact_ids)}")
        print(f"First 20 IDs: {exact_ids[:20]}")

        # Check competitor title counts & keywords for all exact records
        zero_comp_count = 0
        has_comp_count = 0
        comp_count_dist = {}

        for p, fpd in exact_records:
            c_count = db.query(CompetitorProduct).filter(CompetitorProduct.source_product_asin == p.asin).count()
            comp_count_dist[c_count] = comp_count_dist.get(c_count, 0) + 1
            if c_count == 0:
                zero_comp_count += 1
            else:
                has_comp_count += 1

        print("\nCOMPETITOR TITLES DISTRIBUTION FOR EXACT-NAME RECORDS:")
        print(f"  - Products with 0 competitor titles : {zero_comp_count}")
        print(f"  - Products with >0 competitor titles: {has_comp_count}")
        print("  - Detailed breakdown (comp_count: record_count):")
        for c_c, r_c in sorted(comp_count_dist.items()):
            print(f"      {c_c:2d} competitor titles: {r_c:3d} products")

    finally:
        db.close()

if __name__ == "__main__":
    deep_investigate()
