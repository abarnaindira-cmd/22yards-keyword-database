from sqlalchemy import text
from app.database import SessionLocal

db = SessionLocal()

# Query products 1 to 100 (IDs 4 to 103)
prods = db.execute(text("SELECT id, asin, product_name FROM products ORDER BY id ASC LIMIT 100;")).fetchall()
first_100_asins = [p.asin for p in prods if p.asin]

# Total keywords for these 100 products
kws = db.execute(text("""
    SELECT id, source_product_asin, keyword 
    FROM keywords 
    WHERE source_product_asin IN :asins AND LOWER(marketplace) = 'amazon';
"""), {"asins": tuple(first_100_asins)}).fetchall()

total_keywords = len(kws)

# Fetch all URL records for these products
url_rows = db.execute(text("""
    SELECT source_product_asin, keyword, url_1, url_2, url_3, url_4, url_5 
    FROM keyword_search_urls 
    WHERE source_product_asin IN :asins AND LOWER(marketplace) = 'amazon';
"""), {"asins": tuple(first_100_asins)}).fetchall()

url_map = {(u.source_product_asin.strip().lower(), u.keyword.strip().lower()): u for u in url_rows}

completed_5_urls_kw = 0
partial_urls_kw = 0
failed_0_urls_kw = 0
total_populated_url_slots = 0
failed_kw_details = []

for k in kws:
    key = (k.source_product_asin.strip().lower(), k.keyword.strip().lower())
    u_rec = url_map.get(key)
    if u_rec:
        urls = [u_rec.url_1, u_rec.url_2, u_rec.url_3, u_rec.url_4, u_rec.url_5]
        valid_urls = [s for s in urls if s and str(s).strip() != '']
        cnt = len(valid_urls)
        total_populated_url_slots += cnt
        if cnt == 5:
            completed_5_urls_kw += 1
        elif cnt > 0:
            partial_urls_kw += 1
        else:
            failed_0_urls_kw += 1
            failed_kw_details.append((k.source_product_asin, k.keyword))
    else:
        failed_0_urls_kw += 1
        failed_kw_details.append((k.source_product_asin, k.keyword))

remaining_pending = total_keywords - completed_5_urls_kw

print("==========================================================================")
print("FINAL POST-RUN MYSQL DATABASE VERIFICATION REPORT")
print("==========================================================================")
print(f"Products Processed                       : {len(prods)}")
print(f"Total Harvested Keywords                 : {total_keywords}")
print(f"Keywords Completed (5/5 URLs)            : {completed_5_urls_kw}")
print(f"Keywords Partially Completed (1-4 URLs)  : {partial_urls_kw}")
print(f"Keywords Failed (0 URLs)                 : {failed_0_urls_kw}")
print(f"Keywords Remaining Pending (<5 URLs)     : {remaining_pending}")
print(f"Total Organic URL Slots Saved in MySQL   : {total_populated_url_slots}")
print("==========================================================================")

if failed_kw_details:
    print("\nFailed Keyword Details:")
    for asin, kw in failed_kw_details:
        print(f"  ASIN: {asin} | Keyword: '{kw}'")

db.close()
