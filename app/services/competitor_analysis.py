import re
import time
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from app.models.product import Product
from app.models.keyword import Keyword
from app.models.competitor import KeywordRanking, CompetitorProduct, CompetitorKeyword
from app.services.amazon_rank_collector import search_amazon_results
from app.services.keyword_collector import collect_amazon_keywords


CORE_NOISE = {
    "new", "latest", "original", "premium", "pro", "professional", "men", "mens",
    "women", "womens", "kids", "kid", "junior", "senior", "small", "medium", "large",
    "xl", "xxl", "pack", "set", "combo", "kit", "black", "white", "blue", "red",
}


def competitor_seed_queries(title: str, category: Optional[str] = None) -> List[str]:
    """Build conservative, product-focused autocomplete seeds from a competitor title."""
    text = re.sub(r"\([^)]*\)|\[[^]]*\]", " ", title or "")
    text = re.sub(r"\b[A-Z]{1,4}[- ]?\d{2,6}[A-Z]?\b", " ", text)
    text = re.sub(r"[^\w\s-]", " ", text)
    words = [w for w in text.split() if len(w) > 1 and not w.isdigit()]
    cleaned = [w for w in words if w.lower() not in CORE_NOISE]

    seeds: List[str] = []
    if category:
        cat = re.sub(r"[^\w\s-]", " ", category).strip()
        if len(cat.split()) >= 2:
            seeds.append(cat)

    # Use 2-4 word phrases ending in a likely product noun.
    product_nouns = {
        "bat", "gloves", "glove", "helmet", "shoes", "shoe", "shirt", "t-shirt", "tshirt",
        "shorts", "pants", "pant", "jacket", "trophy", "grip", "guard", "pad", "bottle",
        "racket", "ball", "stumps", "cap", "sweatshirt", "dumbbell", "kit", "bag"
    }
    for n in range(min(4, len(cleaned)), 1, -1):
        phrase = " ".join(cleaned[:n])
        if any(cleaned[-1].lower().rstrip("s") == noun.rstrip("s") for noun in product_nouns):
            seeds.append(phrase)
            break

    if len(cleaned) >= 2:
        seeds.append(" ".join(cleaned[:2]))
    elif cleaned:
        seeds.append(cleaned[0])

    out = []
    for s in seeds:
        s = re.sub(r"\s+", " ", s).strip()
        if s and s.lower() not in {x.lower() for x in out}:
            out.append(s)
    return out[:3]


def get_product_keywords(db: Session, product: Product, limit: Optional[int] = None) -> List[Keyword]:
    q = db.query(Keyword).filter(Keyword.source_product_asin == product.asin).order_by(Keyword.id.asc())
    return q.limit(limit).all() if limit else q.all()


def _upsert_ranking(db: Session, source_asin: str, keyword: Keyword, result, is_our: bool):
    row = db.query(KeywordRanking).filter(
        KeywordRanking.source_product_asin == source_asin,
        KeywordRanking.keyword == keyword.keyword,
        KeywordRanking.result_asin == result.asin,
    ).first()
    if not row:
        row = KeywordRanking(
            source_product_asin=source_asin,
            keyword_id=keyword.id,
            keyword=keyword.keyword,
            result_asin=result.asin,
            rank_position=result.rank_position,
            result_title=result.title,
            product_url=result.product_url,
            is_our_product=1 if is_our else 0,
            page_number=result.page_number,
        )
        db.add(row)
    else:
        row.rank_position = result.rank_position
        row.result_title = result.title
        row.product_url = result.product_url
        row.is_our_product = 1 if is_our else 0
        row.page_number = result.page_number
    return row


import json


