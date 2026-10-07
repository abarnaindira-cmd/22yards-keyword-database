import re
import time
import logging
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session

from app.models.product import Product
from app.models.keyword import Keyword
from app.database import SessionFlipkart
from app.services.flipkart_keyword_collector import collect_flipkart_keywords, RETRIES_STATS

logger = logging.getLogger("flipkart_suggestion_runner")

KNOWN_BRANDS = [
    "vector x", "viva fitness", "viva", "sg", "ss", "ton", "cosco", "dsc", "gm",
    "mrf", "ceat", "kookaburra", "bdm", "spartan", "ipl", "minimal buzz", "minimal",
    "nike", "adidas", "puma", "under armour", "nivia", "yonex", "li-ning", "hundred"
]

BROAD_CATEGORIES = {
    "apparel", "shoe", "shoes", "gym training", "sports"
}


def clean_flipkart_title_to_seeds(product_name: str, category: Optional[str] = None) -> List[str]:
    """
    Extract clean search query seeds from a Flipkart product title and category.
    """
    if not product_name and not category:
        return []

    raw_name = (product_name or "").strip()

    # 1. Strip parenthesized content and brackets
    text = re.sub(r'\(.*?\)', ' ', raw_name)
    text = re.sub(r'\[.*?\]', ' ', text)

    # 2. Strip model codes like VS-029, CS-100, etc.
    text = re.sub(r'\b[A-Z]{1,3}[-\s]?\d{2,5}[A-Z]?\b', ' ', text)

    # 3. Strip common noise terms
    noise_patterns = [
        r'\bkit product\b', r'\bew jr\b', r'\bs\.?jr\b', r'\br\.?h\b', r'\bl\.?h\b',
        r'\bkit \d+\b', r'\byouth\b', r'\badult\b', r'\bjunior\b', r'\bpro\b',
        r'\bpremium\b', r'\bsuper\b', r'\bultra\b', r'\bmax\b', r'\bedition\b'
    ]
    for pat in noise_patterns:
        text = re.sub(pat, ' ', text, flags=re.IGNORECASE)

    # 4. Clean non-alphanumeric punctuation
    text = re.sub(r'[^\w\s]', ' ', text)

    # 5. Tokenize
    raw_words = [w for w in text.split() if w.strip()]
    stop_tokens = {"in", "s", "and", "or", "for", "with", "of", "to", "by", "a", "an", "the", "pack", "set", "of"}
    words = [w for w in raw_words if len(w) > 1 and w.lower() not in stop_tokens and not re.match(r'^\d+$', w)]

    if not words and not category:
        return [raw_name] if raw_name else []

    seeds = []

    # A. Clean Category Seed
    cat_cleaned = re.sub(r'[^\w\s]', ' ', category or '').strip()
    cat_cleaned = re.sub(r'\s+', ' ', cat_cleaned)
    if cat_cleaned and cat_cleaned.lower() not in BROAD_CATEGORIES:
        seeds.append(cat_cleaned)

    # B. Extract Brand if present
    brand = ""
    lower_title = " ".join(words).lower()
    for b in KNOWN_BRANDS:
        if lower_title.startswith(b):
            b_word_count = len(b.split())
            brand = " ".join(words[:b_word_count])
            break

    brand_word_count = len(brand.split()) if brand else 0
    non_brand_words = words[brand_word_count:]

    # C. Non-brand Core Phrase (up to 4 words)
    if len(non_brand_words) >= 2:
        nb_phrase = " ".join(non_brand_words[:min(len(non_brand_words), 4)])
        seeds.append(nb_phrase)
    elif len(non_brand_words) == 1 and cat_cleaned:
        seeds.append(f"{non_brand_words[0]} {cat_cleaned}")

    # D. Full Cleaned Title fallback
    full_cleaned = " ".join(words[:min(len(words), 5)])
    if full_cleaned:
        seeds.append(full_cleaned)

    # Filter and deduplicate seeds
    final_seeds = []
    seen = set()
    for s in seeds:
        s_clean = re.sub(r'\s+', ' ', s).strip()
        if s_clean and len(s_clean.split()) >= 2:
            s_lower = s_clean.lower()
            if s_lower not in seen and s_lower not in BROAD_CATEGORIES:
                seen.add(s_lower)
                final_seeds.append(s_clean)

    if not final_seeds and raw_name:
        final_seeds.append(raw_name)

    return final_seeds


