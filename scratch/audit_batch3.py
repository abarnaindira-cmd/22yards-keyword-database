import sys
sys.stdout.reconfigure(encoding='utf-8')

from app.database import SessionLocal
from app.models.product import Product
from app.models.keyword import Keyword
from app.models.competitor import CompetitorProduct
from app.models.final_product_data import FinalProductData

def audit_batch3():
    db = SessionLocal()

    b3_prods = db.query(Product).order_by(Product.id.asc()).offset(200).limit(100).all()

    print("==========================================================================")
    print("READ-ONLY AUDIT REPORT: BATCH 3 (PRODUCTS 201-300 / IDs 204 to 303)")
    print("==========================================================================")
    print(f"Total Products in Batch 3: {len(b3_prods)}")
    print(f"First Product: ID {b3_prods[0].id}, SKU: {b3_prods[0].asin}, Name: {b3_prods[0].product_name}")
    print(f"Last Product : ID {b3_prods[-1].id}, SKU: {b3_prods[-1].asin}, Name: {b3_prods[-1].product_name}\n")

    audit_results = []
    comp_dist = {">=20": 0, "1-19": 0, "0": 0}

    for idx, p in enumerate(b3_prods, 201):
        asin = p.asin
        comps = db.query(CompetitorProduct).filter(CompetitorProduct.source_product_asin == asin).all()
        comp_titles = [c.competitor_title.strip() for c in comps if c.competitor_title and c.competitor_title.strip()]
        unique_comp_titles = list(dict.fromkeys(comp_titles))

        kws = db.query(Keyword).filter(Keyword.source_product_asin == asin).all()
        fd = db.query(FinalProductData).filter(FinalProductData.sku_id == asin).first()

        c_count = len(unique_comp_titles)
        if c_count >= 20:
            comp_dist[">=20"] += 1
        elif c_count > 0:
            comp_dist["1-19"] += 1
        else:
            comp_dist["0"] += 1

        title_str = fd.final_product_title if fd else None
        is_fallback_pipe = bool(title_str and " | " in title_str)
        is_same_as_name = bool(title_str and title_str.strip().lower() == p.product_name.strip().lower())

        audit_results.append({
            "product_index": idx,
            "id": p.id,
            "sku": asin,
            "product_name": p.product_name,
            "comp_count": c_count,
            "unique_comp_count": c_count,
            "kw_count": len(kws),
            "fd_exists": bool(fd),
            "title": title_str,
            "is_fallback_pipe": is_fallback_pipe,
            "is_same_as_name": is_same_as_name
        })

    print("--- 1. COMPETITOR TITLE COVERAGE DISTRIBUTION ---")
    print(f"  - >= 20 Competitor Titles : {comp_dist['>=20']} products")
    print(f"  - 1-19 Competitor Titles  : {comp_dist['1-19']} products")
    print(f"  - 0 Competitor Titles     : {comp_dist['0']} products (Flagged for Manual Review)\n")

    print("--- 2. PRODUCTS WITH FEWER THAN 20 COMPETITOR TITLES (1-19 TITLES) ---")
    fewer_20 = [r for r in audit_results if 0 < r["comp_count"] < 20]
    for r in fewer_20:
        print(f"  - SKU: {r['sku']} | ID: {r['id']} | Competitor Titles Available: {r['comp_count']} | Name: {r['product_name'][:40]}")

    print(f"\n--- 3. PRODUCTS WITH 0 COMPETITOR TITLES ---")
    zero_comp = [r for r in audit_results if r["comp_count"] == 0]
    if zero_comp:
        for r in zero_comp:
            print(f"  - SKU: {r['sku']} | ID: {r['id']} | Name: {r['product_name']}")
    else:
        print("  - None! All 100 products in Batch 3 have at least 1 competitor title.")

    print("\n--- 4. EXISTING TITLE GENERATION ANALYSIS IN final_product_data ---")
    pipe_fallbacks = [r for r in audit_results if r["is_fallback_pipe"]]
    name_same = [r for r in audit_results if r["is_same_as_name"]]
    print(f"  - Total records in final_product_data for Batch 3 : {sum(1 for r in audit_results if r['fd_exists'])} / 100")
    print(f"  - Titles containing fallback keyword pipes (' | ')  : {len(pipe_fallbacks)}")
    print(f"  - Titles identical to original product name         : {len(name_same)}")

    db.close()

if __name__ == "__main__":
    audit_batch3()
