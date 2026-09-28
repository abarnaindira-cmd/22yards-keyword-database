import sys
import os

sys.path.insert(0, r'd:\22yards_keyword_database')

from app.database import SessionLocal
from app.models.product import Product
from app.services.keyword_collector import clean_product_title_to_seeds, collect_amazon_keywords

def main():
    db = SessionLocal()
    try:
        sample_names = [
            "Vector X Fighter Men's Jacket",
            "Vector X Mens Track Pant",
            "SG HELMET SMARTECH",
            "SS SKY PREMIUM BATTING GLOVES (Kit Product) Youth",
            "Cricket Bat Grip - GRIPPER",
            "Viva Fitness PVC Dumbbell",
            "Ton Pro 9000 Cricket Spike Shoes"
        ]

        products = []
        for name in sample_names:
            p = db.query(Product).filter(Product.product_name == name).first()
            if not p:
                p = db.query(Product).filter(Product.product_name.like(f"%{name[:12]}%")).first()
            if p:
                products.append((p.product_name, p.category))
            else:
                # Default categories if not found
                cat_map = {
                    "Vector X Fighter Men's Jacket": "APPAREL",
                    "Vector X Mens Track Pant": "APPAREL",
                    "SG HELMET SMARTECH": "Cricket Helmet",
                    "SS SKY PREMIUM BATTING GLOVES (Kit Product) Youth": "Batting Gloves",
                    "Cricket Bat Grip - GRIPPER": "Cricket Accessories - Grip",
                    "Viva Fitness PVC Dumbbell": "Gym Training",
                    "Ton Pro 9000 Cricket Spike Shoes": "Shoe"
                }
                products.append((name, cat_map.get(name)))

        print("=" * 80, flush=True)
        print("TESTING IMPROVED SEED GENERATION & KEYWORD COLLECTION ON 7 SAMPLES", flush=True)
        print("=" * 80 + "\n", flush=True)

        for i, (prod_name, cat) in enumerate(products, 1):
            seeds = clean_product_title_to_seeds(prod_name, cat)
            
            print(f"Sample #{i}:", flush=True)
            print(f"  Original Product Name : '{prod_name}'", flush=True)
            print(f"  Category              : '{cat}'", flush=True)
            print(f"  Generated Seeds       : {seeds}", flush=True)
            print(f"  Amazon Suggestions Returned Per Seed:", flush=True)
            
            unique_keywords = []
            for s in seeds:
                res = collect_amazon_keywords(s)
                print(f"    - Seed '{s}': {len(res)} suggestion(s) -> {res}", flush=True)
                for kw in res:
                    if kw and kw.lower() not in [k.lower() for k in unique_keywords]:
                        unique_keywords.append(kw)
                        
            print(f"  Final Unique Keywords ({len(unique_keywords)}): {unique_keywords}", flush=True)
            print("-" * 80 + "\n", flush=True)

    finally:
        db.close()

if __name__ == "__main__":
    main()
