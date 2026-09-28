import json
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Query, Response
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.database import get_db
from app.models.product import Product
from app.models.keyword import Keyword
from app.models.competitor import CompetitorProduct, CompetitorKeyword
from app.schemas.product import (
    ProductCreate,
    ProductUpdate,
    ProductResponse,
    ProductUploadResponse
)
from app.services.excel_processor import parse_products_excel

router = APIRouter(prefix="/api/products", tags=["Products"])

@router.post("/match-excel", summary="Match Uploaded Excel Products with Existing MySQL Data")
async def match_products_excel(
    file: UploadFile = File(..., description="Excel spreadsheet (.xlsx or .xls)"),
    db: Session = Depends(get_db)
):
    """
    Parse uploaded Excel file, match products with MySQL database by ASIN or Product Name,
    and return existing matched data (keywords, competitor products, and details) without re-scraping.
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
            detail="No valid product rows with ASIN and Product Name found in the uploaded Excel file."
        )

    matched_products = []
    unmatched_products = []

    for item in parsed_products:
        asin = item.get("asin")
        prod_name = item.get("product_name")

        prod = None
        if asin:
            prod = db.query(Product).filter(Product.asin == asin).first()
        if not prod and prod_name:
            prod = db.query(Product).filter(Product.product_name == prod_name).first()

        if prod:
            kw_rows = db.query(Keyword).filter(Keyword.source_product_asin == prod.asin).all()
            keywords = [
                {
                    "id": k.id,
                    "keyword": k.keyword,
                    "source": k.source,
                    "relevance_score": k.relevance_score,
                }
                for k in kw_rows
            ]

            cp_rows = (
                db.query(CompetitorProduct)
                .filter(CompetitorProduct.source_product_asin == prod.asin)
                .order_by(CompetitorProduct.competitor_rank.asc())
                .all()
            )
            competitor_products = []
            for cp in cp_rows:
                bp_list = []
                if cp.bullet_points:
                    try:
                        bp_list = json.loads(cp.bullet_points)
                    except Exception:
                        bp_list = [cp.bullet_points]

                reviews_list = []
                if cp.reviews:
                    try:
                        reviews_list = json.loads(cp.reviews)
                    except Exception:
                        reviews_list = [cp.reviews]

                competitor_products.append({
                    "id": cp.id,
                    "source_product_asin": cp.source_product_asin,
                    "keyword": cp.keyword,
                    "competitor_asin": cp.competitor_asin,
                    "competitor_rank": cp.competitor_rank,
                    "competitor_title": cp.competitor_title,
                    "product_url": cp.product_url,
                    "price": cp.price,
                    "rating": cp.rating,
                    "review_count": cp.review_count,
                    "description": cp.description,
                    "bullet_points": bp_list,
                    "reviews": reviews_list,
                    "marketplace": cp.marketplace,
                })

            ck_rows = (
                db.query(CompetitorKeyword)
                .filter(CompetitorKeyword.source_product_asin == prod.asin)
                .all()
            )
            competitor_keywords = [
                {
                    "id": ck.id,
                    "keyword": ck.keyword,
                    "competitor_asin": ck.competitor_asin,
                    "source": ck.source,
                    "relevance_score": ck.relevance_score,
                }
                for ck in ck_rows
            ]

            matched_products.append({
                "id": prod.id,
                "asin": prod.asin,
                "excel_asin": asin,
                "product_name": prod.product_name,
                "category": prod.category,
                "status": prod.status,
                "keyword_count": len(keywords),
                "competitor_count": len(competitor_products),
                "keywords": keywords,
                "competitor_products": competitor_products,
                "competitor_keywords": competitor_keywords,
                "matched": True
            })
        else:
            unmatched_products.append({
                "asin": asin,
                "product_name": prod_name,
                "category": item.get("category"),
                "matched": False
            })

    return {
        "filename": file.filename,
        "total_excel_products": len(parsed_products),
        "matched_count": len(matched_products),
        "unmatched_count": len(unmatched_products),
        "matched_products": matched_products,
        "unmatched_products": unmatched_products
    }


@router.post("/upload-excel", response_model=ProductUploadResponse, summary="Upload Excel Product File")
async def upload_products_excel(
    file: UploadFile = File(..., description="Excel spreadsheet (.xlsx) containing product ASIN, title/name, and category"),
    db: Session = Depends(get_db)
):
    """
    Ingest product list from Excel (.xlsx) file into MySQL database 'marketlens'.
    Upserts product records by ASIN.
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
            detail="No valid product rows with ASIN and Product Name found in the uploaded Excel file."
        )

    imported_count = 0
    updated_count = 0

    for prod_data in parsed_products:
        existing = db.query(Product).filter(Product.asin == prod_data["asin"]).first()
        if existing:
            existing.product_name = prod_data["product_name"]
            if prod_data.get("category"):
                existing.category = prod_data["category"]
            existing.status = "pending"
            updated_count += 1
        else:
            new_prod = Product(
                asin=prod_data["asin"],
                product_name=prod_data["product_name"],
                category=prod_data.get("category"),
                status="pending"
            )
            db.add(new_prod)
            imported_count += 1

    db.commit()

    return ProductUploadResponse(
        filename=file.filename,
        total_rows=len(parsed_products),
        imported_count=imported_count,
        skipped_count=updated_count,
        message=f"Successfully processed {len(parsed_products)} products ({imported_count} imported new, {updated_count} updated)."
    )

from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Query, Response

@router.get("", response_model=List[ProductResponse], summary="List Products")
def list_products(
    response: Response,
    asin: Optional[str] = Query(None, description="Filter by ASIN"),
    status: Optional[str] = Query(None, description="Filter by Status (pending, in_progress, completed)"),
    category: Optional[str] = Query(None, description="Filter by Category"),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db)
):
    """Retrieve stored products from MySQL database 'marketlens' ordered by product ID ascending."""
    query = db.query(Product)
    if asin:
        query = query.filter(Product.asin == asin)
    if status:
        query = query.filter(Product.status == status)
    if category:
        query = query.filter(Product.category == category)

    total_count = query.count()
    response.headers["X-Total-Count"] = str(total_count)
    response.headers["Access-Control-Expose-Headers"] = "X-Total-Count"

    return query.order_by(Product.id.asc()).offset(skip).limit(limit).all()

@router.get("/{product_id}", response_model=ProductResponse, summary="Get Product by ID")
def get_product(
    product_id: int,
    db: Session = Depends(get_db)
):
    """Get a single product record by ID."""
    prod = db.query(Product).filter(Product.id == product_id).first()
    if not prod:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Product with ID {product_id} not found."
        )
    return prod

@router.delete("/{product_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete Product")
def delete_product(
    product_id: int,
    db: Session = Depends(get_db)
):
    """Delete a product record from MySQL."""
    prod = db.query(Product).filter(Product.id == product_id).first()
    if not prod:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Product with ID {product_id} not found."
        )
    db.delete(prod)
    db.commit()
    return None
