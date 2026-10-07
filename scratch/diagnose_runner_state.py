import os
import sys
from sqlalchemy import create_engine, text

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.database import MYSQL_DATABASE_URL

def diagnose():
    engine = create_engine(MYSQL_DATABASE_URL)
    with engine.connect() as conn:
        # 1. Total products
        total_prods = conn.execute(text("SELECT COUNT(*) FROM products")).scalar()

        # 2. Check the 30 legacy pipe fallbacks
        pipes = conn.execute(text("""
            SELECT p.id, p.asin, p.product_name, fpd.final_product_title,
                   (SELECT COUNT(*) FROM competitor_products c WHERE c.source_product_asin = p.asin) as comp_count
            FROM products p
            JOIN final_product_data fpd ON p.asin = fpd.sku_id
            WHERE fpd.final_product_title LIKE '%|%'
            ORDER BY p.id ASC
        """)).fetchall()

        print(f"=== 30 LEGACY PIPE FALLBACK PRODUCTS ===")
        print(f"Total legacy pipe products remaining: {len(pipes)}")
        for r in pipes[:10]:
            print(f"  ID: {r[0]:4d} | SKU: {r[1]:15s} | Competitors: {r[4]:2d} | Title: {r[3][:60]}...")
        if len(pipes) > 10:
            print("  ...")
            for r in pipes[-5:]:
                print(f"  ID: {r[0]:4d} | SKU: {r[1]:15s} | Competitors: {r[4]:2d} | Title: {r[3][:60]}...")

        # 3. Check MANUAL_REVIEW_REQUIRED products competitor count
        mr_comp_counts = conn.execute(text("""
            SELECT 
                CASE WHEN comp_count = 0 THEN '0 Competitors' ELSE '>=1 Competitors' END as category,
                COUNT(*) as qty
            FROM (
                SELECT p.asin, (SELECT COUNT(*) FROM competitor_products c WHERE c.source_product_asin = p.asin) as comp_count
                FROM products p
                JOIN final_product_data fpd ON p.asin = fpd.sku_id
                WHERE fpd.final_product_title = 'MANUAL_REVIEW_REQUIRED'
            ) t
            GROUP BY category
        """)).fetchall()

        print("\n=== MANUAL REVIEW REQUIRED BREAKDOWN ===")
        for r in mr_comp_counts:
            print(f"  {r[0]}: {r[1]} products")

        # 4. Check Groq Success products competitor count
        groq_comp_counts = conn.execute(text("""
            SELECT COUNT(*) FROM final_product_data 
            WHERE final_product_title IS NOT NULL 
              AND TRIM(final_product_title) != '' 
              AND final_product_title NOT LIKE '%|%' 
              AND final_product_title != 'MANUAL_REVIEW_REQUIRED'
        """)).scalar()

        print(f"\n=== GROQ AI TITLES SUCCESS TOTAL ===")
        print(f"  Total Groq AI Titles: {groq_comp_counts}")

if __name__ == "__main__":
    diagnose()
