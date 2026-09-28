import io
from typing import List, Dict, Any
import openpyxl

def parse_products_excel(file_bytes: bytes) -> List[Dict[str, Any]]:
    """
    Parse uploaded Excel file (.xlsx) and extract product records (ASIN/SKU, Product Name, Category).
    Identifies column headers flexibly regardless of exact case or spacing.
    """
    workbook = openpyxl.load_workbook(filename=io.BytesIO(file_bytes), data_only=True)
    sheet = workbook.active

    rows = list(sheet.iter_rows(values_only=True))
    if not rows:
        return []

    # Identify header row (first non-empty row)
    header_idx = 0
    header = None
    for idx, row in enumerate(rows):
        if row and any(cell is not None for cell in row):
            header = [str(cell).strip() if cell is not None else "" for cell in row]
            header_idx = idx
            break

    if not header:
        return []

    # Find column indices dynamically (exact matches first)
    asin_col = -1
    title_col = -1
    category_col = -1

    # Pass 1: Exact matches
    for i, col_name in enumerate(header):
        normalized = col_name.lower().strip().replace("_", " ").replace("-", " ")
        if normalized in ["sku id for market places", "sku id", "sku", "asin", "product asin", "item asin"]:
            asin_col = i
        elif normalized in ["name on brand website", "product name", "product title", "title", "item name"]:
            title_col = i
        elif normalized in ["product category", "category", "dept", "department"]:
            category_col = i

    # Pass 2: Partial matches if missing
    for i, col_name in enumerate(header):
        normalized = col_name.lower().strip().replace("_", " ").replace("-", " ")
        if asin_col == -1 and any(k in normalized for k in ["sku id", "sku", "asin"]):
            asin_col = i
        if title_col == -1 and any(k in normalized for k in ["name on brand website", "product name", "product title"]):
            title_col = i
        if category_col == -1 and any(k in normalized for k in ["product category", "category"]):
            category_col = i

    # Fallback column index defaults if header matching failed
    if asin_col == -1 and len(header) >= 1:
        asin_col = 0
    if title_col == -1 and len(header) >= 2:
        title_col = 1
    if category_col == -1 and len(header) >= 3:
        category_col = 2

    products = []
    for row in rows[header_idx + 1:]:
        if not row or all(cell is None for cell in row):
            continue

        raw_asin = str(row[asin_col]).strip() if asin_col < len(row) and row[asin_col] is not None else ""
        raw_title = str(row[title_col]).strip() if title_col < len(row) and row[title_col] is not None else ""
        raw_cat = str(row[category_col]).strip() if category_col < len(row) and row[category_col] is not None else None

        if not raw_asin or not raw_title or raw_asin.lower() == "none" or raw_title.lower() == "none":
            continue

        products.append({
            "asin": raw_asin,
            "product_name": raw_title,
            "category": raw_cat if raw_cat and raw_cat.lower() != "none" else None
        })

    return products
