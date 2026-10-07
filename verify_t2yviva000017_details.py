import sys
import pandas as pd
from sqlalchemy import text

sys.path.insert(0, r"d:\22yards_keyword_database_competitor_ready\22yards_keyword_database")

from app.database import SessionLocal
from app.services.excel_exporter import export_harvested_keywords_to_excel

def main():
    db = SessionLocal()
    target_asin = "T2YVIVA000017"

    print("=" * 100)
    print(f" DETAILED MYSQL VERIFICATION FOR ASIN: {target_asin}")
    print("=" * 100)

    # 1. Query MySQL keyword_search_urls table directly
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
        WHERE source_product_asin = :asin AND marketplace = 'amazon'
        ORDER BY id ASC;
    """)

    rows = db.execute(sql_query, {"asin": target_asin}).fetchall()

    print(f"Total Stored Rows in 'keyword_search_urls' for {target_asin}: {len(rows)}\n")

    kw_url_map = {}

    for idx, row in enumerate(rows, 1):
        urls = [row.url_1, row.url_2, row.url_3, row.url_4, row.url_5]
        asins = [u.split("/dp/")[-1] for u in urls if u and "/dp/" in u]
        kw_url_map[row.keyword] = asins

        print(f"[{idx:2d}/10] Keyword: '{row.keyword}'")
        print(f"       Marketplace: {row.marketplace}")
        print(f"       Extracted ASINs: {asins}")
        print(f"       URL 1: {row.url_1}")
        print(f"       URL 2: {row.url_2}")
        print(f"       URL 3: {row.url_3}")
        print(f"       URL 4: {row.url_4}")
        print(f"       URL 5: {row.url_5}")
        print("-" * 100)

    # 2. Check overlap between keywords
    print("\n" + "=" * 100)
    print(" ANALYSIS OF URL / ASIN OVERLAP BETWEEN KEYWORDS")
    print("=" * 100)
    
    kws = list(kw_url_map.keys())
    for i in range(len(kws)):
        for j in range(i + 1, len(kws)):
            kw1, kw2 = kws[i], kws[j]
            asins1 = kw_url_map[kw1]
            asins2 = kw_url_map[kw2]
            overlap = set(asins1).intersection(set(asins2))
            identical = (asins1 == asins2)
            if identical:
                print(f"[IDENTICAL MATCH] '{kw1}' <===> '{kw2}' ({len(overlap)} matching ASINs: {asins1})")
            elif overlap:
                print(f"[PARTIAL OVERLAP] '{kw1}' vs '{kw2}' -> {len(overlap)} matching ASINs: {list(overlap)}")
            else:
                print(f"[DIFFERENT]       '{kw1}' vs '{kw2}' -> 0 matching ASINs")

    # 3. Verify Excel Export with source_product_asin + keyword + marketplace
    print("\n" + "=" * 100)
    print(" VERIFYING EXCEL EXPORT MATCHING (source_product_asin + keyword + marketplace)")
    print("=" * 100)

    excel_file = export_harvested_keywords_to_excel(db, source_product_asin=target_asin)
    df_excel = pd.read_excel(excel_file, sheet_name="Harvested Keywords")

    print(f"Excel File Exported: {excel_file}")
    print("Excel Sheet Columns:")
    print(list(df_excel.columns))
    print(f"Total Keyword Rows in Excel: {len(df_excel)}")
    
    all_match = True
    for index, excel_row in df_excel.iterrows():
        kw = excel_row["Keyword Phrase"]
        db_row = db.execute(text("""
            SELECT url_1, url_2, url_3, url_4, url_5 
            FROM keyword_search_urls 
            WHERE source_product_asin = :asin AND keyword = :kw AND marketplace = 'amazon'
        """), {"asin": target_asin, "kw": kw}).fetchone()

        if db_row:
            u1_match = (str(excel_row["Amazon Product URL 1"]).strip() == str(db_row.url_1).strip())
            u2_match = (str(excel_row["Amazon Product URL 2"]).strip() == str(db_row.url_2).strip())
            u3_match = (str(excel_row["Amazon Product URL 3"]).strip() == str(db_row.url_3).strip())
            u4_match = (str(excel_row["Amazon Product URL 4"]).strip() == str(db_row.url_4).strip())
            u5_match = (str(excel_row["Amazon Product URL 5"]).strip() == str(db_row.url_5).strip())
            if not (u1_match and u2_match and u3_match and u4_match and u5_match):
                all_match = False
                print(f"Mismatch found for keyword '{kw}'!")

    if all_match:
        print("[SUCCESS] All 10 Excel rows match the exact stored URLs in MySQL!")
    else:
        print("[FAIL] Mismatch detected between Excel and MySQL.")

    print("=" * 100 + "\n")
    db.close()

if __name__ == "__main__":
    main()
