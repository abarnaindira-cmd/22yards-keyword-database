import openpyxl
import io
from fastapi.testclient import TestClient
from app.main import app
from app.database import SessionLocal
from sqlalchemy import text

client = TestClient(app)

print("=== 1. TESTING GET /api/keywords?asin=T2YVIVA000017 ===")
resp = client.get("/api/keywords?asin=T2YVIVA000017")
print(f"Status: {resp.status_code}")
keywords_data = resp.json()
print(f"Keywords count: {len(keywords_data)}")
if keywords_data:
    first_kw = keywords_data[0]
    print(f"Sample keyword record from GET /api/keywords:")
    print(f"  keyword: {first_kw.get('keyword')}")
    print(f"  url_1: {first_kw.get('url_1')}")
    print(f"  url_2: {first_kw.get('url_2')}")
    print(f"  url_3: {first_kw.get('url_3')}")
    print(f"  url_4: {first_kw.get('url_4')}")
    print(f"  url_5: {first_kw.get('url_5')}")

print("\n=== 2. TESTING GET /api/keywords/export-harvested-keywords?asin=T2YVIVA000017&format=excel ===")
resp = client.get("/api/keywords/export-harvested-keywords?asin=T2YVIVA000017&format=excel")
print(f"Status: {resp.status_code}, Content-Type: {resp.headers.get('content-type')}")
wb = openpyxl.load_workbook(io.BytesIO(resp.content))
print(f"Sheet names: {wb.sheetnames}")
sheet = wb["Harvested Keywords"]
headers = [sheet.cell(row=1, column=col).value for col in range(1, 11)]
print(f"Headers: {headers}")

for row in range(2, 12):
    row_vals = [sheet.cell(row=row, column=col).value for col in range(1, 11)]
    print(f"Row {row}: ASIN={row_vals[0]}, Keyword={row_vals[2]}, URL1={row_vals[5]}, URL2={row_vals[6]}")

print("\n=== 3. TESTING GET /api/keywords/export-harvested-keywords?format=excel (ALL PRODUCTS) ===")
resp_all = client.get("/api/keywords/export-harvested-keywords?format=excel")
wb_all = openpyxl.load_workbook(io.BytesIO(resp_all.content))
sheet_all = wb_all["Harvested Keywords"]

print(f"Total rows in All Products export: {sheet_all.max_row}")
print("Checking first 30 rows in All Products export:")
for row in range(2, 31):
    row_vals = [sheet_all.cell(row=row, column=col).value for col in range(1, 11)]
    print(f"Row {row:2d}: ASIN={row_vals[0]:15s} | Kw={row_vals[2]:30s} | URL1={row_vals[5]}")

print("\n=== 4. CHECKING PRODUCTS IN PRODUCTS TABLE (First 10 vs 100 target) ===")
db = SessionLocal()
prods = db.execute(text("SELECT id, asin, product_name FROM products ORDER BY id ASC LIMIT 20")).fetchall()
for p in prods:
    print(f"ID={p.id}: ASIN={p.asin}, Name={p.product_name}")
db.close()
