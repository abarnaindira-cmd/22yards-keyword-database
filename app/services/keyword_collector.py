import re
from typing import List, Optional
import httpx

AMAZON_COMPLETION_URL = "https://completion.amazon.com/api/2017/suggestions"
DEFAULT_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"

BROAD_CATEGORIES = {
    "apparel", "shoe", "shoes", "gym training"
}

GENERIC_CATEGORIES = {
    "apparel", "shoe", "shoes", "cricket helmet", "batting gloves", "batting pad",
    "thigh guard", "abdo guard", "elbow guard", "cricket bat", "fiber trophies",
    "badminton racket", "cricket accessories", "gym training", "umbrella",
    "cricket accessories - grip", "skates protective gear kit", "kit bag",
    "swimming cap", "sunscreen", "shuttlecock", "wicket keeping gloves - inner",
    "ball", "cricket stumps", "wicket keeping gloves", "headband", "shin guard",
    "water bottles", "badminton accessories", "helmet", "gloves", "pads", "pant", "pants"
}

KNOWN_BRANDS = [
    "vector x", "viva fitness", "viva", "sg", "ss", "ton", "cosco", "dsc", "gm",
    "mrf", "ceat", "kookaburra", "bdm", "spartan", "ipl", "minimal buzz", "minimal",
    "nike", "adidas", "puma", "under armour"
]

