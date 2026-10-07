from sqlalchemy import text
from app.database import SessionLocal

db = SessionLocal()

prods = db.execute(text("SELECT id, asin, product_name FROM products ORDER BY id ASC LIMIT 100;")).fetchall()
first_100_asins = [p.asin for p in prods if p.asin]

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

count_5_of_5 = 0
count_1_to_4 = 0
count_0_of_5 = 0
total_url_slots = 0

for k in kws:
    key = (k.source_product_asin.strip().lower(), k.keyword.strip().lower())
    u = url_map.get(key)
    if u:
        slot_urls = [u.url_1, u.url_2, u.url_3, u.url_4, u.url_5]
        valid_urls = [x for x in slot_urls if x and str(x).strip() != '']
        cnt = len(valid_urls)
        total_url_slots += cnt
        if cnt == 5:
            count_5_of_5 += 1
        elif cnt > 0:
            count_1_to_4 += 1
        else:
            count_0_of_5 += 1
    else:
        count_0_of_5 += 1

print("==========================================================================")
print("FINAL DATABASE AUDIT VERIFICATION RESULT FOR PRODUCTS 1 TO 100")
print("==========================================================================")
print(f"Total Products                     : {len(prods)}")
print(f"Total Keywords                     : {len(kws)}")
print(f"Keywords with 5/5 URLs            : {count_5_of_5}")
print(f"Keywords with 1–4 URLs            : {count_1_to_4}")
print(f"Keywords with 0 URLs              : {count_0_of_5}")
print(f"Total Incomplete Keywords          : {count_1_to_4 + count_0_of_5}")
print(f"Total Populated Organic URL Slots  : {total_url_slots} / {len(kws)*5}")
print("==========================================================================")

db.close()
