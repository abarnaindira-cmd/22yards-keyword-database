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
        print("      RUNNING BATCH OF 28 PENDING FLIPKART PRODS  ")
        print("==================================================")
        
        # Snapshot targeted pending products and their Amazon properties before processing
        pending_products = (
            db.query(Product)
            .filter(Product.flipkart_status == 'pending')
            .order_by(Product.id.asc())
            .limit(28)
            .all()
        )
        
        if not pending_products:
            print("No pending Flipkart products found in database.")
            return

        target_ids = [p.id for p in pending_products]
        amazon_before = {p.id: {"marketplace": p.marketplace, "status": p.status, "asin": p.asin} for p in pending_products}
        
        print(f"Targeting {len(target_ids)} pending products (ID range: {target_ids[0]} to {target_ids[-1]})...\n")

        # Run batch collection with limit=28
        res = run_flipkart_batch_keyword_collection(db, limit=28, delay_seconds=0.5)

        # Verification of Amazon data preservation
        amazon_intact = True
        for pid in target_ids:
            p = db.query(Product).filter(Product.id == pid).first()
            before = amazon_before[pid]
            if p.marketplace != before["marketplace"] or p.status != before["status"]:
                amazon_intact = False
                print(f"WARNING: Amazon attributes modified for Product ID {p.id}!")

        # Query overall status counts from MySQL
        total_prods = db.query(Product).count()
        completed_fk = db.query(Product).filter(Product.flipkart_status == 'completed').count()
        pending_fk = db.query(Product).filter(Product.flipkart_status == 'pending').count()
        failed_fk = db.query(Product).filter(Product.flipkart_status == 'failed').count()
        total_fk_keywords = db.query(Keyword).filter(Keyword.marketplace == 'flipkart').count()

        print("\n==================================================")
        print("       FLIPKART BATCH (28 PRODS) RESULT REPORT    ")
        print("==================================================")
        print(f"1. Products Processed in Batch:  {res['total_products_processed']}")
        print(f"2. Successful Products:          {res['successful_products']}")
        print(f"3. Failed Products in Batch:     {res['failed_products']}")
        print(f"4. Total Keywords Collected:     {res['total_keywords_collected']}")
        print(f"5. HTTP 403 Responses:           {res['http_403_count']}")
        print(f"6. Total Retries Attempted:      {res['retries_count']}")
        print("--------------------------------------------------")
        print("7. Final DB Flipkart Overall Counts:")
        print(f"   - Total Database Products:    {total_prods}")
        print(f"   - Flipkart Completed:         {completed_fk}")
        print(f"   - Flipkart Pending:           {pending_fk}")
        print(f"   - Flipkart Failed:            {failed_fk}")
        print(f"   - Total Flipkart Keywords DB: {total_fk_keywords}")
        print("--------------------------------------------------")
        print(f"8. Amazon Data Preservation:     {'CONFIRMED UNCHANGED' if amazon_intact else 'FAILED - DATA MODIFIED'}")
        print("==================================================\n")

    finally:
        db.close()

if __name__ == "__main__":
    main()
