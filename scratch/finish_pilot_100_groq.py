import time
import sys
sys.stdout.reconfigure(encoding='utf-8')

from sqlalchemy import text
from app.database import SessionLocal
from app.models.product import Product
from app.models.competitor import CompetitorProduct
from app.services.title_generator import process_final_product_data_for_asin, fallback_generate_title

def sweep_pilot_fallbacks():
    db = SessionLocal()

    # Re-select the exact 100 pilot products
    comp_sql = """
    SELECT source_product_asin, COUNT(DISTINCT competitor_title) AS comp_count
    FROM competitor_products
    WHERE competitor_title IS NOT NULL AND TRIM(competitor_title) != ''
    GROUP BY source_product_asin;
    """
    comp_counts = db.execute(text(comp_sql)).fetchall()
    asin_to_comp = {row[0]: row[1] for row in comp_counts}

    all_prods = db.query(Product).order_by(Product.id.asc()).all()

    prods_20_plus = [p for p in all_prods if asin_to_comp.get(p.asin, 0) >= 20]
    prods_1_to_19 = [p for p in all_prods if 1 <= asin_to_comp.get(p.asin, 0) < 20]

    pilot_prods = prods_20_plus[:70] + prods_1_to_19[:30]
    pilot_asins = [p.asin for p in pilot_prods]

    fpd_rows = db.execute(
        text("SELECT sku_id, product_name, final_product_title, all_keywords FROM final_product_data WHERE sku_id IN :asins"),
        {"asins": tuple(pilot_asins)}
    ).fetchall()

    fallback_asins = []
    for r in fpd_rows:
        sku_id, p_name, final_title, kws_json = r[0], r[1], r[2], r[3]
        import json
        kws = json.loads(kws_json) if isinstance(kws_json, str) else (kws_json or [])
        expected_fb = fallback_generate_title(p_name, kws)
        if final_title == expected_fb:
            fallback_asins.append(sku_id)

    print(f"Sweeping {len(fallback_asins)} pilot fallback products with Groq AI (2.5s sleep)...")
    
    groq_now = 0
    for idx, asin in enumerate(fallback_asins, 1):
        res = process_final_product_data_for_asin(db, asin)
        method = res.get("generation_method")
        print(f"[{idx}/{len(fallback_asins)}] ASIN: {asin} -> Method: {method.upper()} | Title: {res.get('final_product_title')[:75]}...")
        if method == "groq":
            groq_now += 1
        time.sleep(2.5)

    print(f"\nSweep Finished! Groq regenerated: {groq_now}/{len(fallback_asins)}")
    db.close()

if __name__ == "__main__":
    sweep_pilot_fallbacks()
