import os
from typing import Optional, List
import pandas as pd
from sqlalchemy import text
from sqlalchemy.orm import Session

def export_harvested_keywords_to_excel(
    db: Session,
    source_product_asin: Optional[str] = None,
    output_filepath: Optional[str] = None,
    file_format: str = "excel"
) -> str:
    """
    Export Harvested Keywords report to Excel or CSV using stored data in MySQL.
    Reads keywords and joins stored Amazon URLs from 'keyword_search_urls' table using:
      TRIM(LOWER(k.source_product_asin)) = TRIM(LOWER(u.source_product_asin))
      AND TRIM(LOWER(k.keyword)) = TRIM(LOWER(u.keyword))
      AND u.marketplace = 'amazon'
    Populates columns A-J (F-J containing stored Amazon URLs) without making any new live search requests.
    """
    sql_query = """
    SELECT 
        k.source_product_asin AS `Source Product ASIN`,
        COALESCE(p.product_name, '') AS `Source Product Name`,
        k.keyword AS `Keyword Phrase`,
        k.source AS `Source`,
        COALESCE(k.relevance_score, 0.0) AS `Relevance Score`,
        COALESCE(u.url_1, '') AS `Amazon Product URL 1`,
        COALESCE(u.url_2, '') AS `Amazon Product URL 2`,
        COALESCE(u.url_3, '') AS `Amazon Product URL 3`,
        COALESCE(u.url_4, '') AS `Amazon Product URL 4`,
        COALESCE(u.url_5, '') AS `Amazon Product URL 5`
    FROM keywords k
    LEFT JOIN products p 
        ON TRIM(LOWER(k.source_product_asin)) = TRIM(LOWER(p.asin))
    LEFT JOIN keyword_search_urls u 
        ON TRIM(LOWER(k.source_product_asin)) = TRIM(LOWER(u.source_product_asin)) 
       AND TRIM(LOWER(k.keyword)) = TRIM(LOWER(u.keyword))
       AND LOWER(u.marketplace) = 'amazon'
    WHERE LOWER(k.marketplace) = 'amazon'
    """

    params = {}
    if source_product_asin:
        sql_query += " AND TRIM(LOWER(k.source_product_asin)) = :asin"
        params["asin"] = source_product_asin.strip().lower()

    sql_query += " ORDER BY (CASE WHEN p.id IS NOT NULL THEN 0 ELSE 1 END) ASC, p.id ASC, (CASE WHEN u.url_1 IS NOT NULL AND u.url_1 != '' THEN 0 ELSE 1 END) ASC, k.source_product_asin ASC, k.id ASC;"

    df = pd.read_sql(text(sql_query), con=db.bind, params=params)

    # Ensure blank values are empty strings rather than NaN
    url_cols = [
        "Amazon Product URL 1",
        "Amazon Product URL 2",
        "Amazon Product URL 3",
        "Amazon Product URL 4",
        "Amazon Product URL 5"
    ]
    for col in url_cols:
        df[col] = df[col].fillna("").astype(str)

    ext = ".csv" if file_format.lower() == "csv" else ".xlsx"
    if not output_filepath:
        current_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        if source_product_asin:
            filename = f"{source_product_asin}_Harvested_Keywords{ext}"
        else:
            filename = f"Harvested_Keywords_All_Products{ext}"
        output_filepath = os.path.join(current_dir, filename)

    if file_format.lower() == "csv":
        df.to_csv(output_filepath, index=False, encoding="utf-8")
    else:
        with pd.ExcelWriter(output_filepath, engine="openpyxl") as writer:
            df.to_excel(writer, sheet_name="Harvested Keywords", index=False)

    return output_filepath

PERSISTENT_BATCH_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "scratch",
    "active_batch_asins.json"
)

CURRENT_BATCH_ASINS: List[str] = []

def set_current_batch_asins(asins: List[str]):
    """Store/track and persist the active uploaded/selected product batch ASINs."""
    global CURRENT_BATCH_ASINS
    clean_asins = [a.strip() for a in asins if a and isinstance(a, str)]
    CURRENT_BATCH_ASINS = clean_asins
    try:
        os.makedirs(os.path.dirname(PERSISTENT_BATCH_FILE), exist_ok=True)
        import json
        with open(PERSISTENT_BATCH_FILE, "w", encoding="utf-8") as f:
            json.dump(clean_asins, f, indent=2)
    except Exception as e:
        import logging
        logging.getLogger("excel_exporter").warning(f"Failed to persist batch ASINs to file: {e}")

