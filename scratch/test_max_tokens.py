from app.services.groq_service import get_groq_client

client = get_groq_client()

prompt = "Product Name: VIVA Sport One Color Swimming Cap\nKeywords: swimming cap, swimming cap for women\nGenerate a concise product title for Amazon."

for max_t in [150, 300, 600]:
    print(f"\n--- Testing max_tokens={max_t} ---")
    res = client.chat.completions.create(
        model="openai/gpt-oss-120b",
        messages=[
            {"role": "user", "content": prompt}
        ],
        max_tokens=max_t
    )
    msg = res.choices[0].message
    print("Choice message keys/attrs:", dir(msg))
    print("Content:", repr(msg.content))
    if hasattr(msg, 'reasoning'):
        print("Reasoning:", repr(getattr(msg, 'reasoning')))
