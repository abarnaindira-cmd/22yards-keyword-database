import sys
sys.stdout.reconfigure(encoding='utf-8')

from sqlalchemy import text
from app.database import SessionLocal
from app.models.product import Product
from app.services.title_generator import process_final_product_data_for_asin

db = SessionLocal()

products = db.query(Product).filter(Product.id.between(4, 103)).all()
target_asins = [p.asin for p in products if p.asin]

rows = db.execute(
    text("SELECT sku_id, final_product_title FROM final_product_data WHERE sku_id IN :asins"),
    {"asins": tuple(target_asins)}
).fetchall()

for r in rows:
    if " | " in (r[1] or ""):
        print("Fallback ASIN:", r[0])
        res = process_final_product_data_for_asin(db, r[0])
        print("Result:", res)

db.close()
