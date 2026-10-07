from sqlalchemy import text
from app.database import SessionLocal
from app.models.competitor import CompetitorProduct
from app.models.product import Product

db = SessionLocal()

# Check competitor titles for T2YVIVA000017
sku_id = "T2YVIVA000017"
comp_rows = db.query(CompetitorProduct).filter(
    CompetitorProduct.source_product_asin == sku_id
).all()

print(f"CompetitorProduct records for {sku_id}: {len(comp_rows)}")

# Collect unique competitor titles
titles = []
for c in comp_rows:
    if c.competitor_title and c.competitor_title.strip():
        if c.competitor_title.strip() not in titles:
            titles.append(c.competitor_title.strip())

print(f"Unique Competitor Titles for {sku_id}: {len(titles)}")
for idx, t in enumerate(titles[:20], 1):
    print(f"  {idx}. {t}")

# Check average competitor titles across target 100 products (IDs 4 to 103)
target_prods = db.query(Product).filter(Product.id.between(4, 103)).all()
counts = []
for p in target_prods:
    c_count = db.query(CompetitorProduct).filter(CompetitorProduct.source_product_asin == p.asin).count()
    counts.append(c_count)

print(f"\nAcross 100 Target Batch Products (IDs 4-103):")
print(f"  - Min Competitor Products per ASIN : {min(counts) if counts else 0}")
print(f"  - Max Competitor Products per ASIN : {max(counts) if counts else 0}")
print(f"  - Avg Competitor Products per ASIN : {sum(counts)/len(counts) if counts else 0:.1f}")

db.close()
