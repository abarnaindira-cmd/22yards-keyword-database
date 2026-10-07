import os
import sys
import json
import pandas as pd
import openpyxl

sys.stdout.reconfigure(encoding='utf-8')

from app.database import SessionLocal
from app.models.product import Product
from app.models.final_product_data import FinalProductData

def export_and_validate_batch3():
    db = SessionLocal()

    # 1. Fetch expected 100 Batch 3 products (IDs 204 to 303)
    b3_prods = db.query(Product).order_by(Product.id.asc()).offset(200).limit(100).all()
    b3_asins = [p.asin for p in b3_prods if p.asin]

    assert len(b3_prods) == 100, f"Expected 100 Batch 3 products, found {len(b3_prods)}"

    # 2. Fetch existing final_product_data records
    b3_fd = db.query(FinalProductData).filter(FinalProductData.sku_id.in_(b3_asins)).all()
    b3_fd_map = {fd.sku_id: fd for fd in b3_fd}

    # 3. Check status counts
    groq_count = 0
    manual_review_count = 0
    legacy_fallback_count = 0
    failed_count = 0

    export_rows = []

    for idx, p in enumerate(b3_prods, 201):
        asin = p.asin
        fd = b3_fd_map.get(asin)

        if not fd:
            failed_count += 1
            status = "MISSING_RECORD"
            title = ""
            kws = ""
        else:
            title = fd.final_product_title or ""

            # Format keywords cell as clean comma-separated string
            kws_val = fd.all_keywords
            if isinstance(kws_val, list):
                kws = ", ".join([str(x) for x in kws_val])
            elif isinstance(kws_val, str):
                try:
                    parsed = json.loads(kws_val)
                    if isinstance(parsed, list):
                        kws = ", ".join([str(x) for x in parsed])
                    else:
                        kws = str(parsed)
                except Exception:
                    kws = kws_val
            else:
                kws = str(kws_val) if kws_val else ""

            if title == "MANUAL_REVIEW_REQUIRED":
                manual_review_count += 1
                status = "MANUAL_REVIEW_REQUIRED"
            elif " | " in title:
                legacy_fallback_count += 1
                status = "LEGACY_KEYWORD_FALLBACK"
            elif title:
                groq_count += 1
                status = "GROQ_AI_GENERATED"
            else:
                failed_count += 1
                status = "EMPTY_TITLE"

        export_rows.append({
            "product_name": p.product_name,
            "sku_id": asin,
            "final_product_title": title,
            "all_keywords": kws,
            "generation_method": status
        })

    # 4. Save Excel to scratch folder
    output_filepath = os.path.join("scratch", "Batch_3_Database_Export.xlsx")
    df = pd.DataFrame(export_rows)

    required_cols = ["product_name", "sku_id", "final_product_title", "all_keywords", "generation_method"]
    df = df[required_cols]

    with pd.ExcelWriter(output_filepath, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="Batch 3 Final Data", index=False)

    print("==========================================================================")
    print("BATCH 3 DATABASE STATUS & EXPORT VALIDATION REPORT")
    print("==========================================================================")
    print(f"Total Batch 3 Products Expected : {len(b3_prods)}")
    print(f"Total Batch 3 Database Rows      : {len(b3_fd)}")
    print(f"First Expected SKU (ID {b3_prods[0].id})   : {b3_asins[0]}")
    print(f"Last Expected SKU  (ID {b3_prods[-1].id})  : {b3_asins[-1]}\n")

    print("--- 1. PROCESSING METRICS BREAKDOWN ---")
    print(f"  - Groq AI Generated Titles     : {groq_count}")
    print(f"  - Marked MANUAL_REVIEW_REQUIRED: {manual_review_count}")
    print(f"  - Legacy Fallback Pipe Titles   : {legacy_fallback_count}")
    print(f"  - Failed / Missing Records     : {failed_count}\n")

    # 5. Validate Excel File
    print("--- 2. EXCEL EXPORT VALIDATION ---")
    wb = openpyxl.load_workbook(output_filepath)
    sheet = wb.active
    rows_cnt = sheet.max_row
    cols_cnt = sheet.max_column
    headers = [sheet.cell(row=1, column=c).value for c in range(1, cols_cnt + 1)]
    exported_skus = [sheet.cell(row=r, column=2).value for r in range(2, rows_cnt + 1) if sheet.cell(row=r, column=2).value]

    print(f"  - Export File Path             : {os.path.abspath(output_filepath)}")
    print(f"  - File Size                    : {os.path.getsize(output_filepath)} bytes")
    print(f"  - Total Rows (Header + Data)   : {rows_cnt}")
    print(f"  - Total Columns                : {cols_cnt}")
    print(f"  - Export Headers               : {headers}")
    print(f"  - First Exported SKU           : {exported_skus[0]}")
    print(f"  - Last Exported SKU            : {exported_skus[-1]}")

    assert rows_cnt == 101, f"Expected 101 rows (1 header + 100 data), got {rows_cnt}"
    assert cols_cnt == 5, f"Expected 5 columns, got {cols_cnt}"
    assert headers == required_cols, f"Header mismatch: {headers}"
    assert len(exported_skus) == 100, f"Expected 100 SKUs, got {len(exported_skus)}"
    assert set(exported_skus) == set(b3_asins), "Exported SKU set does not match database expected SKUs!"
    assert exported_skus[0] == b3_asins[0], f"First SKU mismatch: {exported_skus[0]} vs {b3_asins[0]}"
    assert exported_skus[-1] == b3_asins[-1], f"Last SKU mismatch: {exported_skus[-1]} vs {b3_asins[-1]}"

    print("\n>>> EXCEL EXPORT VALIDATION PASSED PERFECTLY!")

    # 6. Verify Batch 1 & 2 Integrity
    b1_prods = db.query(Product).order_by(Product.id.asc()).offset(0).limit(100).all()
    b1_asins = [p.asin for p in b1_prods]
    b1_fd = db.query(FinalProductData).filter(FinalProductData.sku_id.in_(b1_asins)).all()

    b2_prods = db.query(Product).order_by(Product.id.asc()).offset(100).limit(100).all()
    b2_asins = [p.asin for p in b2_prods]
    b2_fd = db.query(FinalProductData).filter(FinalProductData.sku_id.in_(b2_asins)).all()

    print("\n--- 3. BATCH 1 & BATCH 2 INTEGRITY CHECK ---")
    print(f"  - Batch 1 Database Records     : {len(b1_fd)} / 100")
    print(f"  - Batch 2 Database Records     : {len(b2_fd)} / 100")
    assert len(b1_fd) == 100 and len(b2_fd) == 100, "Batch 1 or Batch 2 records modified!"
    print(">>> BATCH 1 AND BATCH 2 REMAIN 100% UNTOUCHED!")

    db.close()

if __name__ == "__main__":
    export_and_validate_batch3()
