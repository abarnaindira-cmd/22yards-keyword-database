import json
from sqlalchemy import text
from app.database import SessionLocal

def audit_target_100():
    db = SessionLocal()

    # Fetch 100 target products (IDs 4 to 103)
    prods = db.execute(text("SELECT id, asin, product_name FROM products ORDER BY id ASC LIMIT 100;")).fetchall()
    target_asins = [p.asin for p in prods if p.asin]

    rows = db.execute(text("""
        SELECT product_name, sku_id, final_product_title, all_keywords 
        FROM final_product_data 
        WHERE sku_id IN :asins
        ORDER BY sku_id ASC;
    """), {"asins": tuple(target_asins)}).fetchall()

    print("==========================================================================")
    print(f"AUDIT REPORT FOR THE 100 TARGET PRODUCTS (Product IDs 4 to 103)")
    print("==========================================================================")

    identical_count = 0
    empty_kw_count = 0
    enhanced_count = 0

    for r in rows:
        p_name = (r[0] or "").strip()
        sku = (r[1] or "").strip()
        f_title = (r[2] or "").strip()
        raw_kws = r[3]

        kws_list = []
        if isinstance(raw_kws, str):
            try:
                kws_list = json.loads(raw_kws)
            except Exception:
                kws_list = [raw_kws] if raw_kws else []
        elif isinstance(raw_kws, list):
            kws_list = raw_kws

        if len(kws_list) == 0:
            empty_kw_count += 1

        if p_name.lower() == f_title.lower():
            identical_count += 1
        else:
            enhanced_count += 1

    print(f"1. Total Target Products Evaluated : {len(rows)} / 100")
    print(f"2. Products with Enhanced Titles   : {enhanced_count} / {len(rows)} ({(enhanced_count/len(rows))*100:.1f}%)")
    print(f"3. Products with Identical Titles  : {identical_count} / {len(rows)}")
    print(f"4. Products with Missing Keywords  : {empty_kw_count} / {len(rows)}")

    print("\nSample Target Product Records:")
    for r in rows[:5]:
        p_name = r[0]
        sku = r[1]
        f_title = r[2]
        kws_len = len(json.loads(r[3]) if isinstance(r[3], str) else r[3])
        print(f"  SKU: {sku:18s} | Kws Count: {kws_len:2d} | Title: {f_title[:70]}...")

    db.close()

if __name__ == "__main__":
    audit_target_100()
