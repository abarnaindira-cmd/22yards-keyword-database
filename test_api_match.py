import urllib.request
import json
import openpyxl, io

wb = openpyxl.Workbook()
ws = wb.active
ws.append(['ASIN', 'Product Name'])
ws.append(['T2YTYKA000003', 'TYKA PRIMA HALF SLEEVES MEN WHITE JERSEY'])
ws.append(['T2YTYKA000004', 'TYKA PRIMA HALF SLEEVES MEN WHITE JERSEY'])
ws.append(['T2YTYKA000006', 'TYKA PRIMA HALF SLEEVES MEN WHITE JERSEY'])

file_stream = io.BytesIO()
wb.save(file_stream)
file_stream.seek(0)

boundary = '----WebKitFormBoundary7MA4YWxkTrZu0gW'
body = (
    b'--' + boundary.encode() + b'\r\n'
    b'Content-Disposition: form-data; name="file"; filename="test.xlsx"\r\n'
    b'Content-Type: application/vnd.openxmlformats-officedocument.spreadsheetml.sheet\r\n\r\n' +
    file_stream.read() +
    b'\r\n--' + boundary.encode() + b'--\r\n'
)

req = urllib.request.Request(
    'http://localhost:8001/api/products/match-excel',
    data=body,
    headers={'Content-Type': f'multipart/form-data; boundary={boundary}'}
)

res = urllib.request.urlopen(req)
data = json.loads(res.read().decode())

print("Matched Products Count:", data.get("matched_count"))
for p in data.get("matched_products", []):
    print("----------------------------------------")
    print(f"Product ID: {p.get('id')} | ASIN: {p.get('asin')} | Excel ASIN: {p.get('excel_asin')}")
    print(f"Product Name: {p.get('product_name')}")
    print(f"Keyword Count: {p.get('keyword_count')}")
    print(f"Competitor Count: {p.get('competitor_count')}")
    print(f"Len Competitor Products: {len(p.get('competitor_products', []))}")
