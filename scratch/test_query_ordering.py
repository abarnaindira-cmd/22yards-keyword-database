import openpyxl
import io
from app.database import SessionLocal
from sqlalchemy import text

db = SessionLocal()

print("--- Testing SQL Query Ordering & Filtering ---")

query = """
    SELECT 
        k.source_product_asin AS `Source Product ASIN`,
        COALESCE(p.product_name, '') AS `Source Product Name`,
        k.keyword AS `Keyword Phrase`,
        k.source AS `Source`,
        COALESCE(k.relevance_score, 0.0) AS `Relevance Score`,
        COALESCE(u.url_1, '') AS `Amazon Product URL 1`,
        COALESCE(u.url_2, '') AS `Amazon Product URL 2`,
        COALESCE(u.url_3, '') AS `Amazon Product URL 3`,
        COALESCE(u.url_4, '') AS `Amazon Product URL 4`,
        COALESCE(u.url_5, '') AS `Amazon Product URL 5`
    FROM keywords k
    INNER JOIN products p 
        ON TRIM(LOWER(k.source_product_asin)) = TRIM(LOWER(p.asin))
    LEFT JOIN keyword_search_urls u 
        ON TRIM(LOWER(k.source_product_asin)) = TRIM(LOWER(u.source_product_asin)) 
       AND TRIM(LOWER(k.keyword)) = TRIM(LOWER(u.keyword))
       AND LOWER(u.marketplace) = 'amazon'
    WHERE LOWER(k.marketplace) = 'amazon'
    ORDER BY p.id ASC, k.id ASC;
"""

rows = db.execute(text(query)).fetchall()
print(f"Total rows with INNER JOIN products: {len(rows)}")
for i, r in enumerate(rows[:25]):
    print(f"Row {i+2:2d}: ASIN={r[0]:15s} | Kw={r[2]:30s} | URL1={r[5]}")

url_count = sum(1 for r in rows if r[5])
print(f"\nTotal Populated URL 1 cells out of {len(rows)} rows: {url_count}")

db.close()
