from sqlalchemy import text
from app.database import SessionLocal
from app.models.product import Product

db = SessionLocal()
products = db.query(Product).filter(Product.id.between(4, 103)).all()
target_asins = [p.asin for p in products if p.asin]

res = db.execute(text("SELECT COUNT(*), COUNT(CASE WHEN final_product_title NOT LIKE '%|%' THEN 1 END) FROM final_product_data WHERE sku_id IN :asins"), {"asins": tuple(target_asins)}).fetchone()

print("Total target batch records in final_product_data:", res[0])
print("Groq title records (estimated):", res[1])

db.close()
