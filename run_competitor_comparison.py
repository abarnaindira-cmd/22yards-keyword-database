import argparse
import sys
import os

# Ensure UTF-8 output on Windows consoles
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.database import SessionLocal
from app.services.competitor_comparator import run_comparison_for_all_processed


def main():
    parser = argparse.ArgumentParser(description="Product vs Competitor Keyword Gap Analysis")
    parser.add_argument("--limit", type=int, default=10, help="Number of processed source products to analyze (default: 10)")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        print("=" * 95)
        print(f"PRODUCT VS COMPETITOR KEYWORD GAP ANALYSIS REPORT (Limit: {args.limit} Products)")
        print("=" * 95 + "\n")

        comparison_results = run_comparison_for_all_processed(db, limit=args.limit)

        if not comparison_results:
            print("No processed competitor data found in MySQL database.")
            return

        for idx, res in enumerate(comparison_results, 1):
            if "error" in res:
                print(f"Product #{idx}: ERROR - {res['error']}")
                continue

            print("=" * 95)
            print(f"PRODUCT #{idx}: [{res['source_product_asin']}] {res['product_name']}")
            print(f"Category: {res['category'] or 'N/A'}")
            print(f"Competitors Analyzed: {res['competitors_analyzed_count']} top competitor products")
            print(f"Our Harvested Keywords: {res['own_keywords_count']} keywords")
            print("-" * 95)

            # Sample Competitor Titles
            print("Top Competitor Listing Titles:")
            for t_idx, title in enumerate(res.get("competitor_sample_titles", [])[:3], 1):
                print(f"  {t_idx}. {title[:80]}...")

            print("\nCoverage Summary:")
            print(f"  - Total Relevant Competitor Keywords Evaluated: {res['filtered_relevant_competitor_keywords_count']}")
            print(f"  - Covered in Our Product/Keywords          : {res['covered_keywords_count']}")
            print(f"  - Missing High-Value Opportunities         : {res['missing_keywords_count']}")

            # Covered Keywords Sample
            print("\nSample Covered Keywords (Already Present in Our Listing/Keywords):")
            covered = res.get("covered_keywords", [])
            if covered:
                for c in covered[:5]:
                    print(f"  ✓ {c['keyword']} (Match: {c['match_type']})")
            else:
                print("  (None covered in sample)")

            # Missing Keywords Opportunities
            print("\nRECOMMENDED MISSING COMPETITOR KEYWORDS (Gap Opportunities):")
            missing = res.get("missing_keywords", [])
            if missing:
                for m_idx, m in enumerate(missing[:10], 1):
                    align_flag = " [Category Aligned]" if m["category_aligned"] else ""
                    print(f"  ★ {m_idx:2d}. {m['keyword']}{align_flag} (Relevance Score: {m['relevance_score']:.1f})")
            else:
                print("  (No missing relevant keywords identified)")

            print("=" * 95 + "\n")

        print("=" * 95)
        print(f"SUMMARY: Completed comparison for {len(comparison_results)} source products.")
        print("=" * 95)

    finally:
        db.close()


if __name__ == "__main__":
    main()
