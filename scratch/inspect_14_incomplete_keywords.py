from sqlalchemy import text
from app.database import SessionLocal

db = SessionLocal()

# Query products 1 to 100 (IDs 4 to 103)
prods = db.execute(text("SELECT id, asin, product_name FROM products ORDER BY id ASC LIMIT 100;")).fetchall()
first_100_asins = [p.asin for p in prods if p.asin]

# Get all keywords for these products
kws = db.execute(text("""
    SELECT id, source_product_asin, keyword 
    FROM keywords 
    WHERE source_product_asin IN :asins AND LOWER(marketplace) = 'amazon';
"""), {"asins": tuple(first_100_asins)}).fetchall()

url_rows = db.execute(text("""
    SELECT source_product_asin, keyword, url_1, url_2, url_3, url_4, url_5 
    FROM keyword_search_urls 
    WHERE source_product_asin IN :asins AND LOWER(marketplace) = 'amazon';
"""), {"asins": tuple(first_100_asins)}).fetchall()

url_map = {(u.source_product_asin.strip().lower(), u.keyword.strip().lower()): u for u in url_rows}

incomplete = []

for k in kws:
    key = (k.source_product_asin.strip().lower(), k.keyword.strip().lower())
    u = url_map.get(key)
    if u:
        slot_urls = [u.url_1, u.url_2, u.url_3, u.url_4, u.url_5]
        valid_urls = [x for x in slot_urls if x and str(x).strip() != '']
        if len(valid_urls) < 5:
            incomplete.append({
                "asin": k.source_product_asin,
                "keyword": k.keyword,
                "valid_count": len(valid_urls),
                "existing_urls": valid_urls
            })
    else:
        incomplete.append({
            "asin": k.source_product_asin,
            "keyword": k.keyword,
            "valid_count": 0,
            "existing_urls": []
        })

print(f"Total Incomplete Keywords Found: {len(incomplete)}\n")
for idx, item in enumerate(incomplete, 1):
    print(f"{idx:2d}. ASIN: {item['asin']} | Keyword: '{item['keyword']}' | Existing URLs: {item['valid_count']}/5")
    for i, url in enumerate(item['existing_urls'], 1):
        print(f"    URL {i}: {url}")

db.close()
