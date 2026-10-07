import os
import openpyxl
import sys
sys.stdout.reconfigure(encoding='utf-8')

from sqlalchemy import text
from app.database import SessionLocal
from app.models.product import Product
from app.models.keyword import Keyword
from app.models.final_product_data import FinalProductData
from app.services.excel_exporter import export_final_product_data_to_excel, get_current_batch_asins
from app.services.title_generator import fallback_generate_title

def audit_products_101_to_200():
    db = SessionLocal()

    print("==========================================================================")
    print("AUDIT REPORT: PRODUCTS 101 TO 200 (IDs 104-203)")
    print("==========================================================================")

    # 1. Exact 100 selected product SKUs/ASINs
    # Query offset 100, limit 100 (Products 101-200)
    prods = db.query(Product).order_by(Product.id.asc()).offset(100).limit(100).all()
    selected_asins = [p.asin for p in prods if p.asin]

    print(f"\n1. SELECTED BATCH (PRODUCTS 101-200):")
    print(f"   - Total Selected Products : {len(prods)}")
    print(f"   - ID Range                : ID {prods[0].id} ('{prods[0].asin}') to ID {prods[-1].id} ('{prods[-1].asin}')")
    print(f"   - Sample ASINs (First 3)  : {selected_asins[:3]}")
    print(f"   - Sample ASINs (Last 3)   : {selected_asins[-3:]}")

    # 2. Whether each product already has collected keywords
    kw_rows = db.query(Keyword.source_product_asin, Keyword.keyword)\
                .filter(Keyword.source_product_asin.in_(selected_asins))\
                .all()

    asin_to_kws = {}
    for asin_val, kw_val in kw_rows:
        if asin_val not in asin_to_kws:
            asin_to_kws[asin_val] = []
        if kw_val:
            asin_to_kws[asin_val].append(kw_val)

    prods_with_kws = [a for a in selected_asins if len(asin_to_kws.get(a, [])) > 0]
    prods_without_kws = [a for a in selected_asins if len(asin_to_kws.get(a, [])) == 0]

    print(f"\n2. KEYWORD COLLECTION STATUS:")
    print(f"   - Products WITH Collected Keywords    : {len(prods_with_kws)}/100")
    print(f"   - Products WITHOUT Collected Keywords : {len(prods_without_kws)}/100")
    if prods_without_kws:
        print(f"   - ASINs missing keywords              : {prods_without_kws[:5]}")

    # 3. Groq Title Generation Source Status
    fpd_rows = db.query(FinalProductData).filter(FinalProductData.sku_id.in_(selected_asins)).all()
    fpd_map = {f.sku_id: f for f in fpd_rows}

    groq_count = 0
    fallback_count = 0
    failed_count = 0

    for a in selected_asins:
        rec = fpd_map.get(a)
        if not rec:
            failed_count += 1
        else:
            kws = rec.all_keywords or []
            if isinstance(kws, str):
                import json
                try:
                    kws = json.loads(kws)
                except Exception:
                    kws = []
            expected_fb = fallback_generate_title(rec.product_name, kws)
            if rec.final_product_title == expected_fb:
                fallback_count += 1
            else:
                groq_count += 1

    print(f"\n3. TITLE GENERATION SOURCE AUDIT:")
    print(f"   - Successfully Groq-Generated Titles : {groq_count}")
    print(f"   - Fallback-Generated Titles           : {fallback_count}")
    print(f"   - Failed / Missing Records            : {failed_count}")
    print(f"   - Total Stored in final_product_data  : {len(fpd_rows)}/100")

    # 4. Current-batch tracking inspection
    current_batch_in_exporter = get_current_batch_asins(db)
    matches_selected_batch = (current_batch_in_exporter == selected_asins)
    overlap_count = len(set(current_batch_in_exporter).intersection(set(selected_asins)))

    print(f"\n4. CURRENT-BATCH TRACKING INSPECTION:")
    print(f"   - Currently Tracked Batch ASINs Count : {len(current_batch_in_exporter)}")
    print(f"   - Matches Batch 101-200 Exactly        : {matches_selected_batch}")
    print(f"   - Overlap with Batch 101-200           : {overlap_count}/100")
    if not matches_selected_batch:
        print(f"   - Note: Exporter default tracking is currently holding batch {current_batch_in_exporter[:1]}... to {current_batch_in_exporter[-1:]} (Batch 1-100).")

    # 5. Excel Export Audit for Batch 101-200
    export_filepath = export_final_product_data_to_excel(db, asins_list=selected_asins, output_filepath=os.path.join("scratch", "Audit_Batch_101_200.xlsx"))
    
    wb = openpyxl.load_workbook(export_filepath)
    sheet = wb.active
    total_excel_rows = sheet.max_row
    total_excel_cols = sheet.max_column
    headers = [sheet.cell(row=1, column=c).value for c in range(1, total_excel_cols + 1)]

    exported_skus = [sheet.cell(row=r, column=2).value for r in range(2, total_excel_rows + 1) if sheet.cell(row=r, column=2).value]

    # Compare exported SKUs against selected batch
    selected_set = set(selected_asins)
    exported_set = set(exported_skus)

    missing_skus = list(selected_set - exported_set)
    extra_skus = list(exported_set - selected_set)
    
    import collections
    sku_counts = collections.Counter(exported_skus)
    duplicate_skus = [sku for sku, cnt in sku_counts.items() if cnt > 1]

    print(f"\n5. EXCEL EXPORT AUDIT (Batch 101-200):")
    print(f"   - Export File Path                    : {export_filepath}")
    print(f"   - Total Rows in File                  : {total_excel_rows} (Header + {total_excel_rows - 1} data rows)")
    print(f"   - Total Columns                       : {total_excel_cols}")
    print(f"   - Column Headers                      : {headers}")
    print(f"   - Header Match Exactly                : {headers == ['product_name', 'sku_id', 'final_product_title', 'all_keywords']}")
    print(f"   - Missing SKUs                        : {len(missing_skus)}")
    print(f"   - Extra SKUs                          : {len(extra_skus)}")
    print(f"   - Duplicate SKUs                      : {len(duplicate_skus)}")

    db.close()
    print("\n==========================================================================")
    print("READ-ONLY AUDIT FOR PRODUCTS 101-200 COMPLETE")
    print("==========================================================================")

if __name__ == "__main__":
    audit_products_101_to_200()
