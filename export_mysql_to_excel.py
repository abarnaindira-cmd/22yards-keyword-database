import os
import sys
import pandas as pd

sys.path.insert(0, r'd:\22yards_keyword_database')

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

def export_to_excel():
    export_filepath = r"D:\22yards_keyword_database\marketlens_export.xlsx"

    print("=" * 80)
    print("STARTING READ-ONLY MYSQL TO EXCEL EXPORT UPDATE")
    print(f"Database Target : {DB_NAME}")
    print(f"Export Filepath : {export_filepath}")
    print("=" * 80 + "\n")

    # Read data from MySQL using pandas read_sql
    products_df = pd.read_sql("SELECT * FROM products;", con=engine)
    keywords_df = pd.read_sql("SELECT * FROM keywords;", con=engine)
    summary_df = pd.read_sql(SUMMARY_QUERY, con=engine)

    # Competitor tables are created only after Phase 2 starts. Export them when present.
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
        # Write dataframes to Excel. Phase 1 sheets remain unchanged; Phase 2 sheets are added when available.
        with pd.ExcelWriter(export_filepath, engine="openpyxl") as writer:
            products_df.to_excel(writer, sheet_name="Products", index=False)
            keywords_df.to_excel(writer, sheet_name="Keywords", index=False)
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

    products_count = len(products_df)
    keywords_count = len(keywords_df)
    summary_count = len(summary_df)

    print("=" * 80)
    print("EXCEL WORKBOOK UPDATED SUCCESSFULLY")
    print("=" * 80)
    print(f"Sheet 'Products' Exported         : {products_count} rows")
    print(f"Sheet 'Keywords' Exported         : {keywords_count} rows")
    print(f"Sheet 'Product Keyword Summary'   : {summary_count} total products")
    for sheet_name, df in optional_dfs.items():
        print(f"Sheet '{sheet_name}' Exported      : {len(df)} rows")
    print(f"Final Excel File Path             : {export_filepath}")
    print("=" * 80)

if __name__ == "__main__":
    export_to_excel()
