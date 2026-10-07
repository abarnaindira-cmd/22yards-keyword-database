import sys
sys.stdout.reconfigure(encoding='utf-8')

from sqlalchemy import text
from app.database import SessionLocal
from app.models.product import Product
from app.services.title_generator import process_batch_final_product_data

def process_100_batch():
    db = SessionLocal()

    # Retrieve ASINs for Product IDs 4 to 103 (the 100 uploaded products)
    products = db.query(Product).filter(Product.id.between(4, 103)).order_by(Product.id.asc()).all()
    target_asins = [p.asin for p in products if p.asin]

    print("==========================================================================")
    print(f"PROCESSING BATCH OF {len(target_asins)} UPLOADED PRODUCTS (IDs 4-103)")
    print("==========================================================================")

    res = process_batch_final_product_data(db, target_asins)

    print("\n--- BATCH EXECUTION SUMMARY ---")
    print(f"Total Uploaded Batch Count : {res['total_uploaded']}")
    print(f"Total Processed Count      : {res['total_processed']}")
    print(f"Groq Generated Count       : {res['groq_generated_count']}")
    print(f"Fallback Generated Count   : {res['fallback_generated_count']}")
    print(f"Failed Count               : {res['failed_count']}")

    # Verify count in MySQL final_product_data table
    mysql_count = db.execute(text("SELECT COUNT(*) FROM final_product_data WHERE sku_id IN :asins"), {"asins": tuple(target_asins)}).scalar()
    print(f"Verified MySQL Records in `final_product_data`: {mysql_count}/{len(target_asins)}")

    db.close()
    return res

if __name__ == "__main__":
    process_100_batch()
