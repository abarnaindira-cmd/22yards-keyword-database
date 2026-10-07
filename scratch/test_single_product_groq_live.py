from sqlalchemy import text
from app.database import SessionLocal
from app.services.title_generator import process_final_product_data_for_asin

def test_single_product_groq_live():
    db = SessionLocal()
    target_sku = "T2YVIVA000017"

    print("==========================================================================")
    print(f"REQUIREMENT 10: TESTING REAL GROQ API TITLE GENERATION FOR PRODUCT '{target_sku}'")
    print("==========================================================================")

    from app.services.groq_service import get_groq_client
    cli = get_groq_client()
    print(f"Debug: get_groq_client() = {cli}")

    res = process_final_product_data_for_asin(db, target_sku)

    print("Result Dictionary:")
    print(f"  sku_id             : {res.get('sku_id')}")
    print(f"  product_name       : {res.get('product_name')}")
    print(f"  final_product_title: {res.get('final_product_title')}")
    print(f"  generation_method  : {res.get('generation_method')}")
    print(f"  keywords_count     : {res.get('keywords_count')}")

    # Inspect MySQL record
    db_rec = db.execute(text("SELECT product_name, sku_id, final_product_title, all_keywords FROM final_product_data WHERE sku_id = :sku"), {"sku": target_sku}).fetchone()

    print("\nVerified Saved MySQL Record in `final_product_data`:")
    print(f"  product_name       : {db_rec[0]}")
    print(f"  sku_id             : {db_rec[1]}")
    print(f"  final_product_title: {db_rec[2]}")
    print(f"  all_keywords (JSON): {db_rec[3]}")

    assert res.get("generation_method") == "groq", f"Expected generation method 'groq', got '{res.get('generation_method')}'"
    assert db_rec[1] == target_sku
    assert db_rec[2] and len(db_rec[2]) > 0

    db.close()
    print("\n==========================================================================")
    print("REQUIREMENT 10 TEST PASSED 100% SUCCESSFULLY WITH LIVE GROQ API!")
    print("==========================================================================")

if __name__ == "__main__":
    test_single_product_groq_live()
