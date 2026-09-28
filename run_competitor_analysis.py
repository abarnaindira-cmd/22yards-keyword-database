import argparse
import json
import os
import sys

# Ensure UTF-8 output on Windows consoles
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.database import SessionLocal, init_db
from app.services.competitor_analysis import run_competitor_batch


def main():
    parser = argparse.ArgumentParser(description="Top 20 Competitor Product Details & Keyword Collector")
    parser.add_argument("--products", type=int, default=3, help="Number of completed products to test/process")
    parser.add_argument("--offset", type=int, default=0, help="Number of completed products to skip (e.g. 100)")
    parser.add_argument("--keywords-per-product", type=int, default=1)
    parser.add_argument("--top-competitors", type=int, default=20)
    parser.add_argument("--pages", type=int, default=2)
    parser.add_argument("--delay", type=float, default=1.0)
    parser.add_argument("--no-write", action="store_true", help="Disable MySQL write (default is write enabled)")
    args = parser.parse_args()

    write_to_db = not args.no_write

    init_db()
    db = SessionLocal()
    try:
        print("=" * 90)
        print("TOP 20 COMPETITOR PRODUCTS & KEYWORD EXTRACTION - CONTROLLED TEST")
        print(f"Products: {args.products} | Offset: {args.offset} | Keywords/Product: {args.keywords_per_product} | Top competitors: {args.top_competitors}")
        print(f"Pages: {args.pages} | Write to MySQL: {write_to_db}")
        print("=" * 90)
        result = run_competitor_batch(
            db,
            product_limit=args.products,
            offset=args.offset,
            keywords_per_product=args.keywords_per_product,
            top_competitors=args.top_competitors,
            max_pages=args.pages,
            delay_seconds=args.delay,
            write_db=write_to_db,
        )

        print("\n" + "=" * 90)
        print("COMPETITOR PRODUCT DETAILS & KEYWORD EXTRACTION RESULTS")
        print("=" * 90 + "\n")

        total_cp_inserted = 0
        total_cp_updated = 0
        total_ck_inserted = 0

        for item in result.get("details", []):
            if "error" in item:
                print(f"Product ID: {item.get('product_id')} | SKU: {item.get('product_asin')}")
                print(f"Keyword: {item.get('keyword')}")
                print(f"Error: {item.get('error')}")
                print("-" * 70)
                continue

            print(f"Product ID: {item.get('product_id')} | SKU: {item.get('product_asin')}")
            print(f"Keyword: {item.get('keyword')}")
            competitors = item.get("competitors", [])
            extracted_kws = item.get("extracted_competitor_keywords", [])
            db_stats = item.get("db_stats", {})

            total_cp_inserted += db_stats.get("competitor_products_inserted", 0)
            total_cp_updated += db_stats.get("competitor_products_updated", 0)
            total_ck_inserted += db_stats.get("competitor_keywords_inserted", 0)

            print(f"Top Competitor Products Collected: {len(competitors)}")
            if write_to_db:
                print(f"MySQL DB Writes: Inserted {db_stats.get('competitor_products_inserted', 0)} new competitor products ({db_stats.get('competitor_products_updated', 0)} updated), {db_stats.get('competitor_keywords_inserted', 0)} competitor keywords")
            print("-" * 70)

            print("Top Competitor Product Details Summary:")
            for idx, c in enumerate(competitors, 1):
                c_asin = c.get("asin")
                c_title = (c.get("title") or "")[:55]
                c_price = c.get("price") or "N/A"
                c_rating = c.get("rating") or "N/A"
                c_reviews_count = c.get("review_count") or 0
                bp_count = len(c.get("bullet_points") or [])
                desc_len = len(c.get("description") or "")
                rec_count = len(c.get("reviews") or [])
                print(f"  {idx:2d}. ASIN: {c_asin} | Title: {c_title}...")
                print(f"      Price: {c_price} | Rating: {c_rating} ({c_reviews_count} reviews) | Bullets: {bp_count} | Desc Chars: {desc_len} | Customer Reviews Snippets: {rec_count}")

            print("\nExtracted Competitor Keywords:")
            if extracted_kws:
                for k_idx, kw_text in enumerate(extracted_kws, 1):
                    print(f"  {k_idx:2d}. {kw_text}")
            else:
                print("  (None extracted)")
            print("=" * 90 + "\n")

        print("Summary:")
        print(f"  Products Tested: {result.get('products_tested')}")
        print(f"  Product ID Range: {result.get('product_id_start')} to {result.get('product_id_end')}")
        print(f"  Keyword Tests Run: {result.get('keyword_tests')}")
        print(f"  Write to MySQL: {result.get('write_db')}")
        if write_to_db:
            print(f"  MySQL Rows Inserted (Competitor Products) : {total_cp_inserted}")
            print(f"  MySQL Rows Updated (Competitor Products)  : {total_cp_updated}")
            print(f"  MySQL Rows Inserted (Competitor Keywords) : {total_ck_inserted}")

    finally:
        db.close()


if __name__ == "__main__":
    main()