def clean_product_title_to_seeds(product_name: str, category: Optional[str] = None) -> List[str]:
    """
    Extract clean search query seeds from an Amazon product title and category.
    Rules & Fallback Strategy:
    1. Do NOT use brand-only seeds (e.g., 'Vector X', 'Viva Fitness', 'SS', 'SG', 'Ton').
    2. Do NOT use ultra-broad category-only seeds (e.g., 'APPAREL', 'Shoe').
    3. Exclude single-word generic noun seeds (e.g., 'Helmet', 'Gloves', 'Pants').
    4. Prioritize multi-word product-type phrases (e.g., 'Fiber Trophy', 'Athletic Shorts', 'Cricket Bat Grip', 'Protective Gear Set').
    5. Strip model/SKU numbers (e.g. 2114 A, VS-029, CS-100, 3001), kit tags, size/age tags (e.g. '(Kit Product)', 'Youth', 'Adult', 'EW Jr.').
    6. For model-code-heavy or obscure names, fall back to clean product-type terms from category/title.
    """
    if not product_name and not category:
        return []

    raw_name = (product_name or "").strip()

    # 1. Strip parenthesized content and brackets
    text = re.sub(r'\(.*?\)', ' ', raw_name)
    text = re.sub(r'\[.*?\]', ' ', text)

    # 2. Strip model codes like VS-029, CS-100, etc.
    text = re.sub(r'\b[A-Z]{1,3}[-\s]?\d{2,5}[A-Z]?\b', ' ', text)

    # 3. Strip noise phrases, model tags, size/age tags, internal brand codes
    noise_patterns = [
        r'\bkit product\b', r'\bew jr\b', r'\bs\.?jr\b', r'\br\.?h\b', r'\bl\.?h\b',
        r'\bkit \d+\b', r'\byouth\b', r'\badult\b', r'\bjunior\b', r'\bbiginner\b',
        r'\bbeginner\b', r'\bew\b', r'\bjr\b', r'\bpro\b', r'\bpremium\b', r'\bsuper\b',
        r'\bultra\b', r'\bmax\b', r'\bedition\b', r'\btest\b', r'\bsmartech\b',
        r'\bgutsy\b', r'\bgripper\b', r'\bhitech\b', r'\bmoulded\b', r'\bcms\b',
        r'\bminimal buzz\b', r'\bminimal\b', r'\bbuzz\b', r'\bultrasoft\b', r'\bstrength\b'
    ]
    for pat in noise_patterns:
        text = re.sub(pat, ' ', text, flags=re.IGNORECASE)

    # 4. Replace non-alphanumeric punctuation with spaces
    text = re.sub(r'[^\w\s]', ' ', text)

    # 5. Tokenize & filter pure model numbers / standalone digits / lone model letters / stop words
    raw_words = [w for w in text.split() if w.strip()]
    filtered_words = []
    stop_tokens = {"in", "s", "and", "or", "for", "with", "of", "to", "by", "a", "an", "the"}
    for idx_w, w in enumerate(raw_words):
        if re.match(r'^\d+$', w): # pure digits e.g. 2114, 3001, 4, 1
            continue
        if len(w) == 1:
            continue
        if w.lower() in stop_tokens:
            continue
        filtered_words.append(w)

    words = filtered_words if filtered_words else raw_words
    if not words and not category:
        return []

    # 6. Extract Brand
    brand = ""
    lower_title = " ".join(words).lower()
    for b in KNOWN_BRANDS:
        if lower_title.startswith(b):
            b_word_count = len(b.split())
            brand = " ".join(words[:b_word_count])
            break

    if not brand and words:
        if words[0].lower() in {"vector", "viva", "sg", "ss", "ton", "cosco", "dsc", "gm", "mrf", "ceat", "ipl", "rs", "mb"}:
            brand = words[0]

    brand_word_count = len(brand.split()) if brand else 0
    non_brand_words = words[brand_word_count:]

    seeds = []

    # A. Clean Category Name
    cat_cleaned = re.sub(r'[^\w\s]', ' ', category or '').strip()
    cat_cleaned = re.sub(r'\s+', ' ', cat_cleaned)

    # Standardize specific categories
    cat_search_term = cat_cleaned
    if cat_cleaned.lower() == "fiber trophies":
        cat_search_term = "Fiber Trophy"
    elif cat_cleaned.lower() == "skates protective gear kit":
        cat_search_term = "Protective Gear Set"
    elif cat_cleaned.lower() in {"cricket accessories - grip", "cricket accessories grip"}:
        cat_search_term = "Cricket Bat Grip"

    # B. Brand + Category (ONLY if Category is specific e.g., 'SG Cricket Helmet', 'SS Batting Gloves')
    if brand and cat_search_term and cat_search_term.lower() not in BROAD_CATEGORIES:
        seeds.append(f"{brand} {cat_search_term}")

    # C. Brand + Primary Non-Brand Word (e.g. 'SG Helmet')
    if brand and non_brand_words and cat_search_term and cat_search_term.lower() not in BROAD_CATEGORIES:
        primary_nb = non_brand_words[0]
        if primary_nb.lower() not in cat_search_term.lower():
            seeds.append(f"{brand} {primary_nb}")

    # D. Non-Brand Core Product Phrase (e.g. "Fiber Trophy", "Athletic Shorts", "Fighter Jacket", "Mens Track Pant", "Cricket Bat Grip", "Full Sleeve T Shirt")
    if len(non_brand_words) >= 2:
        nb_full = " ".join(non_brand_words[:min(len(non_brand_words), 4)])
        seeds.append(nb_full)
    elif len(non_brand_words) == 1:
        if cat_search_term and cat_search_term.lower() not in BROAD_CATEGORIES:
            nb_word = non_brand_words[0]
            if nb_word.lower() not in cat_search_term.lower():
                seeds.append(f"{nb_word} {cat_search_term}")

    # E. Product Noun Type Fallback (e.g., if non_brand_words is "Cricket Spike Shoes" -> "Cricket Shoes")
    if len(non_brand_words) >= 3 and non_brand_words[-1].lower() in {"shoes", "pants", "pant", "gloves", "bat", "pad", "grip", "jacket", "shorts", "sweatshirt", "t-shirt", "tshirt", "shirt"}:
        seeds.append(f"{non_brand_words[0]} {non_brand_words[-1]}")

    # F. Category Fallback for Model-Heavy / Obscure Titles
    if cat_search_term and cat_search_term.lower() not in BROAD_CATEGORIES:
        seeds.append(cat_search_term)

    # G. Core product type fallbacks
    raw_lower = raw_name.lower()
    if "full sleeve" in raw_lower:
        seeds.append("Full Sleeve T-Shirt")
    if "basic t-shirt" in raw_lower or "basic tshirt" in raw_lower:
        seeds.append("Basic T-Shirt")
    if "mesh" in raw_lower and ("t-shirt" in raw_lower or "shirt" in raw_lower):
        seeds.append("Mesh T-Shirt")

    # G. Special fallback for Fiber Trophy -> also add Cricket Trophy to ensure autocomplete suggestions
    if any(s.lower() == "fiber trophy" for s in seeds):
        seeds.append("Cricket Trophy")

    # Filter and validate seeds:
    # Rule 1: NO brand-only seeds (e.g., 'Vector X', 'Viva Fitness', 'SS', 'SG', 'Ton')
    # Rule 2: NO ultra-broad category seeds (e.g., 'APPAREL', 'Shoe')
    # Rule 3: NO single-word generic noun seeds (e.g., 'Helmet', 'Gloves')
    final_seeds = []
    brand_lower = brand.lower().strip()

    for s in seeds:
        s_clean = re.sub(r'\s+', ' ', s).strip()
        s_lower = s_clean.lower()

        if not s_clean or len(s_clean.split()) < 2:
            continue

        # Exclude Brand-Only seeds
        if s_lower == brand_lower or s_lower in KNOWN_BRANDS or s_lower in {"vector x", "viva fitness", "viva", "sg", "ss", "ton", "cosco", "dsc", "gm", "mrf", "ceat"}:
            continue

        # Exclude Ultra-Broad Category-Only seeds
        if s_lower in BROAD_CATEGORIES:
            continue

        if s_lower not in [x.lower() for x in final_seeds]:
            final_seeds.append(s_clean)

    return final_seeds

