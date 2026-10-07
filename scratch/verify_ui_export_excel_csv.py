import os
import urllib.request
import pandas as pd
from app.database import SessionLocal
from app.models.product import Product

def test_excel_and_csv_exports():
    from app.services.excel_exporter import export_harvested_keywords_to_excel
    db = SessionLocal()

    print("==========================================================================")
    print("TESTING EXCEL & CSV EXPORT FOR SELECTED PRODUCT RANGE (100 PRODUCTS)")
    print("==========================================================================")

    # 1. Single ASIN Excel Test
    asin_test = "T2YVIVA000017"
    excel_path_asin = export_harvested_keywords_to_excel(db, source_product_asin=asin_test, file_format="excel")

    df_excel_asin = pd.read_excel(excel_path_asin, sheet_name="Harvested Keywords")
    cols_excel = list(df_excel_asin.columns)

    expected_cols = [
        'Source Product ASIN',
        'Source Product Name',
        'Keyword Phrase',
        'Source',
        'Relevance Score',
        'Amazon Product URL 1',
        'Amazon Product URL 2',
        'Amazon Product URL 3',
        'Amazon Product URL 4',
        'Amazon Product URL 5'
    ]

    print(f"\n1. Single ASIN Excel Export ({asin_test}):")
    print(f"   Header Columns A-J: {cols_excel}")
    assert cols_excel == expected_cols, f"Excel columns mismatch: {cols_excel}"
    assert len(df_excel_asin) == 10, f"Expected 10 rows, got {len(df_excel_asin)}"
    
    urls_excel_asin = 0
    for i in range(1, 6):
        urls_excel_asin += df_excel_asin[f"Amazon Product URL {i}"].apply(lambda x: pd.notna(x) and str(x).strip() != '').sum()
    print(f"   Populated URL Slots F-J: {urls_excel_asin}/50")
    assert urls_excel_asin == 50, f"Expected 50 URLs, got {urls_excel_asin}"

    # 2. Single ASIN CSV Test
    csv_path_asin = export_harvested_keywords_to_excel(db, source_product_asin=asin_test, file_format="csv")

    df_csv_asin = pd.read_csv(csv_path_asin)
    cols_csv = list(df_csv_asin.columns)

    print(f"\n2. Single ASIN CSV Export ({asin_test}):")
    print(f"   Header Columns A-J: {cols_csv}")
    assert cols_csv == expected_cols, f"CSV columns mismatch: {cols_csv}"
    assert len(df_csv_asin) == 10, f"Expected 10 rows, got {len(df_csv_asin)}"

    urls_csv_asin = 0
    for i in range(1, 6):
        urls_csv_asin += df_csv_asin[f"Amazon Product URL {i}"].apply(lambda x: pd.notna(x) and str(x).strip() != '').sum()
    print(f"   Populated URL Slots F-J: {urls_csv_asin}/50")
    assert urls_csv_asin == 50, f"Expected 50 URLs, got {urls_csv_asin}"

    # 3. All 100 Products Excel Export Test
    excel_path_all = export_harvested_keywords_to_excel(db, file_format="excel")

    df_excel_all = pd.read_excel(excel_path_all, sheet_name="Harvested Keywords")
    print(f"\n3. All 100 Products Excel Export:")
    print(f"   Total Keyword Rows: {len(df_excel_all)}")
    urls_excel_all = 0
    for i in range(1, 6):
        urls_excel_all += df_excel_all[f"Amazon Product URL {i}"].apply(lambda x: pd.notna(x) and str(x).strip() != '').sum()
    print(f"   Total Populated URL Slots F-J: {urls_excel_all} / 5740")
    assert urls_excel_all == 5740, f"Expected 5740 URLs, got {urls_excel_all}"

    # 4. All 100 Products CSV Export Test
    csv_path_all = export_harvested_keywords_to_excel(db, file_format="csv")

    df_csv_all = pd.read_csv(csv_path_all)
    print(f"\n4. All 100 Products CSV Export:")
    print(f"   Total Keyword Rows: {len(df_csv_all)}")
    urls_csv_all = 0
    for i in range(1, 6):
        urls_csv_all += df_csv_all[f"Amazon Product URL {i}"].apply(lambda x: pd.notna(x) and str(x).strip() != '').sum()
    print(f"   Total Populated URL Slots F-J: {urls_csv_all} / 5740")
    assert urls_csv_all == 5740, f"Expected 5740 URLs, got {urls_csv_all}"

    db.close()
    print("\nALL EXCEL AND CSV EXPORT VERIFICATIONS PASSED SUCCESSFULLY!")

if __name__ == "__main__":
    test_excel_and_csv_exports()
