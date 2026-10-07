import pandas as pd
from app.database import SessionLocal
from app.services.excel_exporter import export_harvested_keywords_to_excel

db = SessionLocal()
filepath = export_harvested_keywords_to_excel(db)
db.close()

df = pd.read_excel(filepath, sheet_name="Harvested Keywords")
cols = list(df.columns)

print("==========================================================================")
print("EXCEL REPORT VERIFICATION FOR 100 PRODUCTS")
print("==========================================================================")
print(f"Export Filepath   : {filepath}")
print(f"Total Rows        : {len(df)}")
print(f"Header Columns A-J: {cols}")

url_cols = [
    "Amazon Product URL 1",
    "Amazon Product URL 2",
    "Amazon Product URL 3",
    "Amazon Product URL 4",
    "Amazon Product URL 5"
]

total_populated_cells = 0
for col in url_cols:
    non_empty = df[col].apply(lambda x: pd.notna(x) and str(x).strip() != '')
    count = non_empty.sum()
    total_populated_cells += count
    print(f"  {col}: {count} populated cells")

print(f"\nTotal Populated URL Cells (Cols F-J) across all rows: {total_populated_cells}")
print("==========================================================================")
