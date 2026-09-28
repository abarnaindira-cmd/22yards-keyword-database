import time
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session

from app.models.product import Product
from app.models.keyword import Keyword
from app.services.keyword_collector import clean_product_title_to_seeds, collect_amazon_keywords

def collect_keywords_for_product(db: Session, product: Product, delay_seconds: float = 0.3) -> List[Keyword]:
    """
    Collect Amazon search suggestions for a single product from MySQL.
    Extracts seed queries, queries Amazon suggestions, saves keywords into 'keywords' table,
    and updates product status to 'completed'.
    """
    seeds = clean_product_title_to_seeds(product.product_name, product.category)
    if not seeds:
        seeds = [product.product_name]

    product.status = "in_progress"
    db.commit()

    all_suggestions = []
    for seed in seeds:
        suggestions = collect_amazon_keywords(seed)
        for kw in suggestions:
            if kw and kw.lower() not in [s.lower() for s in all_suggestions]:
                all_suggestions.append(kw)
        if delay_seconds > 0:
            time.sleep(delay_seconds)

    inserted_keywords = []
    for kw_text in all_suggestions:
        # Check if keyword already stored for this ASIN and source
        existing = db.query(Keyword).filter(
            Keyword.keyword == kw_text,
            Keyword.source_product_asin == product.asin,
            Keyword.source == "search_suggestions"
        ).first()

        if not existing:
            new_kw = Keyword(
                keyword=kw_text,
                source="search_suggestions",
                source_product_asin=product.asin,
                category=product.category,
                relevance_score=0.0
            )
            db.add(new_kw)
            inserted_keywords.append(new_kw)

    try:
        if all_suggestions:
            product.status = "completed"
        else:
            product.status = "failed"
        db.commit()
    except Exception as e:
        db.rollback()
        product.status = "failed"
        db.commit()
        print(f"[Suggestion Runner Error] Error committing keywords for ASIN '{product.asin}': {e}")
        raise e

    return inserted_keywords

def run_batch_keyword_collection(
    db: Session,
    limit: int = 10,
    product_id: Optional[int] = None,
    delay_seconds: float = 0.3
) -> Dict[str, Any]:
    """
    Read pending products from MySQL 'products' table, collect search suggestions from Amazon,
    and store keywords in MySQL 'keywords' table.
    Gracefully catches per-product failures to ensure the batch continues.
    """
    query = db.query(Product)
    if product_id:
        query = query.filter(Product.id == product_id)
    else:
        query = query.filter(Product.status == "pending")

    products = query.order_by(Product.id.asc()).limit(limit).all()

    if not products:
        return {
            "total_products_processed": 0,
            "successful_products": 0,
            "failed_products": 0,
            "total_keywords_collected": 0,
            "message": "No pending products found in MySQL 'products' table to process.",
            "details": []
        }

    successful_count = 0
    failed_count = 0
    total_keywords = 0
    details = []

    for product in products:
        try:
            created_kws = collect_keywords_for_product(db, product, delay_seconds=delay_seconds)
            total_keywords += len(created_kws)
            successful_count += 1
            details.append({
                "product_id": product.id,
                "asin": product.asin,
                "product_name": product.product_name,
                "category": product.category,
                "keywords_collected": len(created_kws),
                "status": product.status,
                "success": True
            })
        except Exception as err:
            failed_count += 1
            details.append({
                "product_id": product.id,
                "asin": product.asin,
                "product_name": product.product_name,
                "category": product.category,
                "keywords_collected": 0,
                "status": "failed",
                "success": False,
                "error": str(err)
            })

    return {
        "total_products_processed": len(products),
        "successful_products": successful_count,
        "failed_products": failed_count,
        "total_keywords_collected": total_keywords,
        "message": f"Successfully processed batch of {len(products)} product(s).",
        "details": details
    }
