import os
import pandas as pd
from app.database import SessionLocal
from app.services.excel_exporter import export_harvested_keywords_to_excel

def run_export_verification():
    db = SessionLocal()

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

    print("==========================================================================")
    print("VERIFYING EXCEL & CSV EXPORT FUNCTIONS AND POPULATED URL CELLS")
    print("==========================================================================")

    # 1. Single ASIN Test: T2YVIVA000017
    asin_test = "T2YVIVA000017"
    excel_path_t2y = export_harvested_keywords_to_excel(db, source_product_asin=asin_test, file_format="excel")
    csv_path_t2y = export_harvested_keywords_to_excel(db, source_product_asin=asin_test, file_format="csv")

    # Inspect Excel
    df_excel_t2y = pd.read_excel(excel_path_t2y, sheet_name="Harvested Keywords")
    cols_excel_t2y = list(df_excel_t2y.columns)
    print(f"\n1a. Single ASIN Excel Export ({asin_test}):")
    print(f"    Filepath: {excel_path_t2y}")
    print(f"    Columns : {cols_excel_t2y}")
    assert cols_excel_t2y == expected_cols, f"Mismatch: {cols_excel_t2y}"
    assert len(df_excel_t2y) == 10, f"Expected 10 rows, got {len(df_excel_t2y)}"

    url_count_excel_t2y = 0
    for i in range(1, 6):
        col = f"Amazon Product URL {i}"
        non_empty = df_excel_t2y[col].apply(lambda x: pd.notna(x) and str(x).strip() != '')
        url_count_excel_t2y += non_empty.sum()
    print(f"    Populated URL Cells (Cols F-J): {url_count_excel_t2y} / 50")
    assert url_count_excel_t2y == 50, f"Expected 50 populated URLs, got {url_count_excel_t2y}"

    # Inspect CSV
    df_csv_t2y = pd.read_csv(csv_path_t2y)
    cols_csv_t2y = list(df_csv_t2y.columns)
    print(f"\n1b. Single ASIN CSV Export ({asin_test}):")
    print(f"    Filepath: {csv_path_t2y}")
    print(f"    Columns : {cols_csv_t2y}")
    assert cols_csv_t2y == expected_cols, f"Mismatch: {cols_csv_t2y}"
    assert len(df_csv_t2y) == 10, f"Expected 10 rows, got {len(df_csv_t2y)}"

    url_count_csv_t2y = 0
    for i in range(1, 6):
        col = f"Amazon Product URL {i}"
        non_empty = df_csv_t2y[col].apply(lambda x: pd.notna(x) and str(x).strip() != '')
        url_count_csv_t2y += non_empty.sum()
    print(f"    Populated URL Cells (Cols F-J): {url_count_csv_t2y} / 50")
    assert url_count_csv_t2y == 50, f"Expected 50 populated URLs, got {url_count_csv_t2y}"

    # Print actual sample URLs from exported file
    print(f"\n    Sample Exported URLs for row 1 ('{df_csv_t2y.iloc[0]['Keyword Phrase']}'):")
    for i in range(1, 6):
        print(f"      Col {chr(70+i-1)} (URL {i}): {df_csv_t2y.iloc[0][f'Amazon Product URL {i}']}")

    # 2. All 100 Products Export Test
    excel_path_all = export_harvested_keywords_to_excel(db, file_format="excel")
    csv_path_all = export_harvested_keywords_to_excel(db, file_format="csv")

    df_excel_all = pd.read_excel(excel_path_all, sheet_name="Harvested Keywords")
    df_csv_all = pd.read_csv(csv_path_all)

    print(f"\n2a. All Products Excel Export:")
    print(f"    Total Rows in Export: {len(df_excel_all)}")
    excel_urls_all = 0
    for i in range(1, 6):
        col = f"Amazon Product URL {i}"
        excel_urls_all += df_excel_all[col].apply(lambda x: pd.notna(x) and str(x).strip() != '').sum()
    print(f"    Total Populated URL Cells (Cols F-J): {excel_urls_all}")
    assert excel_urls_all == 5740, f"Expected 5740 URLs, got {excel_urls_all}"

    print(f"\n2b. All Products CSV Export:")
    print(f"    Total Rows in Export: {len(df_csv_all)}")
    csv_urls_all = 0
    for i in range(1, 6):
        col = f"Amazon Product URL {i}"
        csv_urls_all += df_csv_all[col].apply(lambda x: pd.notna(x) and str(x).strip() != '').sum()
    print(f"    Total Populated URL Cells (Cols F-J): {csv_urls_all}")
    assert csv_urls_all == 5740, f"Expected 5740 URLs, got {csv_urls_all}"

    db.close()
    print("\n==========================================================================")
    print("ALL EXCEL AND CSV DOWNLOAD VERIFICATIONS PASSED 100% SUCCESSFULLY!")
    print("==========================================================================")

if __name__ == "__main__":
    run_export_verification()
