import sys
import os

sys.path.insert(0, r'd:\22yards_keyword_database_competitor_ready\22yards_keyword_database')

from app.database import SessionLocal
from app.models.product import Product
from app.models.competitor import CompetitorProduct
from app.services.title_generator import generate_title_with_groq

def test_exact_groq_calls():
    db = SessionLocal()
    try:
        # Test 5 product IDs known to have exact name in final_product_data
        test_ids = [221, 224, 226, 230, 235]
        
        print("=" * 80)
        print("TESTING LIVE GROQ API CALLS FOR 5 EXACT-NAME PRODUCTS (READ-ONLY TEST)")
        print("=" * 80)

        for p_id in test_ids:
            p = db.query(Product).filter(Product.id == p_id).first()
            if not p:
                continue

            comp_rows = db.query(CompetitorProduct).filter(CompetitorProduct.source_product_asin == p.asin).all()
            comp_titles = [c.competitor_title for c in comp_rows if c.competitor_title and c.competitor_title.strip()][:20]

            print(f"\nProduct ID: {p.id} | ASIN: {p.asin}")
            print(f"Target Product Name : '{p.product_name}'")
            print(f"Competitor Titles   : {len(comp_titles)} available")
            
            # Call Groq live with the exact title generator function
            groq_result = generate_title_with_groq(p.product_name, comp_titles)
            print(f"Groq API Output     : '{groq_result}'")
            print(f"Is Groq Output == Product Name? : {groq_result == p.product_name}")

    finally:
        db.close()

if __name__ == "__main__":
    test_exact_groq_calls()
