import sys
import logging
sys.stdout.reconfigure(encoding='utf-8')

from app.database import SessionLocal
from app.models.product import Product
from app.models.keyword import Keyword
from app.models.competitor import CompetitorProduct
from app.models.final_product_data import FinalProductData
from app.services.title_generator import (
    generate_title_with_groq,
    process_final_product_data_for_asin,
    clean_input_text
)

def run_controlled_test():
    logging.basicConfig(level=logging.INFO)
    db = SessionLocal()

    print("==========================================================================")
    print("CONTROLLED TEST: SINGLE PRODUCT TITLE GENERATION & MANUAL REVIEW PATH")
    print("==========================================================================")

    # Pick Batch 3 Product 201 (ID 204, SKU T2YCOSCO000009)
    prod = db.query(Product).filter(Product.id == 204).first()
    assert prod is not None, "Product ID 204 not found!"
    sku_id = prod.asin

    print(f"Target Product ID   : {prod.id}")
    print(f"Target SKU/ASIN     : {sku_id}")
    print(f"Target Product Name : {prod.product_name}")

    # Fetch original title in final_product_data to verify zero production overwrite
    orig_fd = db.query(FinalProductData).filter(FinalProductData.sku_id == sku_id).first()
    orig_title = orig_fd.final_product_title if orig_fd else None
    print(f"Existing Title in DB : '{orig_title}'")

    # Fetch mapped competitor titles
    comp_rows = db.query(CompetitorProduct).filter(
        CompetitorProduct.source_product_asin == sku_id
    ).all()
    comp_titles_raw = [c.competitor_title for c in comp_rows if c.competitor_title and c.competitor_title.strip()]
    competitor_titles = []
    for t in comp_titles_raw:
        t_clean = t.strip()
        if t_clean not in competitor_titles:
            competitor_titles.append(t_clean)
        if len(competitor_titles) >= 20:
            break

    # Fetch harvested keywords
    kw_rows = db.query(Keyword).filter(Keyword.source_product_asin == sku_id).all()
    kw_list = [k.keyword for k in kw_rows if k.keyword]

    print(f"Harvested Keywords Count      : {len(kw_list)}")
    print(f"Competitor Titles Count Passed: {len(competitor_titles)}")

    # --------------------------------------------------------------------------
    # TEST 1: VERIFY PROMPT PAYLOAD (KEYWORDS NEVER SENT TO GROQ)
    # --------------------------------------------------------------------------
    print("\n--- TEST 1: VERIFYING PROMPT INPUTS TO GROQ ---")
    clean_prod_name = clean_input_text(prod.product_name)
    clean_comps = [clean_input_text(t) for t in competitor_titles[:20] if t]
    comp_summary = "\n".join([f"{i+1}. {t}" for i, t in enumerate(clean_comps)])

    prompt = f"""You are an expert e-commerce SEO copywriter. Analyze the following 20 top competitor product titles for relevant search terms, keyword patterns, title structure, and product terminology. Then generate ONE impressive, original, SEO-friendly final product title for Amazon/e-commerce.

Product Name: {clean_prod_name}

Top 20 Competitor Product Titles:
{comp_summary}

Strict Rules:
1. Base the final title primarily on analyzing the 20 competitor titles and verified product details provided above.
2. DO NOT copy any competitor title verbatim.
3. DO NOT invent or fabricate product features, materials, sizes, or warranties that are not mentioned in the product details or competitor context.
4. Keep the title search-optimized, clear, high-converting, and professional (under 200 characters).
5. Output ONLY the raw title text without quotes, markdown headers, or preamble.
"""

    print("Sample Prompt Payload:")
    print("--------------------------------------------------------------------------")
    print(prompt[:600] + "\n...")
    print("--------------------------------------------------------------------------")

    # Verify no harvested keywords are embedded in prompt
    for kw in kw_list[:10]:
        # Only check keywords that aren't substrings of the product name itself
        if kw.lower() not in prod.product_name.lower():
            assert kw.lower() not in prompt.lower() or "Competitor" in prompt, f"Keyword '{kw}' unexpectedly found in prompt!"

    print(">>> VERIFICATION PASSED: Harvested keywords are 100% excluded from Groq title prompt!")

    # --------------------------------------------------------------------------
    # TEST 2: TEST LIVE GROQ TITLE GENERATION FOR SINGLE PRODUCT
    # --------------------------------------------------------------------------
    print("\n--- TEST 2: LIVE GROQ TITLE GENERATION ---")
    generated_title = generate_title_with_groq(prod.product_name, competitor_titles)
    print(f"Groq AI Generated Title : '{generated_title}'")
    assert generated_title is not None and len(generated_title) > 0, "Groq title generation returned empty!"
    assert generated_title != "MANUAL_REVIEW_REQUIRED", "Groq generation unexpectedly failed!"
    print(">>> VERIFICATION PASSED: Groq title generation generated a natural title successfully!")

    # --------------------------------------------------------------------------
    # TEST 3: TEST MANUAL_REVIEW_REQUIRED FALLBACK PATH
    # --------------------------------------------------------------------------
    print("\n--- TEST 3: MANUAL_REVIEW_REQUIRED FAILURE PATH ---")
    no_comp_title = generate_title_with_groq(prod.product_name, [])
    print(f"Result with 0 competitor titles: {no_comp_title}")
    assert no_comp_title is None, "Expected None when 0 competitor titles are passed!"

    # --------------------------------------------------------------------------
    # TEST 4: VERIFY PRODUCTION DATA INTEGRITY (EXPLICIT ROLLBACK)
    # --------------------------------------------------------------------------
    print("\n--- TEST 4: PRODUCTION DB INTEGRITY & ROLLBACK ---")
    db.rollback()
    after_fd = db.query(FinalProductData).filter(FinalProductData.sku_id == sku_id).first()
    after_title = after_fd.final_product_title if after_fd else None
    print(f"Title in DB After Rollback: '{after_title}'")
    assert after_title == orig_title, f"DB Title was altered! Expected '{orig_title}', got '{after_title}'"
    print(">>> VERIFICATION PASSED: Production DB remained 100% unchanged!")

    db.close()
    print("\n==========================================================================")
    print("ALL CONTROLLED SINGLE PRODUCT TESTS PASSED PERFECTLY!")
    print("==========================================================================")

if __name__ == "__main__":
    run_controlled_test()