def _upsert_competitor(db: Session, source_asin: str, keyword: Keyword, rank_position: int, detail) -> bool:
    row = db.query(CompetitorProduct).filter(
        CompetitorProduct.source_product_asin == source_asin,
        CompetitorProduct.keyword == keyword.keyword,
        CompetitorProduct.competitor_asin == detail.asin,
    ).first()

    bp_json = json.dumps(detail.bullet_points, ensure_ascii=False) if detail.bullet_points else None
    reviews_json = json.dumps(detail.reviews, ensure_ascii=False) if detail.reviews else None

    is_new = False
    if not row:
        row = CompetitorProduct(
            source_product_asin=source_asin,
            keyword_id=keyword.id,
            keyword=keyword.keyword,
            competitor_asin=detail.asin,
            competitor_rank=rank_position,
            competitor_title=detail.title,
            product_url=detail.product_url,
            price=detail.price,
            rating=detail.rating,
            review_count=detail.review_count,
            description=detail.description,
            bullet_points=bp_json,
            reviews=reviews_json,
            marketplace="amazon.in",
        )
        db.add(row)
        is_new = True
    else:
        row.competitor_rank = rank_position
        row.competitor_title = detail.title
        row.product_url = detail.product_url
        row.price = detail.price
        row.rating = detail.rating
        row.review_count = detail.review_count
        row.description = detail.description
        row.bullet_points = bp_json
        row.reviews = reviews_json
    return is_new


def collect_competitor_keywords(
    db: Session,
    source_product_asin: str,
    competitor_asin: str,
    competitor_title: str,
    source_keyword: Optional[str] = None,
    source_keyword_id: Optional[int] = None,
    delay_seconds: float = 0.5,
) -> int:
    seeds = []
    if source_keyword:
        seeds.append(source_keyword)
    seeds.extend(competitor_seed_queries(competitor_title))
    unique_seeds = []
    for s in seeds:
        if s and s.lower() not in {x.lower() for x in unique_seeds}:
            unique_seeds.append(s)

    all_keywords: List[str] = []
    for seed in unique_seeds[:3]:
        suggestions = collect_amazon_keywords(seed)
        for kw in suggestions:
            if kw and kw.lower() not in {x.lower() for x in all_keywords}:
                all_keywords.append(kw)
        if delay_seconds:
            time.sleep(delay_seconds)

    inserted = 0
    for kw in all_keywords:
        existing = db.query(CompetitorKeyword).filter(
            CompetitorKeyword.source_product_asin == source_product_asin,
            CompetitorKeyword.competitor_asin == competitor_asin,
            CompetitorKeyword.keyword == kw,
            CompetitorKeyword.source == "amazon_suggestions",
        ).first()
        if not existing:
            db.add(CompetitorKeyword(
                source_product_asin=source_product_asin,
                competitor_asin=competitor_asin,
                source_keyword_id=source_keyword_id,
                source_keyword=source_keyword,
                keyword=kw,
                source="amazon_suggestions",
                relevance_score=0.0,
            ))
            inserted += 1
    return inserted


from app.services.amazon_detail_collector import fetch_competitor_details_batch
from app.services.competitor_keyword_extractor import extract_competitor_keywords_from_details


