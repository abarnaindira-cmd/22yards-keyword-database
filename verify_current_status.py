import sys

sys.path.insert(0, r'd:\22yards_keyword_database')

from app.database import SessionLocal
from app.models.product import Product
from app.models.keyword import Keyword

def check_db():
    db = SessionLocal()
    try:
        total_products = db.query(Product).count()
        completed_products = db.query(Product).filter(Product.status == "completed").count()
        failed_products = db.query(Product).filter(Product.status == "failed").count()
        pending_products = db.query(Product).filter(Product.status == "pending").count()
        total_keywords = db.query(Keyword).count()
        
        distinct_asins_with_kw = set(r[0] for r in db.query(Keyword.source_product_asin).distinct().all())
        products_with_keywords = db.query(Product).filter(Product.asin.in_(distinct_asins_with_kw)).count()
        failed_with_keywords = db.query(Product).filter(Product.status == "failed", Product.asin.in_(distinct_asins_with_kw)).count()
        
        print("=" * 80)
        print("CURRENT MYSQL DATABASE STATUS")
        print("=" * 80)
        print(f"Total Products in DB             : {total_products}")
        print(f"Completed Products (status='completed') : {completed_products}")
        print(f"Failed Products (status='failed')       : {failed_products}")
        print(f"Pending Products (status='pending')     : {pending_products}")
        print(f"Total Keyword Records            : {total_keywords}")
        print(f"Products with Keywords           : {products_with_keywords}")
        print(f"Failed Products with Keywords    : {failed_with_keywords}")
        print("=" * 80)
        
        print(f"Confirmed failed products to process: {failed_products}")

    finally:
        db.close()

if __name__ == "__main__":
    check_db()
