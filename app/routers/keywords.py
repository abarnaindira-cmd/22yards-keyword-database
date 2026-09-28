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
    
    return query.offset(skip).limit(limit).all()

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