def analyze_product_keyword(
    db: Session,
    product: Product,
    keyword: Keyword,
    top_competitors: int = 20,
    max_pages: int = 2,
    delay_seconds: float = 1.0,
    collect_competitor_kw: bool = True,
    write_db: bool = True,
) -> Dict:
    # 1. Search Amazon using the keyword and collect top competitor cards
    raw_results = search_amazon_results(
        keyword.keyword,
        max_pages=max_pages,
        max_results=top_competitors,
        delay_seconds=delay_seconds,
    )

    competitor_cards = [r.to_dict() for r in raw_results[:top_competitors]]

    # 2. Fetch rich product details (description, bullet points, reviews) for each competitor
    detailed_competitors = fetch_competitor_details_batch(
        competitor_cards,
        delay_seconds=delay_seconds / 2,
    )

    detailed_dicts = [d.to_dict() for d in detailed_competitors]

    # 3. Extract competitor keywords from competitor product text data
    extracted_keywords = extract_competitor_keywords_from_details(detailed_dicts)

    db_stats = {
        "competitor_products_inserted": 0,
        "competitor_products_updated": 0,
        "competitor_keywords_inserted": 0,
    }

    if write_db:
        # Upsert competitor products to MySQL
        for idx, comp_detail in enumerate(detailed_competitors, 1):
            try:
                with db.begin_nested():
                    is_new = _upsert_competitor(
                        db,
                        source_asin=product.asin,
                        keyword=keyword,
                        rank_position=idx,
                        detail=comp_detail,
                    )
                    db.flush()
                if is_new:
                    db_stats["competitor_products_inserted"] += 1
                else:
                    db_stats["competitor_products_updated"] += 1
            except Exception as comp_err:
                print(f"[Warning] Competitor product insert skipped for {comp_detail.asin}: {comp_err}")

        # Store extracted competitor keywords to MySQL (avoiding duplicates for same source_product_asin, competitor_asin, keyword, source)
        if collect_competitor_kw and extracted_keywords:
            seen_in_batch = set()
            for kw in extracted_keywords:
                kw_clean = kw.strip()
                if not kw_clean:
                    continue
                comp_asin = detailed_competitors[0].asin if detailed_competitors else product.asin
                batch_key = (product.asin, comp_asin, kw_clean.lower(), "product_details_extraction")
                if batch_key in seen_in_batch:
                    continue
                seen_in_batch.add(batch_key)

                existing = db.query(CompetitorKeyword).filter(
                    CompetitorKeyword.source_product_asin == product.asin,
                    CompetitorKeyword.competitor_asin == comp_asin,
                    CompetitorKeyword.keyword == kw_clean,
                    CompetitorKeyword.source == "product_details_extraction",
                ).first()
                if not existing:
                    try:
                        with db.begin_nested():
                            db.add(CompetitorKeyword(
                                source_product_asin=product.asin,
                                competitor_asin=comp_asin,
                                source_keyword_id=keyword.id,
                                source_keyword=keyword.keyword,
                                keyword=kw_clean,
                                source="product_details_extraction",
                                relevance_score=0.0,
                            ))
                            db.flush()
                        db_stats["competitor_keywords_inserted"] += 1
                    except Exception as kw_err:
                        pass

        try:
            db.commit()
        except Exception as e:
            db.rollback()
            print(f"[ERROR] DB commit failed during competitor analysis for ASIN {product.asin}: {e}")
            raise e

    payload = {
        "keyword": keyword.keyword,
        "top_competitors_count": len(detailed_dicts),
        "competitors": detailed_dicts,
        "extracted_competitor_keywords": extracted_keywords,
        "db_stats": db_stats,
    }

    return payload


def run_competitor_batch(
    db: Session,
    product_limit: int = 3,
    offset: int = 0,
    keywords_per_product: int = 1,
    top_competitors: int = 20,
    max_pages: int = 2,
    delay_seconds: float = 1.0,
    write_db: bool = True,
) -> Dict:
    products = (
        db.query(Product)
        .filter(Product.status == "completed")
        .order_by(Product.id.asc())
        .offset(offset)
        .limit(product_limit)
        .all()
    )
    details = []
    for product in products:
        keywords = get_product_keywords(db, product, keywords_per_product)
        for kw in keywords:
            try:
                result = analyze_product_keyword(
                    db, product, kw,
                    top_competitors=top_competitors,
                    max_pages=max_pages,
                    delay_seconds=delay_seconds,
                    write_db=write_db,
                )
                details.append({"product_id": product.id, "product_asin": product.asin, **result})
            except Exception as exc:
                details.append({
                    "product_id": product.id,
                    "product_asin": product.asin,
                    "keyword": kw.keyword,
                    "error": str(exc),
                })
    
    product_id_start = products[0].id if products else None
    product_id_end = products[-1].id if products else None

    return {
        "products_tested": len(products),
        "offset": offset,
        "product_limit": product_limit,
        "product_id_start": product_id_start,
        "product_id_end": product_id_end,
        "keyword_tests": len(details),
        "write_db": write_db,
        "details": details,
    }




