import sys
import time
import re

sys.path.insert(0, r"d:\22yards_keyword_database_competitor_ready\22yards_keyword_database")

from playwright.sync_api import sync_playwright
from app.database import SessionLocal
from app.models.product import Product
from app.services.flipkart_suggestion_runner import clean_flipkart_title_to_seeds
from app.services.flipkart_keyword_collector import collect_flipkart_keywords

def get_enhanced_seeds_for_failed_product(product_name, category):
    seeds = clean_flipkart_title_to_seeds(product_name, category)
    if not seeds:
        seeds = [product_name]

    enhanced = list(seeds)

    # 1. Vector-X Jogging Shoe Thunderstorm
    if "Thunderstorm" in product_name:
        for s in ["Vector X Jogging Shoes", "Vector X Shoes", "Jogging Shoes"]:
            if s not in enhanced:
                enhanced.append(s)

    # 2. Ball category
    elif category == "Ball" or "Cricket Ball" in product_name or "Leather" in product_name:
        for s in ["Cricket Ball", "Leather Cricket Ball", "Tennis Cricket Ball"]:
            if s not in enhanced:
                enhanced.append(s)

    # 3. Batting Gloves
    elif category == "Batting Gloves" or "Batting Gloves" in product_name:
        for s in ["Cricket Batting Gloves", "SS Batting Gloves"]:
            if s not in enhanced:
                enhanced.append(s)

    # 4. Cricket Bat
    elif category == "Cricket Bat" or "Cricket Bat" in product_name:
        for s in ["SS Cricket Bat", "English Willow Cricket Bat", "Kashmir Willow Cricket Bat"]:
            if s not in enhanced:
                enhanced.append(s)

    # 5. Cricket Accessories
    elif category == "Cricket Accessories":
        if "Mini Bat" in product_name:
            enhanced.append("Mini Cricket Bat")
        elif "Headband" in product_name:
            enhanced.append("Cricket Headband")
        elif "Wrist Band" in product_name:
            enhanced.append("Cricket Wrist Band")
        elif "Grip" in product_name:
            enhanced.append("Cricket Bat Grip")

    # 6. Cricket Stumps / Pads
    elif "Stump" in product_name:
        enhanced.append("Cricket Stumps")
    elif "Batting Pad" in product_name or "Batting Legguard" in product_name:
        enhanced.append("Cricket Batting Pads")
    elif "Wicket Keeping" in product_name:
        enhanced.append("Wicket Keeping Pads")

    # Deduplicate while preserving order
    final_seeds = []
    seen = set()
    for s in enhanced:
        s_clean = re.sub(r'\s+', ' ', s).strip()
        if s_clean and s_clean.lower() not in seen:
            seen.add(s_clean.lower())
            final_seeds.append(s_clean)

    return final_seeds

def main():
    db = SessionLocal()
    # Sample products from each failure category
    sample_ids = [760, 669, 674, 686, 660, 725]
    prods = db.query(Product).filter(Product.id.in_(sample_ids)).all()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
            viewport={'width': 1280, 'height': 800}
        )
        page.goto('https://www.flipkart.com', wait_until='domcontentloaded', timeout=25000)
        page.keyboard.press('Escape')
        time.sleep(1)

        for prod in prods:
            seeds = get_enhanced_seeds_for_failed_product(prod.product_name, prod.category)
            print(f"=== Product ID {prod.id}: {prod.product_name} | Seeds: {seeds} ===")
            collected = set()
            for seed in seeds:
                search_input = page.locator("input[name='q'], input[title*='Search'], input[placeholder*='Search']")
                if search_input.count() > 0:
                    search_input.first.evaluate("el => el.focus()")
                    search_input.first.fill("")
                    search_input.first.fill(seed)
                    time.sleep(1.5)

                    selectors = [
                        "ul._1sB9Bx li", "ul._3D2Eav li", "div._1AMrR3 div", 
                        "form._2rslOn ul li", "ul[class*='suggest'] li", 
                        "div[class*='suggestion']", "li[class*='suggest']",
                        "a[class*='_3qv22d']", "ul._1cdP2B li", "div._3q2v2d"
                    ]
                    found = []
                    for sel in selectors:
                        elems = page.locator(sel)
                        cnt = elems.count()
                        if cnt > 0:
                            for i in range(cnt):
                                txt = elems.nth(i).inner_text().strip()
                                if txt:
                                    cleaned = txt.split('\n')[0].strip()
                                    if cleaned and cleaned not in found:
                                        found.append(cleaned)
                            if found:
                                break
                    if not found:
                        api_res = collect_flipkart_keywords(seed)
                        found.extend(api_res)

                    for item in found:
                        collected.add(item)
                    print(f"  Seed '{seed}' -> Found {len(found)} suggestions: {found[:3]}")
            print(f"  Total unique suggestions collected: {len(collected)}\n")
        browser.close()
    db.close()

if __name__ == "__main__":
    main()
