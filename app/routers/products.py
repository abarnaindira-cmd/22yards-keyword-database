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
            from app.models.keyword_url import KeywordSearchUrl

            kw_rows = db.query(Keyword).filter(Keyword.source_product_asin == prod.asin).all()
            url_rows = db.query(KeywordSearchUrl).filter(
                KeywordSearchUrl.source_product_asin == prod.asin,
                KeywordSearchUrl.marketplace == "amazon"
            ).all()
            url_map = {u.keyword.strip().lower(): u for u in url_rows}

            keywords = []
            for k in kw_rows:
                u = url_map.get(k.keyword.strip().lower())
                keywords.append({
                    "id": k.id,
                    "keyword": k.keyword,
                    "source": k.source,
                    "relevance_score": k.relevance_score,
                    "url_1": u.url_1 if u and u.url_1 else None,
                    "url_2": u.url_2 if u and u.url_2 else None,
                    "url_3": u.url_3 if u and u.url_3 else None,
                    "url_4": u.url_4 if u and u.url_4 else None,
                    "url_5": u.url_5 if u and u.url_5 else None,
                })

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

    from app.services.excel_exporter import set_current_batch_asins
    batch_asins = [p.get("asin") for p in parsed_products if p.get("asin")]
    if batch_asins:
        set_current_batch_asins(batch_asins)

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

@router.post("/generate-final-data", summary="Generate Final Product Data and Titles")
def generate_final_data(
    sku_id: Optional[str] = Query(None, description="Optional specific product SKU ID (ASIN) to process"),
    limit: Optional[int] = Query(None, description="Max number of products to process"),
    db: Session = Depends(get_db)
):
    """
    Generate final product title using Groq LLM (or fallback), combine keywords into JSON,
    and upsert records into MySQL 'final_product_data' table.
    """
    from app.services.title_generator import process_final_product_data_for_asin, process_all_final_product_data
    try:
        if sku_id:
            res = process_final_product_data_for_asin(db=db, sku_id=sku_id)
            if "error" in res:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=res["error"])
            return res
        else:
            return process_all_final_product_data(db=db, limit=limit)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Final product data generation failed: {str(e)}"
        )

class FinalDataExportPayload(BaseModel if 'BaseModel' in globals() else object):
    pass

@router.get("/export-final-product-data", summary="Export Final Product Data Report to Excel")
def export_final_product_data(
    sku_id: Optional[str] = Query(None, description="Optional SKU ID (ASIN) filter"),
    asins: Optional[str] = Query(None, description="Optional comma-separated list of ASINs/SKUs to export"),
    skip: Optional[int] = Query(None, ge=0, description="Optional pagination offset for batch selection"),
    limit: Optional[int] = Query(None, ge=1, le=500, description="Optional pagination limit for batch selection"),
    batch_index: Optional[int] = Query(None, ge=1, description="Optional 1-based batch index (1 = Products 1-100, 2 = Products 101-200)"),
    db: Session = Depends(get_db)
):
    """
    Export 'final_product_data' table records into a single worksheet Excel file (.xlsx)
    with columns: product_name, sku_id, final_product_title, all_keywords.
    Exports strictly the selected/uploaded batch (or specified ASINs/SKU/batch index) and validates SKU equality.
    """
    import os
    from fastapi.responses import FileResponse
    from app.services.excel_exporter import export_final_product_data_to_excel, set_current_batch_asins

    try:
        asins_list = None
        if sku_id:
            asins_list = None
        elif asins:
            asins_list = [a.strip() for a in asins.split(",") if a.strip()]
        elif batch_index is not None:
            offset = (batch_index - 1) * 100
            prods = db.query(Product).order_by(Product.id.asc()).offset(offset).limit(100).all()
            asins_list = [p.asin for p in prods if p.asin]
        elif skip is not None and limit is not None:
            prods = db.query(Product).order_by(Product.id.asc()).offset(skip).limit(limit).all()
            asins_list = [p.asin for p in prods if p.asin]

        if asins_list:
            set_current_batch_asins(asins_list)

        filepath = export_final_product_data_to_excel(db=db, sku_id=sku_id, asins_list=asins_list)
        filename = os.path.basename(filepath)
        return FileResponse(
            path=filepath,
            filename=filename,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    except ValueError as ve:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(ve)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Export failed: {str(e)}"
        )

@router.get("/final-data", summary="Get Final Product Data Records")
def get_final_product_data_list(
    sku_id: Optional[str] = Query(None, description="Filter by SKU ID (ASIN)"),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db)
):
    """
    Retrieve stored records from MySQL table 'final_product_data'.
    """
    from app.models.final_product_data import FinalProductData
    query = db.query(FinalProductData)
    if sku_id:
        query = query.filter(FinalProductData.sku_id == sku_id)
    return query.order_by(FinalProductData.sku_id.asc()).offset(skip).limit(limit).all()

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