def get_current_batch_asins(db: Session) -> List[str]:
    """Get active uploaded/selected batch ASINs from memory, disk cache, or default to Batch 1 (IDs 4 to 103)."""
    global CURRENT_BATCH_ASINS
    if CURRENT_BATCH_ASINS:
        return CURRENT_BATCH_ASINS

    # Check persistent disk cache
    if os.path.exists(PERSISTENT_BATCH_FILE):
        try:
            import json
            with open(PERSISTENT_BATCH_FILE, "r", encoding="utf-8") as f:
                cached_asins = json.load(f)
                if isinstance(cached_asins, list) and len(cached_asins) > 0:
                    CURRENT_BATCH_ASINS = cached_asins
                    return CURRENT_BATCH_ASINS
        except Exception as e:
            import logging
            logging.getLogger("excel_exporter").warning(f"Failed to read persistent batch ASINs file: {e}")

    # Default to Batch 1 (IDs 4 to 103)
    from app.models.product import Product
    products = db.query(Product).filter(Product.id.between(4, 103)).order_by(Product.id.asc()).all()
    asins = [p.asin for p in products if p.asin]
    CURRENT_BATCH_ASINS = asins
    return CURRENT_BATCH_ASINS

def export_final_product_data_to_excel(
    db: Session,
    sku_id: Optional[str] = None,
    asins_list: Optional[List[str]] = None,
    output_filepath: Optional[str] = None
) -> str:
    """
    Export final product data from MySQL 'final_product_data' table to a single worksheet Excel file (.xlsx).
    Export is strictly filtered to the current selected/uploaded batch (or specified ASINs/SKU).
    Columns: product_name, sku_id, final_product_title, all_keywords (in exact order).
    Validates SKU equality before generating file.
    """
    import logging
    logger = logging.getLogger("excel_exporter")

    params = {}
    where_clauses = []
    target_skus: List[str] = []

    if sku_id:
        where_clauses.append("TRIM(LOWER(sku_id)) = :sku_id")
        params["sku_id"] = sku_id.strip().lower()
        target_skus = [sku_id.strip()]
    else:
        target_asins = asins_list if asins_list else get_current_batch_asins(db)
        clean_asins = [a.strip() for a in target_asins if a]
        target_skus = clean_asins
        if clean_asins:
            where_clauses.append("TRIM(LOWER(sku_id)) IN :asins_list")
            params["asins_list"] = tuple(a.lower() for a in clean_asins)

    sql_query = """
    SELECT 
        product_name AS `product_name`,
        sku_id AS `sku_id`,
        final_product_title AS `final_product_title`,
        all_keywords AS `all_keywords`
    FROM final_product_data
    """
    if where_clauses:
        sql_query += " WHERE " + " AND ".join(where_clauses)

    sql_query += " ORDER BY sku_id ASC;"

    df = pd.read_sql(text(sql_query), con=db.bind, params=params)

    # Convert all_keywords JSON list into a single clean string per cell
    def format_keywords_cell(val):
        if not val:
            return ""
        if isinstance(val, str):
            try:
                import json
                parsed = json.loads(val)
                if isinstance(parsed, list):
                    return ", ".join([str(x) for x in parsed])
                return str(parsed)
            except Exception:
                return val
        elif isinstance(val, list):
            return ", ".join([str(x) for x in val])
        return str(val)

    if not df.empty and "all_keywords" in df.columns:
        df["all_keywords"] = df["all_keywords"].apply(format_keywords_cell)

    # Re-order columns strictly: product_name, sku_id, final_product_title, all_keywords
    required_cols = ["product_name", "sku_id", "final_product_title", "all_keywords"]
    for col in required_cols:
        if col not in df.columns:
            df[col] = ""
    df = df[required_cols]

    # Re-order rows according to target_skus selection order if specified
    if target_skus and not df.empty:
        sku_order_map = {sku.lower(): idx for idx, sku in enumerate(target_skus)}
        df['_sort_key'] = df['sku_id'].astype(str).str.strip().str.lower().map(sku_order_map)
        df = df.sort_values('_sort_key').drop(columns=['_sort_key'])

    # STRICT SKU VALIDATION BEFORE EXPORT
    if target_skus:
        exported_skus = df["sku_id"].dropna().astype(str).str.strip().tolist()
        import collections
        counts = collections.Counter(exported_skus)
        duplicate_skus = [sku for sku, cnt in counts.items() if cnt > 1]

        target_set = set(a.lower() for a in target_skus)
        exported_set = set(a.lower() for a in exported_skus)

        missing_skus = [a for a in target_skus if a.lower() not in exported_set]
        extra_skus = [a for a in exported_skus if a.lower() not in target_set]

        if missing_skus or extra_skus or duplicate_skus:
            err_msg = (
                f"Batch Export Validation Mismatch! "
                f"Expected {len(target_skus)} SKUs, found {len(exported_skus)} exported. "
                f"Missing ({len(missing_skus)}): {missing_skus[:5]}. "
                f"Extra ({len(extra_skus)}): {extra_skus[:5]}. "
                f"Duplicates ({len(duplicate_skus)}): {duplicate_skus[:5]}."
            )
            logger.error(err_msg)
            raise ValueError(err_msg)

    if not output_filepath:
        current_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        if sku_id:
            filename = f"{sku_id}_Final_Product_Data.xlsx"
        else:
            filename = "Final_Product_Data.xlsx"
        output_filepath = os.path.join(current_dir, filename)

    with pd.ExcelWriter(output_filepath, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="Final Product Data", index=False)

    return output_filepath

