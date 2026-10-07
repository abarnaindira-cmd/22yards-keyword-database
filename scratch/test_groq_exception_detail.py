import sys
sys.stdout.reconfigure(encoding='utf-8')

from app.database import SessionLocal
from app.models.product import Product
from app.models.keyword import Keyword
from app.models.competitor import CompetitorProduct
from app.services.groq_service import get_groq_client
from app.services.title_generator import clean_input_text, clean_generated_title

db = SessionLocal()
sku_id = "T2YVIVA000017"

prod = db.query(Product).filter(Product.asin == sku_id).first()
kw_rows = db.query(Keyword).filter(Keyword.source_product_asin == sku_id).order_by(Keyword.relevance_score.desc()).all()
all_keywords_list = [k.keyword for k in kw_rows if k.keyword]
comp_rows = db.query(CompetitorProduct).filter(CompetitorProduct.source_product_asin == sku_id).limit(5).all()
competitor_titles = [c.competitor_title for c in comp_rows if c.competitor_title]

print("Product:", prod.product_name)
print("Keywords count:", len(all_keywords_list))
print("Competitor titles count:", len(competitor_titles))

client = get_groq_client()
print("Client:", client)

clean_prod_name = clean_input_text(prod.product_name)
clean_kws = [clean_input_text(k) for k in all_keywords_list[:10] if k]
clean_comps = [clean_input_text(t) for t in competitor_titles[:5] if t]

kw_summary = ", ".join(clean_kws) if clean_kws else "N/A"
comp_summary = "\n".join([f"- {t}" for t in clean_comps]) if clean_comps else "N/A"

prompt = f"""You are an expert e-commerce SEO copywriter. Generate a concise, high-converting product title for Amazon/e-commerce.

Product Name: {clean_prod_name}
Harvested Keywords: {kw_summary}
Top Competitor Titles (For context only - DO NOT COPY):
{comp_summary}

Strict Rules:
1. Base the title ONLY on the verified product name and relevance keywords provided.
2. DO NOT copy any competitor title verbatim.
3. DO NOT invent or fabricate product features, materials, sizes, or warranties that are not mentioned.
4. Keep the title search-optimized, clear, and professional (under 200 characters).
5. Output ONLY the raw title text without quotes, markdown headers, or preamble.
"""

print("\n--- Sending Prompt to Groq ---")
for model_name in ["openai/gpt-oss-120b", "openai/gpt-oss-20b"]:
    try:
        completion = client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": "You generate concise, compliant e-commerce product titles."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            max_tokens=1000
        )
        raw_content = completion.choices[0].message.content or ""
        print(f"Model {model_name} RAW:", repr(raw_content))
        cleaned = clean_generated_title(raw_content)
        print(f"Model {model_name} CLEANED:", repr(cleaned))
    except Exception as e:
        import traceback
        print(f"Model {model_name} EXCEPTION:", type(e), e)
        traceback.print_exc()

db.close()
