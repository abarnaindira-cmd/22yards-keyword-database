import sys
import time

sys.path.insert(0, r'd:\22yards_keyword_database')

from app.database import SessionLocal
from app.models.product import Product
from app.models.keyword import Keyword
from app.services.keyword_collector import clean_product_title_to_seeds, collect_amazon_keywords

def main():
    db = SessionLocal()
    try:
        # Target ONLY products with status = 'failed'
        failed_products = db.query(Product).filter(Product.status == "failed").all()
        total_failed_before = len(failed_products)
        
        all_products_count = db.query(Product).count()
        completed_products_count = db.query(Product).filter(Product.status == "completed").count()

        print("=" * 80, flush=True)
        print(f"STARTING FINAL RETRY FOR {total_failed_before} FAILED PRODUCTS", flush=True)
        print("=" * 80, flush=True)
        print(f"Total Products in DB            : {all_products_count}", flush=True)
        print(f"Already Completed Products      : {completed_products_count}", flush=True)
        print(f"Target Failed Products for Retry: {total_failed_before}", flush=True)
        print("=" * 80, flush=True)

        processed_count = 0
        successful_count = 0
        still_failed_count = 0
        newly_inserted_keywords = 0
        error_count = 0
        
        delay_seconds = 0.25

        for idx, product in enumerate(failed_products, 1):
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
                    successful_count += 1
                    newly_inserted_keywords += inserted_for_this_product
                    db.commit()
                else:
                    # 0 suggestions -> keep status as 'failed'
                    product.status = "failed"
                    still_failed_count += 1
                    db.commit()

                if idx % 10 == 0 or idx == total_failed_before:
                    print(
                        f"Processed {processed_count}/{total_failed_before} | "
                        f"Successful: {successful_count} | "
                        f"Still failed: {still_failed_count} | "
                        f"New keywords inserted: {newly_inserted_keywords}",
                        flush=True
                    )

            except Exception as e:
                db.rollback()
                error_count += 1
                product.status = "failed"
                still_failed_count += 1
                try:
                    db.commit()
                except Exception:
                    db.rollback()
                print(f"[ERROR] Product ID {product.id} (ASIN: {product.asin}) failed: {e}", flush=True)

        print("\n" + "=" * 80, flush=True)
        print("RETRY RUN COMPLETED", flush=True)
        print("=" * 80, flush=True)
        print(f"Total failed products targeted : {total_failed_before}", flush=True)
        print(f"Processed                      : {processed_count}", flush=True)
        print(f"Successful (marked completed)  : {successful_count}", flush=True)
        print(f"Still failed                   : {still_failed_count}", flush=True)
        print(f"New keywords inserted          : {newly_inserted_keywords}", flush=True)
        print(f"Errors                         : {error_count}", flush=True)
        print("=" * 80 + "\n", flush=True)

        # Verification Queries
        total_products = db.query(Product).count()
        completed_products = db.query(Product).filter(Product.status == "completed").count()
        failed_products_count = db.query(Product).filter(Product.status == "failed").count()
        total_keywords = db.query(Keyword).count()

        distinct_asins_with_kw = set(r[0] for r in db.query(Keyword.source_product_asin).distinct().all())
        products_with_keywords = db.query(Product).filter(Product.asin.in_(distinct_asins_with_kw)).count()
        failed_without_keywords = db.query(Product).filter(
            Product.status == "failed",
            ~Product.asin.in_(distinct_asins_with_kw)
        ).count()

        print("=" * 80, flush=True)
        print("MYSQL VERIFICATION REPORT", flush=True)
        print("=" * 80, flush=True)
        print(f"- total products                 : {total_products}", flush=True)
        print(f"- completed                      : {completed_products}", flush=True)
        print(f"- failed                         : {failed_products_count}", flush=True)
        print(f"- total keywords                 : {total_keywords}", flush=True)
        print(f"- products with keywords         : {products_with_keywords}", flush=True)
        print(f"- failed products still w/o kw   : {failed_without_keywords}", flush=True)
        print("=" * 80, flush=True)

    finally:
        db.close()

if __name__ == "__main__":
    main()
