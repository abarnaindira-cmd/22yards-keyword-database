import os
import pandas as pd
from app.database import SessionLocal
from app.services.excel_exporter import export_harvested_keywords_to_excel

db = SessionLocal()

# Test 1: Single Product Export for T2YVIVA000017
output_path_t2y = export_harvested_keywords_to_excel(db, source_product_asin="T2YVIVA000017")
print("==========================================================================")
print(f"VERIFYING SINGLE PRODUCT EXCEL EXPORT: {output_path_t2y}")
print("==========================================================================")

df_t2y = pd.read_excel(output_path_t2y, sheet_name="Harvested Keywords")
cols_t2y = list(df_t2y.columns)
print(f"Sheet Name: 'Harvested Keywords'")
print(f"Header Columns A-J ({len(cols_t2y)} columns):")
for idx, col in enumerate(cols_t2y):
    col_letter = chr(65 + idx)
    print(f"  Col {col_letter}: {col}")

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

assert cols_t2y == expected_cols, f"Column titles mismatch!\nExpected: {expected_cols}\nGot: {cols_t2y}"
assert len(df_t2y) == 10, f"Expected 10 rows for T2YVIVA000017, got {len(df_t2y)}"

print(f"\nData Rows Verified ({len(df_t2y)} rows):")
total_urls = 0
for idx, row in df_t2y.iterrows():
    kw = row['Keyword Phrase']
    urls = [row[f'Amazon Product URL {i}'] for i in range(1, 6)]
    valid_urls = [u for u in urls if pd.notna(u) and str(u).strip() != '']
    total_urls += len(valid_urls)
    print(f"Row {idx+1:2d} | Keyword: '{kw}' | Valid URLs: {len(valid_urls)}/5")
    for i, u in enumerate(urls, 1):
        print(f"       Col {chr(70+i-1)} (URL {i}): {u}")

assert total_urls == 50, f"Expected 50 valid URLs for T2YVIVA000017, got {total_urls}"
print("\nSINGLE PRODUCT T2YVIVA000017 EXCEL EXPORT VERIFICATION PASSED!\n")

# Test 2: All Products Export
output_path_all = export_harvested_keywords_to_excel(db)
print("==========================================================================")
print(f"VERIFYING ALL-PRODUCTS EXCEL EXPORT: {output_path_all}")
print("==========================================================================")
df_all = pd.read_excel(output_path_all, sheet_name="Harvested Keywords")
cols_all = list(df_all.columns)
assert cols_all == expected_cols, f"All-products column titles mismatch!\nGot: {cols_all}"

df_t2y_filtered = df_all[df_all['Source Product ASIN'] == 'T2YVIVA000017']
print(f"Rows found for T2YVIVA000017 in full export: {len(df_t2y_filtered)}")
assert len(df_t2y_filtered) == 10, "Expected 10 rows for T2YVIVA000017 in full export"

db.close()
print("ALL EXCEL EXPORT VERIFICATIONS SUCCESSFUL!")
