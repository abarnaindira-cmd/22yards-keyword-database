import os
import sys
import time
from sqlalchemy import create_engine, text

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.database import MYSQL_DATABASE_URL

def check_live_delta():
    engine = create_engine(MYSQL_DATABASE_URL)
    with engine.connect() as conn:
        print("--- SNAPSHOT 1 ---")
        groq_count_1 = conn.execute(text("""
            SELECT COUNT(*) FROM final_product_data 
            WHERE final_product_title IS NOT NULL 
              AND TRIM(final_product_title) != '' 
              AND final_product_title NOT LIKE '%|%' 
              AND final_product_title != 'MANUAL_REVIEW_REQUIRED'
        """)).scalar()
        manual_count_1 = conn.execute(text("""
            SELECT COUNT(*) FROM final_product_data 
            WHERE final_product_title = 'MANUAL_REVIEW_REQUIRED'
        """)).scalar()
        pipe_count_1 = conn.execute(text("""
            SELECT COUNT(*) FROM final_product_data 
            WHERE final_product_title LIKE '%|%'
        """)).scalar()
        
        print(f"Groq Titles: {groq_count_1}, Manual Review: {manual_count_1}, Pipe Fallbacks: {pipe_count_1}")

    print("\nWaiting 10 seconds to observe live database updates...")
    time.sleep(10)

    with engine.connect() as conn:
        print("\n--- SNAPSHOT 2 ---")
        groq_count_2 = conn.execute(text("""
            SELECT COUNT(*) FROM final_product_data 
            WHERE final_product_title IS NOT NULL 
              AND TRIM(final_product_title) != '' 
              AND final_product_title NOT LIKE '%|%' 
              AND final_product_title != 'MANUAL_REVIEW_REQUIRED'
        """)).scalar()
        manual_count_2 = conn.execute(text("""
            SELECT COUNT(*) FROM final_product_data 
            WHERE final_product_title = 'MANUAL_REVIEW_REQUIRED'
        """)).scalar()
        pipe_count_2 = conn.execute(text("""
            SELECT COUNT(*) FROM final_product_data 
            WHERE final_product_title LIKE '%|%'
        """)).scalar()
        
        print(f"Groq Titles: {groq_count_2}, Manual Review: {manual_count_2}, Pipe Fallbacks: {pipe_count_2}")
        print(f"Delta Groq Titles  : +{groq_count_2 - groq_count_1}")
        print(f"Delta Manual Review: {manual_count_2 - manual_count_1}")

if __name__ == "__main__":
    check_live_delta()
