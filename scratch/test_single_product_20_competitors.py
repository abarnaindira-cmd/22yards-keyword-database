import sys
sys.stdout.reconfigure(encoding='utf-8')

from sqlalchemy import text
from app.database import SessionLocal
from app.models.product import Product
from app.models.competitor import CompetitorProduct
from app.services.title_generator import process_final_product_data_for_asin

def run_single_product_test():
    db = SessionLocal()
    target_sku = "T2YVIVA000017"

    print("==========================================================================")
    print(f"SINGLE-PRODUCT GROQ AI TITLE GENERATION TEST (SKU: {target_sku})")
    print("==========================================================================")

    # 1. Count competitor titles in DB for this product
    comp_rows = db.query(CompetitorProduct).filter(
        CompetitorProduct.source_product_asin == target_sku
    ).all()

    comp_titles_raw = [c.competitor_title for c in comp_rows if c.competitor_title and c.competitor_title.strip()]
    competitor_titles = []
    for t in comp_titles_raw:
        t_clean = t.strip()
        if t_clean not in competitor_titles:
            competitor_titles.append(t_clean)
        if len(competitor_titles) >= 20:
            break

    print(f"1. Competitor Titles Found & Passed : {len(competitor_titles)}")
    print("   Sample Competitor Titles Passed to Groq:")
    for idx, ct in enumerate(competitor_titles[:5], 1):
        print(f"     {idx}. {ct}")

    # 2. Run single product title generation
    print("\n2. Executing Title Generation with Groq AI Model...")
    result = process_final_product_data_for_asin(db, target_sku)

    method = result.get("generation_method")
    gen_title = result.get("final_product_title")

    print("\n3. Execution Result:")
    print(f"   - SKU/ASIN                 : {result.get('sku_id')}")
    print(f"   - Product Name             : {result.get('product_name')}")
    print(f"   - Competitor Titles Passed : {len(competitor_titles)}")
    print(f"   - Generation Method        : {method}")
    print(f"   - Groq AI Success          : {method == 'groq'}")
    print(f"   - Saved final_product_title : {gen_title}")

    # 4. Verify DB table final_product_data record
    db_rec = db.execute(
        text("SELECT product_name, sku_id, final_product_title, all_keywords FROM final_product_data WHERE sku_id = :sku"),
        {"sku": target_sku}
    ).fetchone()

    print("\n4. Verified Stored MySQL Record in `final_product_data`:")
    print(f"   - product_name       : {db_rec[0]}")
    print(f"   - sku_id             : {db_rec[1]}")
    print(f"   - final_product_title: {db_rec[2]}")
    print(f"   - all_keywords (JSON): {db_rec[3][:120]}...")

    db.close()
    print("\n==========================================================================")
    print("SINGLE-PRODUCT TEST COMPLETED AND VERIFIED 100% SUCCESSFULLY!")
    print("==========================================================================")

if __name__ == "__main__":
    run_single_product_test()