def collect_flipkart_keywords_for_product(
    db: Session,
    product: Product,
    delay_seconds: float = 0.3
) -> List[Keyword]:
    """
    Collect Flipkart search suggestions for a single product from MySQL.
    Uses independent flipkart_status field so Amazon data remains untouched.
    """
    seeds = clean_flipkart_title_to_seeds(product.product_name, product.category)
    if not seeds:
        seeds = [product.product_name]

    logger.info(f"Processing Flipkart product ID={product.id}, ASIN/FSN={product.asin}, seeds={seeds}")

    product.flipkart_status = "in_progress"
    db.commit()

    all_suggestions: List[str] = []
    seen_suggestions = set()

    for seed in seeds:
        suggestions = collect_flipkart_keywords(seed)
        for kw in suggestions:
            kw_clean = re.sub(r'\s+', ' ', kw).strip()
            if kw_clean and kw_clean.lower() not in seen_suggestions:
                seen_suggestions.add(kw_clean.lower())
                all_suggestions.append(kw_clean)
        if delay_seconds > 0:
            time.sleep(delay_seconds)

    inserted_keywords: List[Keyword] = []

    for kw_text in all_suggestions:
        # Check if keyword already stored for this FSN, source, and marketplace
        existing = db.query(Keyword).filter(
            Keyword.keyword == kw_text,
            Keyword.source_product_asin == product.asin,
            Keyword.source == "flipkart_search_suggestions",
            Keyword.marketplace == "flipkart"
        ).first()

        if not existing:
            new_kw = Keyword(
                keyword=kw_text,
                source="flipkart_search_suggestions",
                source_product_asin=product.asin,
                category=product.category,
                marketplace="flipkart",
                relevance_score=0.0
            )
            db.add(new_kw)
            inserted_keywords.append(new_kw)

    try:
        if all_suggestions:
            product.flipkart_status = "completed"
        else:
            product.flipkart_status = "failed"
        db.commit()
    except Exception as e:
        db.rollback()
        product.flipkart_status = "failed"
        db.commit()
        logger.error(f"[Flipkart Runner Error] Error committing keywords for ASIN/FSN '{product.asin}': {e}")
        raise e

    return inserted_keywords


def run_flipkart_batch_keyword_collection(
    db: Optional[Session] = None,
    limit: int = 10,
    delay_seconds: float = 0.5
) -> Dict[str, Any]:
    """
    Read pending Flipkart products from MySQL 'products' table in 'marketlens_flipkart'
    (filtering on flipkart_status == 'pending'), collect search suggestions, and store keywords.
    """
    close_db = False
    if db is None:
        db = SessionFlipkart()
        close_db = True

    try:
        # Reset batch retries counters
        RETRIES_STATS["403_responses"] = 0
        RETRIES_STATS["total_retries"] = 0

        # Filter by flipkart_status == 'pending'
        products = (
            db.query(Product)
            .filter(Product.flipkart_status == "pending")
            .order_by(Product.id.asc())
            .limit(limit)
            .all()
        )

        if not products:
            return {
                "total_products_processed": 0,
                "successful_products": 0,
                "failed_products": 0,
                "total_keywords_collected": 0,
                "http_403_count": 0,
                "retries_count": 0,
                "message": "No pending Flipkart products found in Flipkart MySQL database to process.",
                "details": []
            }

        successful_count = 0
        failed_count = 0
        total_keywords = 0
        details = []

        for product in products:
            try:
                created_kws = collect_flipkart_keywords_for_product(db, product, delay_seconds=delay_seconds)
                if product.flipkart_status == "completed":
                    total_keywords += len(created_kws)
                    successful_count += 1
                    details.append({
                        "product_id": product.id,
                        "asin_fsn": product.asin,
                        "product_name": product.product_name,
                        "category": product.category,
                        "marketplace": product.marketplace,
                        "keywords_collected": len(created_kws),
                        "flipkart_status": product.flipkart_status,
                        "amazon_status": product.status,
                        "success": True
                    })
                else:
                    failed_count += 1
                    details.append({
                        "product_id": product.id,
                        "asin_fsn": product.asin,
                        "product_name": product.product_name,
                        "category": product.category,
                        "marketplace": product.marketplace,
                        "keywords_collected": 0,
                        "flipkart_status": product.flipkart_status,
                        "amazon_status": product.status,
                        "success": False,
                        "reason": "No valid keywords collected across generated seeds"
                    })
            except Exception as err:
                failed_count += 1
                details.append({
                    "product_id": product.id,
                    "asin_fsn": product.asin,
                    "product_name": product.product_name,
                    "category": product.category,
                    "marketplace": product.marketplace,
                    "keywords_collected": 0,
                    "flipkart_status": "failed",
                    "amazon_status": product.status,
                    "success": False,
                    "error": str(err)
                })

        return {
            "total_products_processed": len(products),
            "successful_products": successful_count,
            "failed_products": failed_count,
            "total_keywords_collected": total_keywords,
            "http_403_count": RETRIES_STATS["403_responses"],
            "retries_count": RETRIES_STATS["total_retries"],
            "message": f"Successfully processed batch of {len(products)} Flipkart product(s).",
            "details": details
        }
    finally:
        if close_db and db is not None:
            db.close()
