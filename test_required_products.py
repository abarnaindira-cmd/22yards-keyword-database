import sys
from typing import List, Optional

from app.services.keyword_collector import clean_product_title_to_seeds, collect_amazon_keywords

test_products = [
    {"name": "FIBER TROPHY 2114 A", "category": "Fiber Trophies"},
    {"name": "Athletic Shorts VS-029", "category": "APPAREL"},
    {"name": "THIGH GUARD TEST", "category": "Thigh Guard"},
    {"name": "Defender 4 in 1 Protective Gears Set (Beginner)", "category": "Skates Protective Gear Kit"},
    {"name": "SG HELMET SMARTECH", "category": "Cricket Helmet"},
    {"name": "Vector X Fighter Men's Jacket", "category": "APPAREL"},
    {"name": "Cricket Bat Grip - GRIPPER", "category": "Cricket Accessories - Grip"}
]

def main():
    print("=" * 85)
    print("READ-ONLY TEST: FALLBACK SEED GENERATION & AMAZON SUGGESTIONS")
    print("=" * 85 + "\n")

    summary_rows = []

    for idx, prod in enumerate(test_products, 1):
        p_name = prod["name"]
        p_cat = prod["category"]

        # 1 & 2: Product name & category
        print(f"Product #{idx}: {p_name}")
        print(f"  Category: {p_cat}")

        # 3: Generated seeds using clean_product_title_to_seeds()
        seeds = clean_product_title_to_seeds(p_name, p_cat)
        print(f"  Generated Seeds: {seeds}")

        print("  Amazon Suggestions Per Seed:")
        unique_keywords = []

        # 4 & 5: Suggestion count per seed and returned suggestions
        for seed in seeds:
            suggestions = collect_amazon_keywords(seed)
            count = len(suggestions)
            print(f"    - Seed '{seed}': {count} suggestion(s)")
            print(f"      Returned Suggestions: {suggestions}")

            for kw in suggestions:
                if kw and kw.lower() not in [k.lower() for k in unique_keywords]:
                    unique_keywords.append(kw)

        print(f"  Total Unique Amazon Keywords Harvested: {len(unique_keywords)}")
        print("-" * 85 + "\n")

        summary_rows.append((p_name, seeds, len(unique_keywords)))

    print("=" * 85)
    print("SUMMARY")
    print("=" * 85)
    print(f"{'Product Name':<45} | {'Generated Seeds':<30} | {'Keywords':<8}")
    print("-" * 85)
    for name, s_list, kw_count in summary_rows:
        s_str = ", ".join(f"'{s}'" for s in s_list)
        print(f"{name:<45} | {s_str:<30} | {kw_count:<8}")

if __name__ == "__main__":
    main()
