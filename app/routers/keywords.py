import os
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.database import get_db, test_db_connection
from app.models.keyword import Keyword
from app.schemas.keyword import KeywordCreate, KeywordUpdate, KeywordResponse
from app.services.suggestion_runner import run_batch_keyword_collection

router = APIRouter(prefix="/api/keywords", tags=["Keywords"])

@router.post("/collect-from-products", summary="Collect Amazon Keywords for Stored Products")
def collect_keywords_from_products(
    limit: int = Query(10, ge=1, le=100, description="Max number of pending products to process"),
    product_id: Optional[int] = Query(None, description="Optional specific product ID to process"),
    db: Session = Depends(get_db)
):
    """
    Read product names from MySQL 'products' table, query Amazon Search Suggestions,
    save keywords into MySQL 'keywords' table, and update product status to 'completed'.
    """
    try:
        result = run_batch_keyword_collection(db=db, limit=limit, product_id=product_id)
        return result
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Keyword collection failed: {str(e)}"
        )

@router.post("/collect-amazon-urls", summary="Collect & Permanently Store Organic Amazon URLs for Harvested Keywords")
def collect_amazon_urls(
    asin: str = Query(..., description="Target Product ASIN to process"),
    db: Session = Depends(get_db)
):
    """
    Search each harvested keyword belonging to ASIN on Amazon India,
    collect top 5 organic product URLs, and permanently store in MySQL table 'keyword_search_urls'.
    """
    try:
        from app.services.amazon_url_collector import process_amazon_urls_for_asin
        return process_amazon_urls_for_asin(db=db, target_asin=asin)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Amazon URL collection failed: {str(e)}"
        )

@router.get("/export-harvested-keywords", summary="Export Harvested Keywords Report with Stored Amazon URLs to Excel or CSV")
def export_harvested_keywords(
    asin: Optional[str] = Query(None, description="Optional Product ASIN filter"),
    format: str = Query("excel", description="Export format: 'excel' or 'csv'"),
    db: Session = Depends(get_db)
):
    """
    Read harvested keywords and stored Amazon URLs from MySQL, format into sheet/file 'Harvested Keywords'
    with columns A-J (F-J containing stored Amazon URLs), and return Excel or CSV file. Performs NO live searches.
    """
    from fastapi.responses import FileResponse
    from app.services.excel_exporter import export_harvested_keywords_to_excel
    try:
        fmt = "csv" if format.lower() == "csv" else "excel"
        filepath = export_harvested_keywords_to_excel(db=db, source_product_asin=asin, file_format=fmt)
        filename = os.path.basename(filepath)
        media_type = "text/csv" if fmt == "csv" else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        return FileResponse(
            path=filepath,
            filename=filename,
            media_type=media_type
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Export failed: {str(e)}"
        )

@router.get("/test-db", summary="Test Database Connection")
def check_db_connection():
    """Verify MySQL/Database connection and parameters."""
    result = test_db_connection()
    if result.get("status") == "error":
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=result
        )
    return result

@router.get("", response_model=List[KeywordResponse], summary="List Keywords")
def list_keywords(
    asin: Optional[str] = Query(None, description="Filter by Product ASIN"),
    source: Optional[str] = Query(None, description="Filter by Source"),
    category: Optional[str] = Query(None, description="Filter by Category"),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db)
):
    query = db.query(Keyword)
    if asin:
        query = query.filter(Keyword.source_product_asin == asin)
    if source:
        query = query.filter(Keyword.source == source)
    if category:
        query = query.filter(Keyword.category == category)
    
    keywords = query.offset(skip).limit(limit).all()
    if not keywords:
        return []

    from app.models.keyword_url import KeywordSearchUrl
    asins = list({k.source_product_asin for k in keywords if k.source_product_asin})
    url_rows = db.query(KeywordSearchUrl).filter(
        KeywordSearchUrl.source_product_asin.in_(asins),
        KeywordSearchUrl.marketplace == "amazon"
    ).all() if asins else []
    url_map = {(u.source_product_asin.strip().lower(), u.keyword.strip().lower()): u for u in url_rows}

    res = []
    for k in keywords:
        u = url_map.get((k.source_product_asin.strip().lower() if k.source_product_asin else "", k.keyword.strip().lower()))
        res.append({
            "id": k.id,
            "keyword": k.keyword,
            "source": k.source,
            "source_product_asin": k.source_product_asin,
            "category": k.category,
            "relevance_score": k.relevance_score,
            "url_1": u.url_1 if u and u.url_1 else None,
            "url_2": u.url_2 if u and u.url_2 else None,
            "url_3": u.url_3 if u and u.url_3 else None,
            "url_4": u.url_4 if u and u.url_4 else None,
            "url_5": u.url_5 if u and u.url_5 else None,
            "created_at": k.created_at,
            "updated_at": k.updated_at,
        })
    return res

@router.post("", response_model=KeywordResponse, status_code=status.HTTP_201_CREATED, summary="Create Keyword")
def create_keyword(
    keyword_in: KeywordCreate,
    db: Session = Depends(get_db)
):
    # Check if unique constraint would be violated
    existing = db.query(Keyword).filter(
        Keyword.keyword == keyword_in.keyword,
        Keyword.source_product_asin == keyword_in.source_product_asin,
        Keyword.source == keyword_in.source
    ).first()

    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Keyword '{keyword_in.keyword}' already exists for ASIN '{keyword_in.source_product_asin}' and source '{keyword_in.source}'"
        )

    db_keyword = Keyword(
        keyword=keyword_in.keyword,
        source=keyword_in.source,
        source_product_asin=keyword_in.source_product_asin,
        category=keyword_in.category,
        relevance_score=keyword_in.relevance_score
    )

    try:
        db.add(db_keyword)
        db.commit()
        db.refresh(db_keyword)
        return db_keyword
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Duplicate keyword entry detected."
        )

@router.get("/{keyword_id}", response_model=KeywordResponse, summary="Get Keyword by ID")
def get_keyword(
    keyword_id: int,
    db: Session = Depends(get_db)
):
    db_keyword = db.query(Keyword).filter(Keyword.id == keyword_id).first()
    if not db_keyword:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Keyword with ID {keyword_id} not found"
        )
    return db_keyword

@router.put("/{keyword_id}", response_model=KeywordResponse, summary="Update Keyword")
def update_keyword(
    keyword_id: int,
    keyword_in: KeywordUpdate,
    db: Session = Depends(get_db)
):
    db_keyword = db.query(Keyword).filter(Keyword.id == keyword_id).first()
    if not db_keyword:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Keyword with ID {keyword_id} not found"
        )

    update_data = keyword_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(db_keyword, field, value)

    try:
        db.commit()
        db.refresh(db_keyword)
        return db_keyword
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Update conflicts with existing keyword constraint."
        )

@router.delete("/{keyword_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete Keyword")
def delete_keyword(
    keyword_id: int,
    db: Session = Depends(get_db)
):
    db_keyword = db.query(Keyword).filter(Keyword.id == keyword_id).first()
    if not db_keyword:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Keyword with ID {keyword_id} not found"
        )

    db.delete(db_keyword)
    db.commit()
    return None
