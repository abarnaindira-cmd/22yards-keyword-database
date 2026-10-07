import pandas as pd
from sqlalchemy import text
from app.database import SessionLocal
from app.services.excel_exporter import export_harvested_keywords_to_excel

def verify_updates():
    db = SessionLocal()

    # 1. Fetch products 1 to 100 (IDs 4 to 103)
    prods = db.execute(text("SELECT id, asin, product_name FROM products ORDER BY id ASC LIMIT 100;")).fetchall()
    first_100_asins = [p.asin for p in prods if p.asin]

    url_rows = db.execute(text("""
        SELECT source_product_asin, keyword, url_1, url_2, url_3, url_4, url_5 
        FROM keyword_search_urls 
        WHERE source_product_asin IN :asins AND LOWER(marketplace) = 'amazon';
    """), {"asins": tuple(first_100_asins)}).fetchall()

    db.close()

    total_records = len(url_rows)
    completed_5 = 0
    partial_1_to_4 = 0
    zero_urls = 0
    total_populated_slots = 0

    for r in url_rows:
        valid_urls = [u for u in [r.url_1, r.url_2, r.url_3, r.url_4, r.url_5] if u and str(u).strip() != '']
        cnt = len(valid_urls)
        total_populated_slots += cnt

        if cnt == 5:
            completed_5 += 1
        elif cnt > 0:
            partial_1_to_4 += 1
        else:
            zero_urls += 1

    print("==========================================================================")
    print("DATABASE VERIFICATION SUMMARY FOR FIRST 100 PRODUCTS")
    print("==========================================================================")
    print(f"Total Keyword URL Records Evaluated : {total_records}")
    print(f"Keywords with 5/5 Displayed URLs    : {completed_5} / {total_records} ({(completed_5/total_records)*100:.1f}%)")
    print(f"Keywords with 1-4 Displayed URLs    : {partial_1_to_4}")
    print(f"Keywords with 0 URLs (Failed)       : {zero_urls}")
    print(f"Total Populated URL Slots (F-J)     : {total_populated_slots}")
    print("==========================================================================")

    # Verify Excel export file download
    print("\nVerifying Excel Export Generation...")
    export_path = export_harvested_keywords_to_excel(SessionLocal())
    df = pd.read_excel(export_path, sheet_name="Harvested Keywords")
    print(f"Export Filepath   : {export_path}")
    print(f"Export Rows Count : {len(df)}")
    print(f"Columns           : {list(df.columns)}")
    print("==========================================================================")

if __name__ == "__main__":
    verify_updates()
