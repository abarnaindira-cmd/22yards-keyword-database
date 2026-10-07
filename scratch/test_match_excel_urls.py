import io
import json
import urllib.request
import pandas as pd

# Create in-memory Excel file with ASIN T2YVIVA000017
df = pd.DataFrame([{
    "ASIN": "T2YVIVA000017",
    "Product Name": "Speedo Unisex Adult Swimming Cap"
}, {
    "ASIN": "B000112233",
    "Product Name": "Test Product Without Stored URLs"
}])

excel_buffer = io.BytesIO()
with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
    df.to_excel(writer, index=False, sheet_name='Products')
excel_bytes = excel_buffer.getvalue()

# Send multipart/form-data POST request to http://127.0.0.1:8001/api/products/match-excel
boundary = "----WebKitFormBoundary7MA4YWxkTrZu0gW"
body = bytearray()
body.extend(f"--{boundary}\r\n".encode())
body.extend(b'Content-Disposition: form-data; name="file"; filename="test_products.xlsx"\r\n')
body.extend(b'Content-Type: application/vnd.openxmlformats-officedocument.spreadsheetml.sheet\r\n\r\n')
body.extend(excel_bytes)
body.extend(f"\r\n--{boundary}--\r\n".encode())

req = urllib.request.Request(
    "http://127.0.0.1:8001/api/products/match-excel",
    data=bytes(body),
    headers={"Content-Type": f"multipart/form-data; boundary={boundary}"}
)

with urllib.request.urlopen(req) as resp:
    res = json.loads(resp.read().decode())

print("==========================================================================")
print("MATCH EXCEL API TEST RESULT:")
print("==========================================================================")
print(f"Matched products: {len(res.get('matched_products', []))}")

for p in res.get('matched_products', []):
    asin = p.get('asin')
    keywords = p.get('keywords', [])
    print(f"\nASIN: {asin} | Keywords Count: {len(keywords)}")
    url_count = 0
    for idx, kw in enumerate(keywords, 1):
        urls = [kw.get(f'url_{i}') for i in range(1, 6)]
        valid_urls = [u for u in urls if u]
        url_count += len(valid_urls)
        if valid_urls:
            print(f"  Row {idx:2d} | '{kw['keyword']}' -> {len(valid_urls)} URLs: {valid_urls[0]} ...")
        else:
            print(f"  Row {idx:2d} | '{kw['keyword']}' -> 0 URLs (Blank cells F-J)")
    print(f"Total Stored URLs returned for ASIN {asin}: {url_count}")
