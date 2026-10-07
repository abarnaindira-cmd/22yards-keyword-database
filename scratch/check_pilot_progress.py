from sqlalchemy import text
from app.database import SessionLocal

db = SessionLocal()
res = db.execute(text("SELECT COUNT(*) FROM final_product_data WHERE final_product_title NOT LIKE '%|%'")).scalar()
print("Groq generated records in final_product_data:", res)
db.close()
