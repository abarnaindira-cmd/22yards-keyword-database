from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query, Response, UploadFile, File
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.database import get_db, get_flipkart_db
from app.models.product import Product
from app.models.keyword import Keyword
from app.services.excel_processor import parse_products_excel
from app.services.flipkart_suggestion_runner import (
    collect_flipkart_keywords_for_product,
    run_flipkart_batch_keyword_collection
)

router = APIRouter(prefix="/api/flipkart", tags=["Flipkart"])


@router.post("/match-excel", summary="Process Uploaded Excel File for Flipkart Collection Session")
async def match_flipkart_excel(
    file: UploadFile = File(..., description="Excel spreadsheet (.xlsx or .xls)"),
    db_main: Session = Depends(get_db),
    db_fk: Session = Depends(get_flipkart_db)
):
    """
    Parse uploaded Excel spreadsheet for Flipkart, match each product in MySQL,
    run keyword collection for missing products, and return session-specific results.
    """
    if not file.filename.lower().endswith((".xlsx", ".xls")):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid file format. Please upload an Excel file (.xlsx or .xls)."
        )

    try:
        content = await file.read()
        parsed_products = parse_products_excel(content)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Failed to parse Excel file: {str(e)}"
        )

    if not parsed_products:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No valid product rows with ASIN/FSN and Product Name found in the uploaded Excel file."
        )

    session_products = []
    successful_count = 0
    no_keywords_count = 0
    total_keywords_collected = 0

    for item in parsed_products:
        raw_asin = item.get("asin")
        raw_name = item.get("product_name")
        raw_cat = item.get("category")

        # 1. Match in main database
        prod = None
        if raw_asin:
            prod = db_main.query(Product).filter(Product.asin == raw_asin).first()
        if not prod and raw_name:
            prod = db_main.query(Product).filter(Product.product_name == raw_name).first()

        # If not in main database, create product entry
        if not prod:
            prod = Product(
                asin=raw_asin,
                product_name=raw_name,
                category=raw_cat,
                marketplace="flipkart",
                status="pending",
                flipkart_status="pending"
            )
            db_main.add(prod)
            db_main.commit()
            db_main.refresh(prod)

        # Also ensure product exists in marketlens_flipkart DB
        prod_fk = db_fk.query(Product).filter(Product.id == prod.id).first()
        if not prod_fk:
            prod_fk = db_fk.query(Product).filter(Product.asin == prod.asin).first()
        if not prod_fk:
            prod_fk = Product(
                id=prod.id,
                asin=prod.asin,
                product_name=prod.product_name,
                category=prod.category,
                marketplace="flipkart",
                status="pending",
                flipkart_status="pending"
            )
            db_fk.add(prod_fk)
            try:
                db_fk.commit()
                db_fk.refresh(prod_fk)
            except Exception:
                db_fk.rollback()

        # 2. Check existing stored keywords or run collection
        keywords = db_fk.query(Keyword).filter(
            Keyword.source_product_asin == prod.asin,
            Keyword.marketplace == "flipkart",
            Keyword.source == "flipkart_search_suggestions"
        ).all()
        if not keywords:
            keywords = db_main.query(Keyword).filter(
                Keyword.source_product_asin == prod.asin,
                Keyword.marketplace == "flipkart",
                Keyword.source == "flipkart_search_suggestions"
            ).all()

        # If no keywords exist, run collection for this product
        if not keywords:
            try:
                new_kws = collect_flipkart_keywords_for_product(db_fk, prod_fk or prod, delay_seconds=0.3)
                keywords = new_kws
            except Exception as err:
                print(f"[Flipkart Session] Scraper error for product {prod.asin}: {err}")
                keywords = []

        kw_count = len(keywords)

        if kw_count > 0:
            prod.flipkart_status = "completed"
            if prod_fk:
                prod_fk.flipkart_status = "completed"
            successful_count += 1
            total_keywords_collected += kw_count
            status_label = "Completed"
            keywords_status = "completed"
            success = True
        else:
            # Explicit requirement C: If no keywords available, mark "Keywords Not Available"
            no_keywords_count += 1
            status_label = "Keywords Not Available"
            keywords_status = "no_keywords"
            success = False

        try:
            db_main.commit()
            if prod_fk:
                db_fk.commit()
        except Exception:
            db_main.rollback()
            db_fk.rollback()

        session_products.append({
            "id": prod.id,
            "asin": prod.asin,
            "product_name": prod.product_name,
            "category": prod.category or "General",
            "flipkart_status": prod.flipkart_status,
            "keyword_count": kw_count,
            "keywords_status": keywords_status,
            "status_label": status_label,
            "success": success
        })

    return {
        "filename": file.filename,
        "total_excel_products": len(parsed_products),
        "successful_products": successful_count,
        "no_keywords_count": no_keywords_count,
        "total_keywords_collected": total_keywords_collected,
        "products": session_products
    }



