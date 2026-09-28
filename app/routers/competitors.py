from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.competitor import KeywordRanking, CompetitorProduct, CompetitorKeyword
from app.services.competitor_analysis import run_competitor_batch

router = APIRouter(prefix="/api/competitors", tags=["Competitor Analysis"])


@router.post("/test", summary="Run a competitor-analysis batch process")
def competitor_test(
    product_limit: int = Query(3, ge=1, le=500),
    offset: int = Query(0, ge=0),
    keywords_per_product: int = Query(1, ge=1, le=10),
    top_competitors: int = Query(5, ge=1, le=20),
    max_pages: int = Query(1, ge=1, le=5),
    write_db: bool = Query(False),
    db: Session = Depends(get_db),
):
    """Run competitor analysis batch process with product_limit and offset."""
    try:
        return run_competitor_batch(
            db,
            product_limit=product_limit,
            offset=offset,
            keywords_per_product=keywords_per_product,
            top_competitors=top_competitors,
            max_pages=max_pages,
            write_db=write_db,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/rankings")
def list_rankings(
    source_product_asin: Optional[str] = None,
    keyword: Optional[str] = None,
    db: Session = Depends(get_db),
):
    q = db.query(KeywordRanking)
    if source_product_asin:
        q = q.filter(KeywordRanking.source_product_asin == source_product_asin)
    if keyword:
        q = q.filter(KeywordRanking.keyword == keyword)
    return q.order_by(KeywordRanking.rank_position.asc()).limit(500).all()


@router.get("/products")
def list_competitors(
    source_product_asin: Optional[str] = None,
    keyword: Optional[str] = None,
    db: Session = Depends(get_db),
):
    q = db.query(CompetitorProduct)
    if source_product_asin:
        q = q.filter(CompetitorProduct.source_product_asin == source_product_asin)
    if keyword:
        q = q.filter(CompetitorProduct.keyword == keyword)
    return q.order_by(CompetitorProduct.competitor_rank.asc()).limit(500).all()


@router.get("/keywords")
def list_competitor_keywords(
    source_product_asin: Optional[str] = None,
    competitor_asin: Optional[str] = None,
    db: Session = Depends(get_db),
):
    q = db.query(CompetitorKeyword)
    if source_product_asin:
        q = q.filter(CompetitorKeyword.source_product_asin == source_product_asin)
    if competitor_asin:
        q = q.filter(CompetitorKeyword.competitor_asin == competitor_asin)
    return q.order_by(CompetitorKeyword.id.desc()).limit(500).all()


from app.services.competitor_comparator import (
    compare_product_against_competitors,
    run_comparison_for_all_processed,
)


@router.get("/comparison")
def compare_all_processed(
    limit: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_db),
):
    """Run Product vs Competitor Gap Analysis for processed source products."""
    return run_comparison_for_all_processed(db, limit=limit)


@router.get("/comparison/{source_product_asin}")
def compare_single_product(
    source_product_asin: str,
    db: Session = Depends(get_db),
):
    """Run Product vs Competitor Gap Analysis for a single source product ASIN."""
    result = compare_product_against_competitors(db, source_product_asin)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result

