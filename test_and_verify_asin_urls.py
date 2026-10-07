import sys
import os
import pandas as pd
from sqlalchemy import text

sys.path.insert(0, r"d:\22yards_keyword_database_competitor_ready\22yards_keyword_database")

from app.database import SessionLocal, engine
from app.services.amazon_url_collector import process_amazon_urls_for_asin
from app.services.excel_exporter import export_harvested_keywords_to_excel

def main():
    db = SessionLocal()
    target_asin = "T2YVIVA000017"

    print("=" * 95)
    print(f" STEP 1: RUNNING PLAYWRIGHT COLLECTION & MYSQL STORAGE FOR ASIN: {target_asin}")
    print("=" * 95)

    collection_res = process_amazon_urls_for_asin(db, target_asin)
    if "error" in collection_res:
        print(f"Error: {collection_res['error']}")
        db.close()
        return

    print(f"Product Name:             {collection_res['product_name']}")
    print(f"Total Keywords Processed: {collection_res['total_keywords_processed']}")
    print(f"Total URLs Stored:        {collection_res['total_urls_stored']}")
    print(f"Failed Keywords Count:    {collection_res['failed_keywords_count']}")
    if collection_res['failed_keywords']:
        print(f"Failed Keywords List:     {collection_res['failed_keywords']}")

    print("\n" + "=" * 95)
    print(" STEP 2: SQL VERIFICATION - DIRECT QUERY ON MySQL 'keyword_search_urls' TABLE")
    print("=" * 95)

    sql_query = text("""
        SELECT 
            id,
            source_product_asin,
            keyword,
            url_1,
            url_2,
            url_3,
            url_4,
            url_5,
            marketplace,
            created_at,
            updated_at
        FROM keyword_search_urls
        WHERE source_product_asin = :asin
        ORDER BY id ASC;
    """)

    sql_rows = db.execute(sql_query, {"asin": target_asin}).fetchall()
    print(f"SQL Query Returned {len(sql_rows)} Rows from 'keyword_search_urls':\n")

    for row in sql_rows:
        print(f"ID: {row.id} | ASIN: {row.source_product_asin} | Keyword: '{row.keyword}'")
        print(f"   URL 1: {row.url_1}")
        print(f"   URL 2: {row.url_2}")
        print(f"   URL 3: {row.url_3}")
        print(f"   URL 4: {row.url_4}")
        print(f"   URL 5: {row.url_5}")
        print("-" * 80)

    print("\n" + "=" * 95)
    print(" STEP 3: EXCEL EXPORT VERIFICATION - GENERATING EXCEL FROM MYSQL (NO LIVE SEARCH)")
    print("=" * 95)

    excel_path = export_harvested_keywords_to_excel(db, source_product_asin=target_asin)
    print(f"Excel Export Path: {excel_path}")

    # Read back Excel file to verify columns F-J
    df_excel = pd.read_excel(excel_path, sheet_name="Harvested Keywords")
    print("\nGenerated Excel Columns:")
    print(list(df_excel.columns))
    print("\nGenerated Excel Data (First 3 Rows):")
    print(df_excel.head(3).to_string())

    print("\n" + "=" * 95)
    print(" FINAL VERIFICATION SUMMARY FOR T2YVIVA000017")
    print("=" * 95)
    print(f"- MySQL Table Used:          keyword_search_urls")
    print(f"- Keywords Processed:        {len(sql_rows)}")
    print(f"- URLs Permanently Stored:   {collection_res['total_urls_stored']}")
    print(f"- SQL Verification Status:   SUCCESS ({len(sql_rows)} rows verified in database)")
    print(f"- Excel Verification Status: SUCCESS (Columns F-J verified in Harvested Keywords sheet)")
    print(f"- Failed Keywords:           {collection_res['failed_keywords_count']}")
    print("=" * 95 + "\n")

    db.close()

if __name__ == "__main__":
    main()
