from sqlalchemy import text
from app.database import SessionLocal

db = SessionLocal()

# 1. Fetch first 100 products ordered by id asc
prods = db.execute(text("SELECT id, asin, product_name FROM products ORDER BY id ASC LIMIT 100;")).fetchall()
first_100_asins = [p.asin for p in prods if p.asin]

print(f"1. Total distinct product ASINs among first 100 products: {len(set(first_100_asins))}")

# 2. Total keywords for those products (where marketplace = 'amazon')
kw_query = text("""
    SELECT id, source_product_asin, keyword 
    FROM keywords 
    WHERE source_product_asin IN :asins AND LOWER(marketplace) = 'amazon';
""")
kws = db.execute(kw_query, {"asins": tuple(first_100_asins)}).fetchall()
total_keywords = len(kws)
print(f"2. Total keywords for those 100 products: {total_keywords}")

# 3, 4, 5. Check keyword_search_urls records for these keywords
url_query = text("""
    SELECT source_product_asin, keyword, url_1, url_2, url_3, url_4, url_5 
    FROM keyword_search_urls 
    WHERE source_product_asin IN :asins AND LOWER(marketplace) = 'amazon';
""")
url_rows = db.execute(url_query, {"asins": tuple(first_100_asins)}).fetchall()

url_map = {}
for u in url_rows:
    key = (u.source_product_asin.strip().lower(), u.keyword.strip().lower())
    url_map[key] = u

keywords_with_url_record = 0
keywords_missing_urls = 0
total_url_slots_populated = 0

for k in kws:
    key = (k.source_product_asin.strip().lower(), k.keyword.strip().lower())
    u_rec = url_map.get(key)
    if u_rec:
        keywords_with_url_record += 1
        urls = [u_rec.url_1, u_rec.url_2, u_rec.url_3, u_rec.url_4, u_rec.url_5]
        valid_urls = [s for s in urls if s and str(s).strip() != '']
        total_url_slots_populated += len(valid_urls)
        if len(valid_urls) < 5:
            keywords_missing_urls += 1
    else:
        keywords_missing_urls += 1

print(f"3. Keywords with saved Amazon URL records: {keywords_with_url_record}")
print(f"4. Keywords missing one or more URLs: {keywords_missing_urls}")
print(f"5. Total URL slots populated across first 100 products: {total_url_slots_populated}")

db.close()