def fetch_amazon_suggestions_api(query: str) -> List[str]:
    """
    Fetch search suggestions directly from Amazon's autocomplete API.
    Fast, lightweight, and reliable.
    """
    headers = {
        "User-Agent": DEFAULT_USER_AGENT,
        "Accept-Language": "en-US,en;q=0.9,en-IN;q=0.8",
        "Accept": "application/json, text/javascript, */*; q=0.01",
    }

    keywords = []

    # Query using standard marketplace IDs (ATVPDKIKX0DER / A21TJRUUN4KGV)
    for mid_val in ["ATVPDKIKX0DER", "A21TJRUUN4KGV"]:
        params = {
            "limit": "11",
            "prefix": query,
            "suggestion-type": "KEYWORD",
            "page-type": "Search",
            "alias": "aps",
            "mid": mid_val,
        }

        try:
            with httpx.Client(timeout=8.0) as client:
                resp = client.get(AMAZON_COMPLETION_URL, params=params, headers=headers)
                if resp.status_code == 200:
                    data = resp.json()
                    suggestions = data.get("suggestions", [])
                    for item in suggestions:
                        val = item.get("value", "").strip() if isinstance(item, dict) else str(item).strip()
                        if val and val.lower() not in [k.lower() for k in keywords]:
                            keywords.append(val)
                    if keywords:
                        break
        except Exception as e:
            print(f"[Collector API Warning] Autocomplete API request failed for '{query}' (mid={mid_val}): {e}")

    return keywords

def collect_amazon_keywords(seed_keyword: str, browser=None) -> List[str]:
    """
    Collect Amazon search suggestions for a seed keyword.
    Tries fast API first, falling back to Playwright UI browser scraping if needed.
    """
    if not seed_keyword:
        return []

    # 1. Try fast API extraction
    api_keywords = fetch_amazon_suggestions_api(seed_keyword)
    if api_keywords:
        return api_keywords

    # 2. Fallback to Playwright browser if browser instance provided
    if browser:
        context = browser.new_context(
            user_agent=DEFAULT_USER_AGENT,
            locale="en-IN",
            viewport={"width": 1366, "height": 900}
        )
        context.set_default_timeout(20000)
        page = context.new_page()

        try:
            page.goto("https://www.amazon.in/", wait_until="domcontentloaded")
            search_box = page.locator("#twotabsearchtextbox")
            search_box.wait_for(timeout=15000)
            search_box.fill(seed_keyword)
            page.wait_for_timeout(3000)

            suggestions = page.locator("div.s-suggestion").all_inner_texts()
            keywords = []

            for suggestion in suggestions:
                keyword = suggestion.strip()
                if keyword and keyword.lower() not in [k.lower() for k in keywords]:
                    keywords.append(keyword)

            return keywords
        except Exception as e:
            print(f"[Collector Browser Error] Playwright scraping failed for '{seed_keyword}': {e}")
            return []
        finally:
            context.close()

    return []
