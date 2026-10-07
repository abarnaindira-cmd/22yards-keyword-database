import os
import glob
import sys
sys.stdout.reconfigure(encoding='utf-8')

from sqlalchemy import text
from app.database import SessionLocal
from app.models.product import Product
from app.config import get_groq_api_key, is_groq_configured
from app.services.title_generator import fallback_generate_title

def run_audit():
    print("==========================================================================")
    print("AUDIT REPORT: GROQ TITLE GENERATION FOR LATEST UPLOADED BATCH (100 PRODUCTS)")
    print("==========================================================================")

    # 1. Verify GROQ_API_KEY secure loading
    key = get_groq_api_key()
    configured = is_groq_configured()
    key_length = len(key) if key else 0
    masked_preview = f"{key[:4]}...{key[-4:]}" if (key and len(key) >= 8) else "(masked)"

    print("\n[SECTION 1: GROQ API KEY CONFIGURATION AUDIT]")
    print(f"  - Groq Configured Status : {configured}")
    print(f"  - Key Present            : {bool(key)}")
    print(f"  - Key Length             : {key_length} characters")
    print(f"  - Key Format Valid       : {key.startswith('gsk_') if key else False}")
    print(f"  - Key Masked Preview     : {masked_preview}")

    # 2. Inspect Historical Task Logs
    print("\n[SECTION 2: HISTORICAL RUN TASK LOGS INSPECTION]")
    task_logs = [
        ("task-1943.log", "Batch Run 1 (Initial Rate Limited Run)"),
        ("task-2016.log", "Batch Run 2 (Full 100-Product Execution)"),
        ("task-2052.log", "Batch Run 3 (Retry & Final Sweep)")
    ]

    log_dir = r"C:\Users\abarn\.gemini\antigravity-ide\brain\d3f5e3c2-4ed2-48db-8c50-656bd6d08101\.system_generated\tasks"

    for log_filename, desc in task_logs:
        full_path = os.path.join(log_dir, log_filename)
        if os.path.exists(full_path):
            with open(full_path, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
            print(f"  - Log File: {log_filename} ({desc})")
            print(f"    Lines: {len(lines)} | Bytes: {os.path.getsize(full_path)}")
            # Print last few lines of interest
            summary_lines = [l.strip() for l in lines if ("SUMMARY" in l or "Count" in l or "Verified" in l or "Method" in l or "Rate limit" in l)]
            if summary_lines:
                print("    Key Findings in Log:")
                for sl in summary_lines[-5:]:
                    print(f"      * {sl}")
        else:
            print(f"  - Log File: {log_filename} (Not found at {full_path})")

    # 3. Database Source Verification for 100 Products
    print("\n[SECTION 3: DATABASE SOURCE VERIFICATION FOR 100 PRODUCTS (IDs 4-103)]")
    db = SessionLocal()

    products = db.query(Product).filter(Product.id.between(4, 103)).order_by(Product.id.asc()).all()
    target_asins = [p.asin for p in products if p.asin]

    rows = db.execute(
        text("SELECT sku_id, product_name, final_product_title, all_keywords FROM final_product_data WHERE sku_id IN :asins"),
        {"asins": tuple(target_asins)}
    ).fetchall()

    total_uploaded = len(target_asins)
    total_saved = len(rows)
    groq_generated_count = 0
    fallback_generated_count = 0
    failed_count = total_uploaded - total_saved

    for r in rows:
        sku_id, p_name, final_title, kws_json = r[0], r[1], r[2], r[3]
        import json
        kws = json.loads(kws_json) if isinstance(kws_json, str) else (kws_json or [])
        expected_fallback = fallback_generate_title(p_name, kws)

        if final_title == expected_fallback:
            fallback_generated_count += 1
        else:
            groq_generated_count += 1

    print("\n[SECTION 4: EXACT AUDIT COUNTS]")
    print(f"  - Total Uploaded Batch Products (IDs 4-103) : {total_uploaded}")
    print(f"  - Groq-Generated Titles                      : {groq_generated_count}")
    print(f"  - Fallback-Generated Titles                  : {fallback_generated_count}")
    print(f"  - Failed Titles                              : {failed_count}")
    print(f"  - Total Saved Records in MySQL               : {total_saved}/{total_uploaded}")

    db.close()
    print("\n==========================================================================")
    print("AUDIT COMPLETE")
    print("==========================================================================")

if __name__ == "__main__":
    run_audit()
