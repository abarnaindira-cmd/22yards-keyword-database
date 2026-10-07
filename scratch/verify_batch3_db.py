import sys
sys.stdout.reconfigure(encoding='utf-8')
from app.database import SessionLocal
from app.models.product import Product
from app.models.final_product_data import FinalProductData

def check_db():
    db = SessionLocal()

    b3_prods = db.query(Product).order_by(Product.id.asc()).offset(200).limit(100).all()
    b3_asins = [p.asin for p in b3_prods if p.asin]

    b3_fd = db.query(FinalProductData).filter(FinalProductData.sku_id.in_(b3_asins)).all()
    b3_fd_map = {fd.sku_id: fd for fd in b3_fd}

    print(f"Batch 3 Product Count in `products`: {len(b3_prods)}")
    print(f"Batch 3 Rows in `final_product_data`: {len(b3_fd)}")

    groq_titles = []
    manual_review_titles = []
    fallback_pipe_titles = []
    other_titles = []

    for p in b3_prods:
        fd = b3_fd_map.get(p.asin)
        if not fd or not fd.final_product_title:
            other_titles.append((p.asin, 'MISSING'))
        elif fd.final_product_title == 'MANUAL_REVIEW_REQUIRED':
            manual_review_titles.append(p.asin)
        elif " | " in fd.final_product_title:
            fallback_pipe_titles.append(p.asin)
        else:
            groq_titles.append((p.asin, fd.final_product_title))

    print(f"Groq AI Generated Titles Count       : {len(groq_titles)}")
    print(f"MANUAL_REVIEW_REQUIRED Count         : {len(manual_review_titles)}")
    print(f"Legacy Fallback Pipe (' | ') Count   : {len(fallback_pipe_titles)}")
    print(f"Missing / Other Count                : {len(other_titles)}")

    if groq_titles:
        print("\nSample Groq AI Generated Titles:")
        for asin, t in groq_titles[:5]:
            print(f"  - {asin}: {t}")

    if fallback_pipe_titles:
        print("\nSample Legacy Fallback Pipe Titles:")
        for asin in fallback_pipe_titles[:5]:
            print(f"  - {asin}: {b3_fd_map[asin].final_product_title[:60]}...")

    db.close()

if __name__ == "__main__":
    check_db()
