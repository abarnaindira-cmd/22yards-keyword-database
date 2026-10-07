import logging
from app.database import SessionLocal
from app.models.product import Product
from app.models.keyword import Keyword
from app.services.flipkart_suggestion_runner import run_flipkart_batch_keyword_collection

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

def main():
    db = SessionLocal()
    try:
        print("==================================================")
        print("      RUNNING 5-PRODUCT FLIPKART BATCH TEST       ")
        print("==================================================")
        
        # Target next 5 pending products
        pending_before = (
            db.query(Product)
            .filter(Product.flipkart_status == 'pending')
            .order_by(Product.id.asc())
            .limit(5)
            .all()
        )
        target_ids = [p.id for p in pending_before]
        print(f"Targeting Product IDs for batch test: {target_ids}\n")
        
        # Run batch execution
        res = run_flipkart_batch_keyword_collection(db, limit=5, delay_seconds=0.5)
        
        # Fetch updated database metrics
        total_prods = db.query(Product).count()
        completed_fk = db.query(Product).filter(Product.flipkart_status == 'completed').count()
        pending_fk = db.query(Product).filter(Product.flipkart_status == 'pending').count()
        failed_fk = db.query(Product).filter(Product.flipkart_status == 'failed').count()
        
        print("\n==================================================")
        print("           BATCH TEST METRICS REPORT              ")
        print("==================================================")
        print(f"Products Processed in Batch:  {res['total_products_processed']}")
        print(f"Successful Products:          {res['successful_products']}")
        print(f"Failed Products in Batch:     {res['failed_products']}")
        print(f"Keywords Collected in Batch:  {res['total_keywords_collected']}")
        print(f"HTTP 403 Responses:           {res['http_403_count']}")
        print(f"Total Retries Attempted:      {res['retries_count']}")
        print("--------------------------------------------------")
        print("DB Flipkart Status Overall Summary:")
        print(f"  - Total Database Products:  {total_prods}")
        print(f"  - Flipkart Completed:       {completed_fk}")
        print(f"  - Flipkart Pending:         {pending_fk}")
        print(f"  - Flipkart Failed:          {failed_fk}")
        print("==================================================\n")
        
        print("Details per product in batch:")
        for item in res['details']:
            print(f"  - Product ID {item['product_id']} ({item['asin_fsn']}): status={item['flipkart_status']}, keywords={item['keywords_collected']}, amazon_status={item['amazon_status']}")

    finally:
        db.close()

if __name__ == "__main__":
    main()
