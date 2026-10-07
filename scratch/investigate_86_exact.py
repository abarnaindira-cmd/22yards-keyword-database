import sys
import os

sys.path.insert(0, r'd:\22yards_keyword_database_competitor_ready\22yards_keyword_database')

from app.database import SessionLocal
from app.models.product import Product
from app.models.final_product_data import FinalProductData
from app.models.competitor import CompetitorProduct
from app.models.keyword import Keyword

def investigate():
    db = SessionLocal()
    try:
        prods = db.query(Product).filter(Product.id >= 214, Product.id <= 2156).order_by(Product.id.asc()).all()
        print(f"Total Products fetched in range 214-2156: {len(prods)}")

        fpds = {f.sku_id: f for f in db.query(FinalProductData).all()}

        exact_match_list = []
        pipe_list = []
        groq_list = []
        manual_review_list = []

        for p in prods:
            fpd = fpds.get(p.asin)
            if not fpd:
                continue
            title = fpd.final_product_title or ""
            if title == p.product_name:
                exact_match_list.append((p, fpd))
            elif "|" in title:
                pipe_list.append((p, fpd))
            elif title == "MANUAL_REVIEW_REQUIRED":
                manual_review_list.append((p, fpd))
            else:
                groq_list.append((p, fpd))

        print(f"Exact Original Product Name Count: {len(exact_match_list)}")
        print(f"Pipe Legacy Fallback Title Count  : {len(pipe_list)}")
        print(f"Groq AI Generated Title Count    : {len(groq_list)}")
        print(f"Manual Review Required Count     : {len(manual_review_list)}")

        print("\n" + "=" * 80)
        print("EXACT ORIGINAL PRODUCT NAME INVESTIGATION (sample of 10):")
        print("=" * 80)

        for p, fpd in exact_match_list[:10]:
            comps = db.query(CompetitorProduct).filter(CompetitorProduct.source_product_asin == p.asin).all()
            kws = db.query(Keyword).filter(Keyword.source_product_asin == p.asin).all()
            comp_titles = [c.competitor_title for c in comps if c.competitor_title and c.competitor_title.strip()]
            
            print(f"Product ID: {p.id:4d} | SKU/ASIN: {p.asin:16s}")
            print(f"  Product Name                : '{p.product_name}'")
            print(f"  Final Product Title in FPD  : '{fpd.final_product_title}'")
            print(f"  Raw Competitor Titles Count : {len(comp_titles)}")
            print(f"  Keywords Count in `keywords`: {len(kws)}")
            print(f"  Keywords Count in FPD JSON  : {len(fpd.all_keywords) if fpd.all_keywords else 0}")
            if comp_titles:
                print(f"  First 2 Competitor Titles   : {comp_titles[:2]}")
            print("-" * 80)

    finally:
        db.close()

if __name__ == "__main__":
    investigate()
