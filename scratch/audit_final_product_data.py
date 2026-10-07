import json
from sqlalchemy import text
from app.database import SessionLocal
from app.config import get_groq_api_key, is_groq_configured

def run_audit():
    db = SessionLocal()

    print("==========================================================================")
    print("AUDIT REPORT: FINAL_PRODUCT_DATA TABLE & GROQ GENERATION WORKFLOW")
    print("==========================================================================")

    # Check Groq API Key configuration status
    groq_key = get_groq_api_key()
    groq_active = is_groq_configured()
    print("1. GROQ API KEY CONFIGURATION STATUS:")
    print(f"   - GROQ_API_KEY present: {bool(groq_key)}")
    print(f"   - GROQ_API_KEY length : {len(groq_key) if groq_key else 0}")
    print(f"   - Is Groq Active      : {groq_active}")

    # Query all final_product_data rows
    rows = db.execute(text("SELECT product_name, sku_id, final_product_title, all_keywords FROM final_product_data")).fetchall()
    total_records = len(rows)
    print(f"\n2. TOTAL RECORDS IN `final_product_data`: {total_records}")

    identical_title_count = 0
    empty_keywords_count = 0
    identical_title_with_keywords = 0
    identical_title_no_keywords = 0
    title_enhanced_count = 0

    for r in rows:
        p_name = (r[0] or "").strip()
        sku = (r[1] or "").strip()
        f_title = (r[2] or "").strip()
        raw_kws = r[3]

        # Parse keywords list
        kws_list = []
        if isinstance(raw_kws, str):
            try:
                kws_list = json.loads(raw_kws)
            except Exception:
                kws_list = [raw_kws] if raw_kws else []
        elif isinstance(raw_kws, list):
            kws_list = raw_kws

        has_keywords = len(kws_list) > 0
        if not has_keywords:
            empty_keywords_count += 1

        is_identical = (p_name.lower() == f_title.lower())
        if is_identical:
            identical_title_count += 1
            if has_keywords:
                identical_title_with_keywords += 1
            else:
                identical_title_no_keywords += 1
        else:
            title_enhanced_count += 1

    print("\n3. DETAILED BREAKDOWN OF TITLES & KEYWORDS:")
    print(f"   a) Products where `final_product_title` is IDENTICAL to `product_name`: {identical_title_count} / {total_records} ({(identical_title_count/total_records)*100:.1f}%)")
    print(f"      - Identical title AND missing/empty keywords: {identical_title_no_keywords}")
    print(f"      - Identical title BUT has harvested keywords  : {identical_title_with_keywords}")
    print(f"   b) Products with ENHANCED `final_product_title` (Different from product_name): {title_enhanced_count} / {total_records} ({(title_enhanced_count/total_records)*100:.1f}%)")
    print(f"   c) Products with MISSING / EMPTY `all_keywords` ([]): {empty_keywords_count} / {total_records} ({(empty_keywords_count/total_records)*100:.1f}%)")

    # Check underlying `keywords` table in MySQL
    kw_products_count = db.execute(text("SELECT COUNT(DISTINCT source_product_asin) FROM keywords")).scalar()
    total_products_count = db.execute(text("SELECT COUNT(*) FROM products")).scalar()
    print(f"\n4. UNDERLYING `keywords` TABLE COVERAGE:")
    print(f"   - Total products in `products` table       : {total_products_count}")
    print(f"   - Products with records in `keywords` table: {kw_products_count}")
    print(f"   - Products without any keywords in DB      : {total_products_count - kw_products_count}")

    # Inspect sample records of each category
    print("\n5. SAMPLE RECORDS FOR AUDIT:")

    # Category A: Identical title, no keywords
    sample_cat_a = [r for r in rows if r[0].strip().lower() == r[2].strip().lower() and not r[3]]
    if sample_cat_a:
        print("\n   [Sample Category A: Identical title, 0 keywords in DB]")
        for s in sample_cat_a[:3]:
            print(f"     SKU: {s[1]} | Name: {s[0]}")

    # Category B: Identical title, BUT has keywords
    sample_cat_b = [r for r in rows if r[0].strip().lower() == r[2].strip().lower() and r[3] and len(json.loads(r[3]) if isinstance(r[3], str) else r[3]) > 0]
    if sample_cat_b:
        print("\n   [Sample Category B: Identical title, BUT has keywords]")
        for s in sample_cat_b[:3]:
            print(f"     SKU: {s[1]} | Name: {s[0]} | Kws: {s[3][:60]}")

    # Category C: Enhanced title
    sample_cat_c = [r for r in rows if r[0].strip().lower() != r[2].strip().lower()]
    if sample_cat_c:
        print("\n   [Sample Category C: Enhanced title with keywords]")
        for s in sample_cat_c[:3]:
            print(f"     SKU: {s[1]}")
            print(f"       Name : {s[0]}")
            print(f"       Title: {s[2]}")

    db.close()
    print("\n==========================================================================")
    print("AUDIT COMPLETED SUCCESSFULLY.")
    print("==========================================================================")

if __name__ == "__main__":
    run_audit()
