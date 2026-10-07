from sqlalchemy import text
from app.database import SessionLocal
from app.models.product import Product

db = SessionLocal()
products = db.query(Product).filter(Product.id.between(4, 103)).all()
target_asins = [p.asin for p in products if p.asin]

rows = db.execute(text("SELECT sku_id, product_name, final_product_title, all_keywords FROM final_product_data WHERE sku_id IN :asins"), {"asins": tuple(target_asins)}).fetchall()

print("Total records in DB table final_product_data:", len(rows))

fallback_count = 0
groq_count = 0

for r in rows:
    title = r[2] or ""
    if " | " in title:
        fallback_count += 1
    else:
        groq_count += 1

print("Groq generated titles   :", groq_count)
print("Fallback generated titles:", fallback_count)

db.close()
