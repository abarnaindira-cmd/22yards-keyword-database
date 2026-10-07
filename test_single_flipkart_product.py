import logging
from app.database import SessionLocal
from app.models.product import Product
from app.models.keyword import Keyword
from app.services.flipkart_suggestion_runner import (
    clean_flipkart_title_to_seeds,
    collect_flipkart_keywords_for_product,
    run_flipkart_batch_keyword_collection
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

def run_single_product_test():
    db = SessionLocal()
    try:
        print("==================================================")
        print("         STAGE 2: FLIPKART SAFETY CHECKS          ")
        print("==================================================")
        
        # 1. Print Safety Checks
        total_prods = db.query(Product).count()
        pending_fk = db.query(Product).filter(Product.flipkart_status == 'pending').count()
        completed_fk = db.query(Product).filter(Product.flipkart_status == 'completed').count()
        failed_fk = db.query(Product).filter(Product.flipkart_status == 'failed').count()

        print(f"Total Products in DB: {total_prods}")
        print(f"Pending Flipkart products (flipkart_status='pending'): {pending_fk}")
        print(f"Completed Flipkart products (flipkart_status='completed'): {completed_fk}")
        print(f"Failed Flipkart products (flipkart_status='failed'): {failed_fk}")
        print("==================================================\n")

        # 2. Select 1 pending product from MySQL to test
        test_product = db.query(Product).filter(Product.flipkart_status == 'pending').first()
        if not test_product:
            print("No pending Flipkart products found in MySQL.")
            return

        print(f"Testing Flipkart collection for Product ID: {test_product.id}, ASIN: {test_product.asin}, Name: '{test_product.product_name}'")
        print(f"Pre-test Amazon status (Product.status): '{test_product.status}', Marketplace: '{test_product.marketplace}'")

        # 3. Generate seeds
        seeds = clean_flipkart_title_to_seeds(test_product.product_name, test_product.category)

        # 4. Execute collection for ONLY this 1 product
        print("Executing keyword collection for single test product...")
        inserted_keywords = collect_flipkart_keywords_for_product(db, test_product)

        # 5. Display single product test results
        db.refresh(test_product)
        print("\n==================================================")
        print("         SINGLE FLIPKART PRODUCT TEST RESULT       ")
        print("==================================================")
        print(f"Product ID:                {test_product.id}")
        print(f"Product ASIN/FSN:          {test_product.asin}")
        print(f"Product Name:              {test_product.product_name}")
        print(f"Marketplace:               {test_product.marketplace} (Unchanged)")
        print(f"Amazon Status (status):    {test_product.status} (Unchanged)")
        print(f"Flipkart Status:           {test_product.flipkart_status}")
        print(f"Seeds Generated:           {seeds}")
        print(f"Number of Keywords Found:  {len(inserted_keywords)}")
        print(f"Keyword DB Insert Count:   {len(inserted_keywords)}")
        print("\nCollected Keywords:")
        for idx, kw in enumerate(inserted_keywords, 1):
            print(f"  {idx}. {kw.keyword}")
        print("==================================================\n")

    finally:
        db.close()

if __name__ == "__main__":
    run_single_product_test()
