import sys
import re
import html
import urllib.parse
from typing import List, Dict, Any
import httpx
from playwright.sync_api import sync_playwright

sys.path.insert(0, r'd:\22yards_keyword_database')

from app.database import SessionLocal
from app.models.product import Product
from app.services.keyword_collector import clean_product_title_to_seeds, DEFAULT_USER_AGENT

def extract_keyword_candidates_from_titles(titles: List[str], seed: str) -> List[str]:
    """
    Extract meaningful multi-word keyword phrases from Amazon Search Result product titles.
    1. Unescapes HTML entities.
    2. Strips noise tags, brackets, and parenthesized specs.
    3. Splits on clause delimiters (commas, dashes, slashes, pipes).
    4. Filters out noise phrases and deduplicates case-insensitively.
    """
    candidates = []
    
    stop_phrases = {"results", "sponsored", "featured from our brands", "check each product page"}
    
    for raw_title in titles:
        t = html.unescape(raw_title)
        
        # Remove parenthesized specs e.g. (Black/Silver), (Pack of 2)
        t = re.sub(r'\(.*?\)', ' ', t)
        t = re.sub(r'\[.*?\]', ' ', t)
        
        # Split on separators like ',', '|', '-', '/'
        parts = re.split(r'[,|/\-\\]', t)
        
        for p in parts:
            p_clean = re.sub(r'[^\w\s]', ' ', p)
            p_clean = re.sub(r'\s+', ' ', p_clean).strip()
            
            if not p_clean or p_clean.lower() in stop_phrases:
                continue
                
            words = p_clean.split()
            # Multi-word candidate phrases (2 to 5 words)
            if 2 <= len(words) <= 5:
                if not all(w.isdigit() for w in words):
                    if p_clean.lower() not in [c.lower() for c in candidates]:
                        candidates.append(p_clean)
                        
    return candidates

def fetch_amazon_search_results(seed: str, browser=None) -> List[str]:
    """
    Fetch organic search result product titles for a seed query.
    Uses Playwright browser context / HTTP client with updated DOM selectors.
    """
    encoded_seed = urllib.parse.quote_plus(seed)
    url = f"https://www.amazon.in/s?k={encoded_seed}"
    
    headers = {
        "User-Agent": DEFAULT_USER_AGENT,
        "Accept-Language": "en-US,en;q=0.9,en-IN;q=0.8",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    }
    
    # 1. Fast HTTP client try
    try:
        with httpx.Client(timeout=6.0, follow_redirects=True) as client:
            resp = client.get(url, headers=headers)
            if resp.status_code == 200:
                raw_html = resp.text
                if "Robot Check" not in raw_html and "Captcha" not in raw_html:
                    titles = re.findall(r'class="a-size-base-plus[^"]*">(.*?)</span>', raw_html)
                    if not titles:
                        titles = re.findall(r'class="a-size-medium[^"]*">(.*?)</span>', raw_html)
                    if titles:
                        clean_titles = [re.sub(r'<[^>]+>', '', t).strip() for t in titles if t.strip()]
                        return clean_titles
    except Exception:
        pass
        
    # 2. Playwright Browser Fallback (handles anti-bot / 503 reliably)
    if browser:
        context = None
        try:
            context = browser.new_context(
                user_agent=DEFAULT_USER_AGENT,
                locale="en-IN",
                viewport={"width": 1366, "height": 900},
                extra_http_headers={
                    "Accept-Language": "en-US,en;q=0.9,en-IN;q=0.8"
                }
            )
            context.set_default_timeout(15000)
            page = context.new_page()
            
            page.goto(url, wait_until="domcontentloaded")
            page.wait_for_timeout(2500)
            
            # Robust selectors for Amazon search result product titles
            selectors = [
                "div[data-component-type='s-search-result'] h2",
                "span.a-size-base-plus",
                "span.a-size-medium.a-color-base.a-text-normal",
                "h2 span"
            ]
            
            titles = []
            for sel in selectors:
                elems = page.locator(sel).all_inner_texts()
                if elems:
                    cleaned = []
                    for t in elems:
                        t_str = t.strip()
                        if t_str and not t_str.lower().startswith("results") and not t_str.lower().startswith("1-48"):
                            cleaned.append(t_str)
                    if cleaned:
                        titles = cleaned
                        break
                    
            return titles
        except Exception as e:
            print(f"    [Playwright Error] Browser fetch failed for '{seed}': {e}")
            return []
        finally:
            if context:
                context.close()
                
    return []

def main():
    db = SessionLocal()
    try:
        # Step 1: Read only 5 currently failed products (distinct titles)
        all_failed = db.query(Product).filter(Product.status == "failed").all()
        
        seen_names = set()
        test_products = []
        for p in all_failed:
            if p.product_name not in seen_names:
                seen_names.add(p.product_name)
                test_products.append(p)
            if len(test_products) == 5:
                break

        print("=" * 85)
        print("READ-ONLY PROTOTYPE: AMAZON SEARCH RESULTS FALLBACK (5 TEST PRODUCTS)")
        print("=" * 85 + "\n")

        successful_read_count = 0
        no_data_count = 0
        total_candidates_extracted = 0

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            
            for idx, product in enumerate(test_products, 1):
                try:
                    # Step 3: Seed generation using existing clean_product_title_to_seeds
                    seeds = clean_product_title_to_seeds(product.product_name, product.category)
                    seed = seeds[0] if seeds else product.product_name
                    search_url = f"https://www.amazon.in/s?k={urllib.parse.quote_plus(seed)}"

                    print(f"Product #{idx}: ID={product.id}")
                    print(f"  Product Name      : {product.product_name}")
                    print(f"  Category          : {product.category}")
                    print(f"  Generated Seed    : {seed}")
                    print(f"  Amazon Search URL : {search_url}")

                    # Step 4 & 5: Perform Amazon search and extract titles
                    titles = fetch_amazon_search_results(seed, browser=browser)
                    num_titles = len(titles)
                    print(f"  Search Results Read: {num_titles} product titles")

                    # Extract keyword candidates from search result titles
                    candidates = extract_keyword_candidates_from_titles(titles, seed)
                    print(f"  Keyword Candidates Extracted ({len(candidates)}):")
                    if candidates:
                        for c in candidates[:5]:
                            print(f"    - {c}")
                        successful_read_count += 1
                        total_candidates_extracted += len(candidates)
                    else:
                        print("    - [No usable search result titles found]")
                        no_data_count += 1

                    print("-" * 85 + "\n")

                except Exception as err:
                    print(f"  [ERROR] Failed to process product ID {product.id}: {err}")
                    no_data_count += 1
                    print("-" * 85 + "\n")

            browser.close()

        print("=" * 85)
        print("PROTOTYPE TEST SUMMARY")
        print("=" * 85)
        print(f"- Products tested                                  : {len(test_products)}")
        print(f"- Products where search results successfully read : {successful_read_count}")
        print(f"- Products where no usable search data was found   : {no_data_count}")
        print(f"- Total keyword candidates extracted              : {total_candidates_extracted}")
        print("=" * 85)

    finally:
        db.close()

if __name__ == "__main__":
    main()
