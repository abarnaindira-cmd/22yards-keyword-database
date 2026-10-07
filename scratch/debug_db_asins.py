import sys
import pandas as pd
from sqlalchemy import text
from app.database import SessionLocal, engine

db = SessionLocal()

print("--- PRODUCTS IN MYSQL ---")
prods = db.execute(text("SELECT id, asin, product_name FROM products ORDER BY id ASC")).fetchall()
print(f"Total products in `products` table: {len(prods)}")
for p in prods[:10]:
    print(p)

print("\n--- KEYWORDS BY ASIN IN MYSQL ---")
kw_counts = db.execute(text("SELECT source_product_asin, COUNT(*) as cnt FROM keywords GROUP BY source_product_asin ORDER BY source_product_asin")).fetchall()
print(f"Total ASINs with keywords in `keywords` table: {len(kw_counts)}")
for k in kw_counts[:10]:
    print(k)

print("\n--- KEYWORD SEARCH URLS BY ASIN IN MYSQL ---")
url_counts = db.execute(text("SELECT source_product_asin, COUNT(*) as cnt, COUNT(url_1) as u1 FROM keyword_search_urls GROUP BY source_product_asin ORDER BY source_product_asin")).fetchall()
print(f"Total ASINs with URLs in `keyword_search_urls` table: {len(url_counts)}")
for u in url_counts:
    print(u)

print("\n--- ASINs in `keywords` that are NOT in `products` or vice versa ---")
k_asins = set(r[0] for r in kw_counts)
p_asins = set(r.asin for r in prods)
u_asins = set(r[0] for r in url_counts)

print(f"ASINs in `keyword_search_urls`: {u_asins}")
print(f"Sample ASINs in `keywords` table: {list(k_asins)[:10]}")
print(f"Sample ASINs in `products` table: {list(p_asins)[:10]}")

db.close()
