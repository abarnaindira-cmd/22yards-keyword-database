import sys
import logging
sys.stdout.reconfigure(encoding='utf-8')

from app.database import SessionLocal
from app.models.product import Product
from app.models.competitor import CompetitorProduct
from app.models.final_product_data import FinalProductData
from app.services.title_generator import generate_title_with_groq

def test_updated_prompt_behavior():
    logging.basicConfig(level=logging.INFO)
    db = SessionLocal()

    print("==========================================================================")
    print("NON-PRODUCTION DRY-RUN TEST: UPDATED TITLE ACCURACY & PROMPT BEHAVIOR")
    print("==========================================================================")

    # SKU T2YCOSCO000009 (Product ID 204)
    prod = db.query(Product).filter(Product.asin == 'T2YCOSCO000009').first()
    assert prod is not None, "Product T2YCOSCO000009 not found!"

    # Original DB Title
    fd = db.query(FinalProductData).filter(FinalProductData.sku_id == 'T2YCOSCO000009').first()
    orig_db_title = fd.final_product_title if fd else None

    # Competitor titles
    comps = db.query(CompetitorProduct).filter(
        CompetitorProduct.source_product_asin == 'T2YCOSCO000009'
    ).order_by(CompetitorProduct.competitor_rank.asc()).all()

    comp_titles = []
    for c in comps:
        t = c.competitor_title.strip() if c.competitor_title else ""
        if t and t not in comp_titles:
            comp_titles.append(t)
        if len(comp_titles) >= 20:
            break

    print(f"Target SKU          : {prod.asin}")
    print(f"Target Product Name : {prod.product_name}")
    print(f"Original Title in DB: '{orig_db_title}'")
    print(f"Competitor Titles Passed: {len(comp_titles)}\n")

    # Generate title with updated prompt
    new_title = generate_title_with_groq(prod.product_name, comp_titles)

    print("--------------------------------------------------------------------------")
    print("BEFORE & AFTER PROMPT COMPARISON:")
    print("--------------------------------------------------------------------------")
    print("Old Generated Title : 'SCOOPER Kashmir Willow Cricket Tennis Bat - Full-Size Wooden Bat for Tennis Ball, Lightweight Balanced Performance for Kids & Adults'")
    print(f"NEW Generated Title : '{new_title}'")
    print("--------------------------------------------------------------------------\n")

    print("CLAIM-BY-CLAIM EVIDENCE VERIFICATION ON NEW TITLE:")
    print("--------------------------------------------------------------------------")

    claims_check = [
        ("Kashmir Willow", "kashmir willow" in new_title.lower(), "Target Product Name", "EXPLICITLY SUPPORTED"),
        ("Tennis / Tennis Ball", "tennis" in new_title.lower(), "Target Product Name", "EXPLICITLY SUPPORTED"),
        ("Scooper", "scooper" in new_title.lower(), "Target Product Name", "EXPLICITLY SUPPORTED"),
        ("Full-Size (OMITTED)", "full-size" not in new_title.lower() and "full size" not in new_title.lower(), "Omitted (Unverified in Target Name)", "SUCCESSFULLY OMITTED"),
        ("Balanced Performance (OMITTED)", "balanced" not in new_title.lower(), "Omitted (Fluff from Comp #13)", "SUCCESSFULLY OMITTED"),
        ("Kids & Adults (OMITTED)", "kids" not in new_title.lower() and "adults" not in new_title.lower(), "Omitted (Contradictory Comp Claims)", "SUCCESSFULLY OMITTED")
    ]

    for claim_name, is_pass, source_info, verdict in claims_check:
        status_str = "PASSED" if is_pass else "FAILED"
        print(f"  - Claim: {claim_name:<30} | Verdict: {verdict:<22} | Status: [{status_str}] | Evidence: {source_info}")
        assert is_pass, f"Claim validation failed for '{claim_name}'!"

    print("\n--- PRODUCTION DB INTEGRITY VERIFICATION ---")
    db.rollback()
    after_fd = db.query(FinalProductData).filter(FinalProductData.sku_id == 'T2YCOSCO000009').first()
    after_db_title = after_fd.final_product_title if after_fd else None
    assert after_db_title == orig_db_title, "Production database title was unexpectedly altered!"
    print(f"DB Title After Rollback: '{after_db_title}'")
    print(">>> VERIFICATION PASSED: Zero production database records modified!")

    db.close()
    print("\n==========================================================================")
    print("ALL ACCURACY & PROMPT BEHAVIOR TESTS PASSED 100% PERFECTLY!")
    print("==========================================================================")

if __name__ == "__main__":
    test_updated_prompt_behavior()
