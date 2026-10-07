import os
import sys
import pandas as pd
from sqlalchemy import text

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.database import engine, DB_NAME

SUMMARY_QUERY = """
SELECT 
    p.id,
    p.asin,
    p.product_name,
    p.category,
    COUNT(k.id) AS keyword_count
FROM products p
LEFT JOIN keywords k 
    ON p.asin = k.source_product_asin
GROUP BY p.id, p.asin, p.product_name, p.category
ORDER BY keyword_count DESC;
"""

HARVESTED_KEYWORDS_QUERY = """
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
ORDER BY k.source_product_asin ASC, k.id ASC;
"""

def export_to_excel():
    current_dir = os.path.dirname(os.path.abspath(__file__))
    export_filepath = os.path.join(current_dir, "marketlens_export.xlsx")

    print("=" * 80)
    print("STARTING READ-ONLY MYSQL TO EXCEL EXPORT UPDATE")
    print(f"Database Target : {DB_NAME}")
    print(f"Export Filepath : {export_filepath}")
    print("=" * 80 + "\n")

    # Read data from MySQL using pandas read_sql
    products_df = pd.read_sql("SELECT * FROM products;", con=engine)
    harvested_keywords_df = pd.read_sql(text(HARVESTED_KEYWORDS_QUERY), con=engine)
    summary_df = pd.read_sql(SUMMARY_QUERY, con=engine)

    optional_tables = {
        "Keyword Rankings": "keyword_rankings",
        "Competitor Products": "competitor_products",
        "Competitor Keywords": "competitor_keywords",
    }
    optional_dfs = {}
    with engine.connect() as conn:
        for sheet_name, table_name in optional_tables.items():
            exists = conn.exec_driver_sql(
                "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema=%s AND table_name=%s",
                (DB_NAME, table_name),
            ).scalar()
            if exists:
                optional_dfs[sheet_name] = pd.read_sql(f"SELECT * FROM {table_name};", con=engine)

    try:
        with pd.ExcelWriter(export_filepath, engine="openpyxl") as writer:
            products_df.to_excel(writer, sheet_name="Products", index=False)
            harvested_keywords_df.to_excel(writer, sheet_name="Harvested Keywords", index=False)
            summary_df.to_excel(writer, sheet_name="Product Keyword Summary", index=False)
            for sheet_name, df in optional_dfs.items():
                df.to_excel(writer, sheet_name=sheet_name, index=False)
    except PermissionError:
        print("=" * 80)
        print("[PERMISSION ERROR] Unable to write to Excel file.")
        print(f"The file '{export_filepath}' is currently open in Microsoft Excel.")
        print("Please CLOSE the Excel file and rerun the script.")
        print("=" * 80)
        sys.exit(1)

    print("=" * 80)
    print("EXCEL WORKBOOK UPDATED SUCCESSFULLY")
    print("=" * 80)
    print(f"Sheet 'Products' Exported           : {len(products_df)} rows")
    print(f"Sheet 'Harvested Keywords' Exported : {len(harvested_keywords_df)} rows")
    print(f"Sheet 'Product Keyword Summary'     : {len(summary_df)} total products")
    for sheet_name, df in optional_dfs.items():
        print(f"Sheet '{sheet_name}' Exported        : {len(df)} rows")
    print(f"Final Excel File Path               : {export_filepath}")
    print("=" * 80)

if __name__ == "__main__":
    export_to_excel()
