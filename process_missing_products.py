import sys
import time
import os

sys.path.insert(0, r'd:\22yards_keyword_database')

from app.database import SessionLocal
from app.models.product import Product
from app.models.keyword import Keyword
from app.services.keyword_collector import clean_product_title_to_seeds, collect_amazon_keywords

def main():
    db = SessionLocal()
    try:
        # Step 1: Identify all products and existing ASINs in keywords table
        all_products = db.query(Product).all()
        asins_with_keywords = set(
            r[0] for r in db.query(Keyword.source_product_asin).distinct().all()
        )
        
        # Missing products: Products with 0 keywords in MySQL
        missing_products = [p for p in all_products if p.asin not in asins_with_keywords]
        
        total_missing_before = len(missing_products)
        print("=" * 80, flush=True)
        print(f"STARTING RETRY PROCESS FOR {total_missing_before} PRODUCTS WITHOUT KEYWORDS", flush=True)
        print("=" * 80, flush=True)
        print(f"Total Products in DB            : {len(all_products)}", flush=True)
        print(f"Products Already WITH Keywords   : {len(all_products) - total_missing_before}", flush=True)
        print(f"Total Missing Products before retry: {total_missing_before}", flush=True)
        print("=" * 80, flush=True)
        
        processed_count = 0
        with_kw_count = 0
        zero_kw_count = 0
        newly_inserted_keywords = 0
        error_count = 0
        errors = []
        
        delay_seconds = 0.2
        
        for idx, product in enumerate(missing_products, 1):
            try:
                processed_count += 1
                seeds = clean_product_title_to_seeds(product.product_name, product.category)
                
                all_suggestions = []
                for seed in seeds:
                    suggestions = collect_amazon_keywords(seed)
                    for kw in suggestions:
                        if kw and kw.lower() not in [s.lower() for s in all_suggestions]:
                            all_suggestions.append(kw)
                    if delay_seconds > 0:
                        time.sleep(delay_seconds)
                        
                inserted_for_this_product = 0
                for kw_text in all_suggestions:
                    existing = db.query(Keyword).filter(
                        Keyword.keyword == kw_text,
                        Keyword.source_product_asin == product.asin,
                        Keyword.source == "search_suggestions"
                    ).first()
                    
                    if not existing:
                        new_kw = Keyword(
                            keyword=kw_text,
                            source="search_suggestions",
                            source_product_asin=product.asin,
                            category=product.category,
                            relevance_score=0.0
                        )
                        db.add(new_kw)
                        inserted_for_this_product += 1
                        
                if all_suggestions:
                    product.status = "completed"
                    with_kw_count += 1
                    newly_inserted_keywords += inserted_for_this_product
                    db.commit()
                else:
                    # Keep eligible for retry, do NOT falsely mark as completed
                    product.status = "failed"
                    zero_kw_count += 1
                    db.commit()
                    
                if idx % 25 == 0 or idx == total_missing_before:
                    print(f"[{idx}/{total_missing_before}] Processed: {processed_count} | Keywords Collected: {with_kw_count} | Zero Keywords: {zero_kw_count} | New Keywords Inserted: {newly_inserted_keywords}", flush=True)
                    
            except Exception as e:
                db.rollback()
                error_count += 1
                errors.append((product.asin, str(e)))
                product.status = "failed"
                try:
                    db.commit()
                except Exception:
                    db.rollback()
                print(f"[ERROR] Product ID {product.id} (ASIN: {product.asin}) failed: {e}", flush=True)

        print("\n" + "=" * 80, flush=True)
        print("RETRY RUN SUMMARY LOGGING", flush=True)
        print("=" * 80, flush=True)
        print(f"Total missing products before retry : {total_missing_before}", flush=True)
        print(f"Products processed                 : {processed_count}", flush=True)
        print(f"Products with keywords collected   : {with_kw_count}", flush=True)
        print(f"Products with zero keywords        : {zero_kw_count}", flush=True)
        print(f"Keywords newly inserted            : {newly_inserted_keywords}", flush=True)
        print(f"Errors encountered                 : {error_count}", flush=True)
        print("=" * 80 + "\n", flush=True)

        # Step 2: Final MySQL Verification
        total_products_db = db.query(Product).count()
        distinct_asins_with_kw = set(r[0] for r in db.query(Keyword.source_product_asin).distinct().all())
        products_with_kw_db = db.query(Product).filter(Product.asin.in_(distinct_asins_with_kw)).count()
        products_without_kw_db = total_products_db - products_with_kw_db
        total_keyword_records_db = db.query(Keyword).count()
        
        print("=" * 80, flush=True)
        print("MYSQL VERIFICATION REPORT", flush=True)
        print("=" * 80, flush=True)
        print(f"1. Total products in MySQL       : {total_products_db}", flush=True)
        print(f"2. Products with keywords        : {products_with_kw_db}", flush=True)
        print(f"3. Products without keywords     : {products_without_kw_db}", flush=True)
        print(f"4. Total keyword records in MySQL: {total_keyword_records_db}", flush=True)
        print("=" * 80, flush=True)

    finally:
        db.close()

if __name__ == "__main__":
    main()
