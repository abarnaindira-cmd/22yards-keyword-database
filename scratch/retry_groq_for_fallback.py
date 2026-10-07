import sys
import time
sys.stdout.reconfigure(encoding='utf-8')

from sqlalchemy import text
from app.database import SessionLocal
from app.models.product import Product
from app.services.title_generator import process_final_product_data_for_asin

def retry_fallback_products():
    db = SessionLocal()

    products = db.query(Product).filter(Product.id.between(4, 103)).all()
    target_asins = [p.asin for p in products if p.asin]

    rows = db.execute(text("SELECT sku_id, final_product_title FROM final_product_data WHERE sku_id IN :asins"), {"asins": tuple(target_asins)}).fetchall()

    fallback_asins = [r[0] for r in rows if " | " in (r[1] or "")]

    print("==========================================================================")
    print(f"RETRYING GROQ TITLE GENERATION FOR {len(fallback_asins)} FALLBACK PRODUCTS")
    print("==========================================================================")

    groq_success = 0
    still_fallback = 0

    for idx, asin in enumerate(fallback_asins, 1):
        res = process_final_product_data_for_asin(db, asin)
        method = res.get("generation_method")
        print(f"[{idx}/{len(fallback_asins)}] ASIN: {asin} -> Method: {method} | Title: {res.get('final_product_title')}")
        if method == "groq":
            groq_success += 1
        else:
            still_fallback += 1
        time.sleep(2.0)

    print("\n--- RETRY SUMMARY ---")
    print(f"Total Retried         : {len(fallback_asins)}")
    print(f"Now Groq Generated    : {groq_success}")
    print(f"Still Fallback        : {still_fallback}")

    db.close()

if __name__ == "__main__":
    retry_fallback_products()
