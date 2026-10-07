import sys
import json
sys.stdout.reconfigure(encoding='utf-8')

from sqlalchemy import text
from app.database import SessionLocal
from app.models.product import Product
from app.models.keyword import Keyword
from app.models.competitor import CompetitorProduct
from app.models.final_product_data import FinalProductData
from app.config import get_groq_api_key, is_groq_configured

def run_preflight_audit():
    db = SessionLocal()

    print("==========================================================================")
    print("READ-ONLY PREFLIGHT AUDIT: ALL PRODUCTS IN DATABASE (marketlens)")
    print("==========================================================================")

    # 1. Groq Configuration Check
    key = get_groq_api_key()
    configured = is_groq_configured()
    masked_preview = f"{key[:4]}...{key[-4:]}" if (key and len(key) >= 8) else "(masked)"

    print("\n[SECTION 1: GROQ API CONFIGURATION CHECK]")
    print(f"  - Groq Configured        : {configured}")
    print(f"  - API Key Present        : {bool(key)}")
    print(f"  - Key Length             : {len(key) if key else 0} characters")
    print(f"  - Key Masked Preview     : {masked_preview}")

    # 2. Total Products & Details Availability
    all_prods = db.query(Product).order_by(Product.id.asc()).all()
    total_prods_count = len(all_prods)

    valid_details_prods = [p for p in all_prods if p.asin and p.product_name and p.product_name.strip()]
    missing_details_prods = [p for p in all_prods if not (p.asin and p.product_name and p.product_name.strip())]

    print("\n[SECTION 2: PRODUCT DETAILS AVAILABILITY]")
    print(f"  - Total Products in Database       : {total_prods_count}")
    print(f"  - Products with Valid Details      : {len(valid_details_prods)}")
    print(f"  - Products Missing Details        : {len(missing_details_prods)}")

    # 3. Competitor Titles Distribution
    print("\n[SECTION 3: COMPETITOR TITLES DISTRIBUTION (Target: 20 titles)]")
    
    # Query count of unique non-empty competitor titles per source_product_asin
    comp_sql = """
    SELECT source_product_asin, COUNT(DISTINCT competitor_title) AS comp_count
    FROM competitor_products
    WHERE competitor_title IS NOT NULL AND TRIM(competitor_title) != ''
    GROUP BY source_product_asin;
    """
    comp_counts_rows = db.execute(text(comp_sql)).fetchall()
    asin_to_comp_count = {row[0]: row[1] for row in comp_counts_rows}

    prods_with_20_or_more = []
    prods_with_1_to_19 = []
    prods_with_zero_comp = []

    for p in valid_details_prods:
        c_count = asin_to_comp_count.get(p.asin, 0)
        if c_count >= 20:
            prods_with_20_or_more.append(p)
        elif c_count > 0:
            prods_with_1_to_19.append((p, c_count))
        else:
            prods_with_zero_comp.append(p)

    print(f"  - Products with >= 20 Competitor Titles : {len(prods_with_20_or_more)}")
    print(f"  - Products with 1-19 Competitor Titles  : {len(prods_with_1_to_19)}")
    print(f"  - Products with 0 Competitor Titles     : {len(prods_with_zero_comp)}")

    # 4. Harvested Keywords Preservation Check
    kw_sql = """
    SELECT source_product_asin, COUNT(DISTINCT keyword) AS kw_count
    FROM keywords
    WHERE keyword IS NOT NULL AND TRIM(keyword) != ''
    GROUP BY source_product_asin;
    """
    kw_counts_rows = db.execute(text(kw_sql)).fetchall()
    asin_to_kw_count = {row[0]: row[1] for row in kw_counts_rows}

    prods_with_kws = [p for p in valid_details_prods if asin_to_kw_count.get(p.asin, 0) > 0]
    prods_without_kws = [p for p in valid_details_prods if asin_to_kw_count.get(p.asin, 0) == 0]

    print("\n[SECTION 4: HARVESTED KEYWORDS PRESERVATION CHECK]")
    print(f"  - Products WITH Harvested Keywords     : {len(prods_with_kws)}")
    print(f"  - Products WITHOUT Harvested Keywords  : {len(prods_without_kws)}")

    # 5. Existing Final Titles Snapshot & Rollback Readiness
    fpd_rows = db.query(FinalProductData).all()
    fpd_asins = {f.sku_id for f in fpd_rows}

    print("\n[SECTION 5: EXISTING FINAL DATA SNAPSHOT & ROLLBACK READINESS]")
    print(f"  - Stored Records in `final_product_data`: {len(fpd_rows)}")
    print(f"  - Products Covered in final_product_data : {len(fpd_asins)}")

    # Save a rollback snapshot file in scratch directory
    backup_data = [
        {
            "sku_id": f.sku_id,
            "product_name": f.product_name,
            "final_product_title": f.final_product_title,
            "all_keywords_count": len(f.all_keywords) if isinstance(f.all_keywords, list) else 0
        }
        for f in fpd_rows
    ]

    backup_filepath = "scratch/preflight_rollback_snapshot.json"
    with open(backup_filepath, "w", encoding="utf-8") as bf:
        json.dump(backup_data, bf, indent=2)

    print(f"  - Saved Rollback Snapshot File           : {backup_filepath} ({len(backup_data)} records)")

    # 6. Bulk Regeneration Summary & Safety Assessment
    print("\n[SECTION 6: BULK REGENERATION SCOPE & SAFETY ASSESSMENT]")
    print(f"  - Total Titles Requiring Groq Generation: {len(valid_details_prods)}")
    print(f"  - High Quality Competitor Context (>=20): {len(prods_with_20_or_more)} products ({len(prods_with_20_or_more)/len(valid_details_prods)*100:.1f}%)")
    print(f"  - Database Safety                        : SAFE (Original product records & keywords untouched)")

    db.close()
    print("\n==========================================================================")
    print("PREFLIGHT AUDIT COMPLETE")
    print("==========================================================================")

if __name__ == "__main__":
    run_preflight_audit()
