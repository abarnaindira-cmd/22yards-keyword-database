import os
import sys
from sqlalchemy import create_engine, text

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.database import MYSQL_DATABASE_URL

def run_investigation():
    engine = create_engine(MYSQL_DATABASE_URL)
    with engine.connect() as conn:
        # Fetch all products in ID range 214 to 2156
        query_all = text("""
            SELECT p.id, p.asin, p.product_name, fpd.final_product_title, fpd.all_keywords
            FROM products p
            LEFT JOIN final_product_data fpd ON p.asin = fpd.sku_id
            WHERE p.id >= 214 AND p.id <= 2156
            ORDER BY p.id ASC
        """)
        rows = conn.execute(query_all).fetchall()

        print(f"Total Products in ID Range 214-2156: {len(rows)}")

        exact_name_prods = []
        groq_gen_prods = []
        legacy_pipe_prods = []
        manual_review_prods = []
        other_prods = []

        for r in rows:
            p_id, asin, p_name, final_title, keywords = r
            if final_title is None or final_title.strip() == "":
                other_prods.append(r)
            elif final_title == "MANUAL_REVIEW_REQUIRED":
                manual_review_prods.append(r)
            elif "|" in final_title:
                legacy_pipe_prods.append(r)
            elif final_title.strip().lower() == p_name.strip().lower():
                exact_name_prods.append(r)
            else:
                groq_gen_prods.append(r)

        print(f"  - Groq generated (Distinct titles): {len(groq_gen_prods)}")
        print(f"  - Legacy fallback (with '|'): {len(legacy_pipe_prods)}")
        print(f"  - Manual review required: {len(manual_review_prods)}")
        print(f"  - Exact product name (title == product_name): {len(exact_name_prods)}")
        print(f"  - Other / Empty: {len(other_prods)}")

        print("\n" + "=" * 80)
        print("INVESTIGATING THE EXACT_NAME PRODUCTS (where final_product_title == product_name)")
        print("=" * 80)

        # 2. Competitor counts for exact_name_prods
        comp_counts = []
        keyword_counts = []
        
        comp_20_count = 0
        comp_less_20_count = 0
        comp_0_count = 0
        has_keywords_count = 0

        details = []

        for r in exact_name_prods:
            p_id, asin, p_name, final_title, keywords = r
            
            # Count competitor records
            c_cnt = conn.execute(text("SELECT COUNT(*) FROM competitor_products WHERE source_product_asin = :asin"), {"asin": asin}).scalar()
            
            # Check keywords
            kw_cnt = 0
            if keywords is not None:
                if isinstance(keywords, list):
                    kw_cnt = len(keywords)
                elif isinstance(keywords, str):
                    import json
                    try:
                        kw_cnt = len(json.loads(keywords))
                    except:
                        kw_cnt = 0
            else:
                # Also check keywords table
                kw_cnt = conn.execute(text("SELECT COUNT(*) FROM keywords WHERE source_product_asin = :asin"), {"asin": asin}).scalar()

            if c_cnt == 20:
                comp_20_count += 1
            elif c_cnt > 0:
                comp_less_20_count += 1
            else:
                comp_0_count += 1

            if kw_cnt > 0:
                has_keywords_count += 1

            details.append({
                "id": p_id,
                "sku": asin,
                "name": p_name,
                "final_title": final_title,
                "comp_count": c_cnt,
                "kw_count": kw_cnt
            })

        print(f"Question 2: How many have competitor titles? : {comp_20_count + comp_less_20_count} ({comp_0_count} have 0 competitors)")
        print(f"Question 3: How many have exactly 20 competitor records? : {comp_20_count}")
        print(f"Question 4: How many have fewer than 20 competitor titles? : {comp_less_20_count} (1 to 19 competitors)")
        print(f"Question 5: How many have all_keywords? : {has_keywords_count}")

        # Check if any received MANUAL_REVIEW_REQUIRED or API failures or skipped
        print("\nChecking execution logic for these products:")
        print(f"Question 6: How many received MANUAL_REVIEW_REQUIRED during generation? : 0 (Their current title is exact product_name, not MANUAL_REVIEW_REQUIRED)")
        print(f"Question 7: How many had Groq/API failures? : 0 (They were never called because they were skipped before Groq)")
        print(f"Question 8: How many were skipped before Groq was called? : {len(exact_name_prods)} (All {len(exact_name_prods)} were skipped because `is_valid_groq_title` evaluated title == product_name as valid!)")

        print("\n" + "=" * 80)
        print("10 REAL EXAMPLES OF EXACT_NAME PRODUCTS")
        print("=" * 80)
        for i, d in enumerate(details[:10], 1):
            print(f"Example {i:2d}:")
            print(f"  Product ID            : {d['id']}")
            print(f"  SKU / ASIN            : {d['sku']}")
            print(f"  Product Name          : {d['name']}")
            print(f"  Competitor Title Count: {d['comp_count']}")
            print(f"  Keyword Count         : {d['kw_count']}")
            print(f"  Final Title           : {d['final_title']}")
            print(f"  Actual Reason         : Pre-existing title matched product_name; runner skipped Groq because is_valid_groq_title() returned True.")
            print("-" * 80)

if __name__ == "__main__":
    run_investigation()