@router.get("/summary", summary="Get Flipkart Keyword Collection Statistics")
def get_flipkart_summary(
    db_main: Session = Depends(get_db),
    db_fk: Session = Depends(get_flipkart_db)
):
    """
    Returns summary metrics for Flipkart processing using flipkart_status 
    from the primary MySQL database and keywords table.
    """
    total_products = db_main.query(Product).count()
    completed_products = db_main.query(Product).filter(Product.flipkart_status == "completed").count()
    pending_products = db_main.query(Product).filter(Product.flipkart_status == "pending").count()
    failed_products = db_main.query(Product).filter(Product.flipkart_status == "failed").count()
    in_progress_products = db_main.query(Product).filter(Product.flipkart_status == "in_progress").count()

    total_keywords = db_fk.query(Keyword).filter(
        Keyword.marketplace == "flipkart",
        Keyword.source == "flipkart_search_suggestions"
    ).count()
    if total_keywords == 0:
        total_keywords = db_main.query(Keyword).filter(
            Keyword.marketplace == "flipkart",
            Keyword.source == "flipkart_search_suggestions"
        ).count()

    return {
        "total_products": total_products,
        "completed_products": completed_products,
        "pending_products": pending_products,
        "failed_products": failed_products,
        "in_progress_products": in_progress_products,
        "total_keywords": total_keywords
    }


@router.get("/products", summary="List Products for Flipkart Interface")
def list_flipkart_products(
    response: Response,
    status_filter: Optional[str] = Query(None, alias="status", description="Filter by flipkart_status (all, pending, completed, failed, in_progress)"),
    category: Optional[str] = Query(None, description="Filter by Category"),
    search: Optional[str] = Query(None, description="Search by ASIN/FSN or Product Name"),
    sort: Optional[str] = Query("id_asc", description="Sort order (id_asc, id_desc, kw_desc, name_asc)"),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db_main: Session = Depends(get_db),
    db_fk: Session = Depends(get_flipkart_db)
):
    """
    List products with Flipkart-specific processing status (flipkart_status)
    from MySQL products table and count of collected Flipkart keywords.
    """
    query = db_main.query(Product)

    if status_filter and status_filter.lower() != "all":
        query = query.filter(Product.flipkart_status == status_filter.lower())

    if category and category.lower() != "all":
        query = query.filter(Product.category == category)

    if search and search.strip():
        term = f"%{search.strip()}%"
        query = query.filter(
            or_(
                Product.asin.like(term),
                Product.product_name.like(term)
            )
        )

    total_count = query.count()
    response.headers["X-Total-Count"] = str(total_count)
    response.headers["Access-Control-Expose-Headers"] = "X-Total-Count"

    # Efficient aggregate for keyword counts per ASIN for Flipkart
    kw_counts = dict(
        db_fk.query(Keyword.source_product_asin, func.count(Keyword.id))
        .filter(Keyword.marketplace == "flipkart", Keyword.source == "flipkart_search_suggestions")
        .group_by(Keyword.source_product_asin)
        .all()
    )
    if not kw_counts:
        kw_counts = dict(
            db_main.query(Keyword.source_product_asin, func.count(Keyword.id))
            .filter(Keyword.marketplace == "flipkart", Keyword.source == "flipkart_search_suggestions")
            .group_by(Keyword.source_product_asin)
            .all()
        )

    if sort == "id_desc":
        query = query.order_by(Product.id.desc())
    elif sort == "name_asc":
        query = query.order_by(Product.product_name.asc())
    else:
        query = query.order_by(Product.id.asc())

    products = query.offset(skip).limit(limit).all()

    result = []
    for p in products:
        # Enforce rule: Do not show Flipkart keyword data for products whose flipkart_status is still pending
        cnt = kw_counts.get(p.asin, 0) if p.flipkart_status == "completed" else 0
        result.append({
            "id": p.id,
            "asin": p.asin,
            "product_name": p.product_name,
            "category": p.category,
            "flipkart_status": p.flipkart_status,
            "amazon_status": p.status,
            "marketplace": p.marketplace,
            "keyword_count": cnt,
            "created_at": p.created_at.isoformat() if p.created_at else None,
            "updated_at": p.updated_at.isoformat() if p.updated_at else None,
        })

    if sort == "kw_desc":
        result.sort(key=lambda x: x["keyword_count"], reverse=True)

    return result


