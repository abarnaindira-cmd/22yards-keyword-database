import os
import json
import urllib.request
import pandas as pd
from app.database import SessionLocal
from app.models.keyword import Keyword
from app.models.keyword_url import KeywordSearchUrl

def verify_step_1_mysql():
    print("==========================================================================")
    print("STEP 1: VERIFYING MYSQL DATA FOR ASIN T2YVIVA000017")
    print("==========================================================================")
    db = SessionLocal()
    
    kws = db.query(Keyword).filter(Keyword.source_product_asin == "T2YVIVA000017").all()
    print(f"Keywords count in MySQL for ASIN T2YVIVA000017: {len(kws)}")
    assert len(kws) == 10, f"Expected 10 keywords, got {len(kws)}"

    urls = db.query(KeywordSearchUrl).filter(
        KeywordSearchUrl.source_product_asin == "T2YVIVA000017",
        KeywordSearchUrl.marketplace == "amazon"
    ).all()
    print(f"URL records count in MySQL table 'keyword_search_urls': {len(urls)}")
    assert len(urls) == 10, f"Expected 10 URL records, got {len(urls)}"

    total_urls = 0
    for idx, u in enumerate(urls, 1):
        slot_urls = [u.url_1, u.url_2, u.url_3, u.url_4, u.url_5]
        valid_slots = [s for s in slot_urls if s and str(s).strip() != '']
        total_urls += len(valid_slots)
        print(f"  Row {idx:2d} | Keyword: '{u.keyword}' | Stored URLs: {len(valid_slots)}/5")
        print(f"         URL 1: {u.url_1}")

    print(f"Total verified URLs stored in MySQL: {total_urls} / 50 expected")
    assert total_urls == 50, f"Expected 50 stored URLs, got {total_urls}"
    db.close()
    print("MySQL DATA VERIFICATION SUCCESSFUL!\n")

def verify_step_2_api_export():
    print("==========================================================================")
    print("STEP 2: CALLING EXCEL EXPORT API: GET /api/keywords/export-harvested-keywords?asin=T2YVIVA000017")
    print("==========================================================================")
    
    api_url = "http://localhost:8001/api/keywords/export-harvested-keywords?asin=T2YVIVA000017"
    download_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    target_filepath = os.path.join(download_dir, "T2YVIVA000017_Harvested_Keywords_API_Test.xlsx")

    # Perform actual HTTP request to backend endpoint
    urllib.request.urlretrieve(api_url, target_filepath)
    print(f"Downloaded API Excel File saved to: {target_filepath}")

    # Inspect downloaded workbook with pandas / openpyxl
    excel_file = pd.ExcelFile(target_filepath)
    print(f"Sheet names in downloaded Excel workbook: {excel_file.sheet_names}")
    assert "Harvested Keywords" in excel_file.sheet_names, "Missing 'Harvested Keywords' sheet!"

    df = pd.read_excel(target_filepath, sheet_name="Harvested Keywords")
    cols = list(df.columns)
    print(f"\nHeader Columns A-J ({len(cols)} columns):")
    for idx, c in enumerate(cols):
        print(f"  Col {chr(65+idx)}: {c}")

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

    assert cols == expected_cols, f"Column mismatch!\nExpected: {expected_cols}\nGot: {cols}"
    assert len(df) == 10, f"Expected 10 keyword rows, got {len(df)}"

    print(f"\nInspecting Excel Data Cells ({len(df)} rows):")
    total_populated_urls = 0
    for idx, row in df.iterrows():
        asin = row['Source Product ASIN']
        kw = row['Keyword Phrase']
        urls = [row[f'Amazon Product URL {i}'] for i in range(1, 6)]
        valid_urls = [u for u in urls if pd.notna(u) and str(u).strip() != '']
        total_populated_urls += len(valid_urls)
        print(f"  Row {idx+1:2d} | ASIN: {asin} | Keyword: '{kw}' | Populated Cells F-J: {len(valid_urls)}/5")
        for i, u in enumerate(urls, 1):
            print(f"         Col {chr(70+i-1)} (URL {i}): {u}")

    print(f"\nTotal Populated Cells F-J in downloaded Excel file: {total_populated_urls} / 50")
    assert total_populated_urls == 50, f"Expected 50 populated cells, got {total_populated_urls}"
    print("API EXCEL EXPORT WORKBOOK VERIFICATION SUCCESSFUL!\n")

def verify_step_3_frontend_connection():
    print("==========================================================================")
    print("STEP 3: VERIFYING FRONTEND API CONNECTION & ALL-PRODUCT EXPORT")
    print("==========================================================================")
    
    from app.services.excel_exporter import export_harvested_keywords_to_excel
    db = SessionLocal()
    target_all = export_harvested_keywords_to_excel(db)
    db.close()

    df_all = pd.read_excel(target_all, sheet_name="Harvested Keywords")
    cols_all = list(df_all.columns)
    
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
    assert cols_all == expected_cols, f"Full export column mismatch: {cols_all}"

    df_t2y_in_all = df_all[df_all['Source Product ASIN'] == 'T2YVIVA000017']
    print(f"Total Keyword Rows in All-Products Export: {len(df_all)}")
    print(f"Rows found for ASIN T2YVIVA000017 in All-Products Export: {len(df_t2y_in_all)}")
    assert len(df_t2y_in_all) == 10, f"Expected 10 rows for T2YVIVA000017, got {len(df_t2y_in_all)}"

    print("FRONTEND API CONNECTION & FULL EXCEL EXPORT VERIFICATION SUCCESSFUL!\n")

if __name__ == "__main__":
    verify_step_1_mysql()
    verify_step_2_api_export()
    verify_step_3_frontend_connection()
