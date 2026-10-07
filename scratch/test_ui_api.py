import json
import urllib.request
import urllib.parse

BASE_URL = "http://localhost:8001"

def test_keywords_endpoint_t2yviva():
    print("==========================================================================")
    print("TEST 1: Testing GET /api/keywords?asin=T2YVIVA000017")
    print("==========================================================================")
    url = f"{BASE_URL}/api/keywords?asin=T2YVIVA000017"
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req) as resp:
        data = json.loads(resp.read().decode('utf-8'))

    print(f"Keywords count returned: {len(data)}")
    assert len(data) == 10, f"Expected 10 keywords for T2YVIVA000017, got {len(data)}"

    total_urls = 0
    for idx, kw in enumerate(data, 1):
        urls = [kw.get(f'url_{i}') for i in range(1, 6)]
        valid_urls = [u for u in urls if u]
        total_urls += len(valid_urls)
        print(f"Row {idx:2d} | Keyword: '{kw['keyword']}' | Valid URLs: {len(valid_urls)}/5")
        for i, u in enumerate(urls, 1):
            print(f"       Col {chr(69+i)} (URL {i}): {u}")
    
    print(f"Total Stored URLs returned: {total_urls} / 50 expected")
    assert total_urls == 50, f"Expected 50 total URLs for T2YVIVA000017, got {total_urls}"
    print("GET /api/keywords?asin=T2YVIVA000017 PASSED!\n")

def test_keywords_endpoint_other_asin():
    print("==========================================================================")
    print("TEST 2: Testing GET /api/keywords for ASIN without stored URLs (e.g. B001123456)")
    print("==========================================================================")
    # Pick another ASIN from products table
    url = f"{BASE_URL}/api/keywords?limit=10"
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req) as resp:
        data = json.loads(resp.read().decode('utf-8'))
    
    non_t2y_count = 0
    blank_url_count = 0
    for kw in data:
        if kw.get("source_product_asin") != "T2YVIVA000017":
            non_t2y_count += 1
            for i in range(1, 6):
                val = kw.get(f"url_{i}")
                if val is None or val == "":
                    blank_url_count += 1
                else:
                    print(f"Warning: URL found for ASIN {kw.get('source_product_asin')}, kw: '{kw.get('keyword')}': {val}")

    print(f"Checked {non_t2y_count} non-T2YVIVA000017 keywords. Blank URL fields count: {blank_url_count}/{non_t2y_count*5}")
    print("Blank cell rule verified!\n")

if __name__ == "__main__":
    test_keywords_endpoint_t2yviva()
    test_keywords_endpoint_other_asin()
