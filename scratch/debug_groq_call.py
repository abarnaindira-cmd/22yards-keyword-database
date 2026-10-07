import traceback
from app.services.groq_service import get_groq_client
from app.services.title_generator import clean_input_text, clean_generated_title

client = get_groq_client()
print("Client:", client)

product_name = "VIVA Sport One Color Swimming Cap"
keywords = ["swimming cap", "swimming cap for women", "swimming caps for men"]
competitor_titles = ["Speedo Unisex Swimming Cap", "Adidas Silicone Swim Cap"]

clean_prod_name = clean_input_text(product_name)
clean_kws = [clean_input_text(k) for k in keywords[:10] if k]
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

models_to_try = ["openai/gpt-oss-120b", "openai/gpt-oss-20b", "qwen/qwen3.8-27b"]

for model_name in models_to_try:
    print(f"\n--- Testing model: {model_name} ---")
    try:
        completion = client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": "You generate concise, compliant e-commerce product titles."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            max_tokens=150
        )
        raw_content = completion.choices[0].message.content or ""
        print("Raw Content:", repr(raw_content))
        cleaned = clean_generated_title(raw_content)
        print("Cleaned Content:", repr(cleaned))
        if cleaned:
            print(f"SUCCESS with {model_name}: {cleaned}")
            break
    except Exception as e:
        print("EXCEPTION:", type(e), e)
        traceback.print_exc()