@router.get("/products/{product_id}", summary="Get Single Flipkart Product and its Keywords")
def get_flipkart_product_detail(
    product_id: int,
    db_main: Session = Depends(get_db),
    db_fk: Session = Depends(get_flipkart_db)
):
    """
    Get detailed Flipkart product info and all collected Flipkart keywords.
    Pending Flipkart products do not return keyword data.
    """
    prod = db_main.query(Product).filter(Product.id == product_id).first()
    if not prod:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Product with ID {product_id} not found."
        )

    # Do NOT show Flipkart keyword data for products whose flipkart_status is still pending
    if prod.flipkart_status != "completed":
        keywords = []
    else:
        keywords = (
            db_fk.query(Keyword)
            .filter(
                Keyword.source_product_asin == prod.asin,
                Keyword.marketplace == "flipkart",
                Keyword.source == "flipkart_search_suggestions"
            )
            .order_by(Keyword.id.asc())
            .all()
        )
        if not keywords:
            keywords = (
                db_main.query(Keyword)
                .filter(
                    Keyword.source_product_asin == prod.asin,
                    Keyword.marketplace == "flipkart",
                    Keyword.source == "flipkart_search_suggestions"
                )
                .order_by(Keyword.id.asc())
                .all()
            )

    kw_list = [
        {
            "id": k.id,
            "keyword": k.keyword,
            "source": k.source,
            "source_product_asin": k.source_product_asin,
            "category": k.category,
            "marketplace": k.marketplace,
            "relevance_score": k.relevance_score,
            "created_at": k.created_at.isoformat() if k.created_at else None
        }
        for k in keywords
    ]

    return {
        "id": prod.id,
        "asin": prod.asin,
        "product_name": prod.product_name,
        "category": prod.category,
        "flipkart_status": prod.flipkart_status,
        "amazon_status": prod.status,
        "marketplace": prod.marketplace,
        "keyword_count": len(kw_list),
        "keywords": kw_list
    }


@router.post("/collect-batch", summary="Run Flipkart Keyword Collection Batch")
def collect_flipkart_batch(
    limit: int = Query(10, ge=1, le=100, description="Max pending Flipkart products to process"),
    product_id: Optional[int] = Query(None, description="Optional specific product ID to process"),
    db: Session = Depends(get_flipkart_db)
):
    """
    Run keyword collection batch for pending Flipkart products.
    """
    if product_id:
        prod = db.query(Product).filter(Product.id == product_id).first()
        if not prod:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Product with ID {product_id} not found."
            )
        kws = collect_flipkart_keywords_for_product(db, prod, delay_seconds=0.5)
        return {
            "total_products_processed": 1,
            "successful_products": 1 if prod.flipkart_status == "completed" else 0,
            "failed_products": 1 if prod.flipkart_status == "failed" else 0,
            "total_keywords_collected": len(kws),
            "product": {
                "id": prod.id,
                "asin": prod.asin,
                "flipkart_status": prod.flipkart_status,
                "keywords_count": len(kws)
            }
        }
    else:
        return run_flipkart_batch_keyword_collection(db, limit=limit, delay_seconds=0.5)


@router.get("/categories", summary="List Flipkart Categories")
def get_flipkart_categories(db_main: Session = Depends(get_db)):
    """Return distinct non-null categories from products table."""
    categories = (
        db_main.query(Product.category)
        .filter(Product.category.isnot(None), Product.category != "")
        .distinct()
        .all()
    )
    return [c[0] for c in categories if c[0]]

