from app.database import SessionLocal
from app.models.keyword_url import KeywordSearchUrl
from app.models.keyword import Keyword

db = SessionLocal()

urls = db.query(KeywordSearchUrl).filter(KeywordSearchUrl.source_product_asin == "T2YVIVA000017").all()
print(f"Direct DB Query KeywordSearchUrl count for ASIN T2YVIVA000017: {len(urls)}")

for u in urls:
    print(f"ASIN: '{u.source_product_asin}' | Keyword: '{u.keyword}' | Marketplace: '{u.marketplace}' | url_1: {u.url_1}")

kws = db.query(Keyword).filter(Keyword.source_product_asin == "T2YVIVA000017").all()
print(f"\nDirect DB Query Keyword count for ASIN T2YVIVA000017: {len(kws)}")
for k in kws:
    print(f"ASIN: '{k.source_product_asin}' | Keyword: '{k.keyword}'")

db.close()
