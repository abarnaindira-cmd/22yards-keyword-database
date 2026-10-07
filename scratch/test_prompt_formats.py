import sys
sys.stdout.reconfigure(encoding='utf-8')

from app.services.groq_service import get_groq_client

client = get_groq_client()

prompt = "Product Name: VIVA Sport One Color Swimming Cap\nKeywords: swimming cap, swimming cap for women\nGenerate a concise product title for Amazon."

# Test 1: system + user
print("--- Test 1: system + user ---")
res1 = client.chat.completions.create(
    model="openai/gpt-oss-120b",
    messages=[
        {"role": "system", "content": "You generate concise e-commerce product titles."},
        {"role": "user", "content": prompt}
    ]
)
print("Test 1 raw:", repr(res1.choices[0].message.content))

# Test 2: user only
print("--- Test 2: user only ---")
res2 = client.chat.completions.create(
    model="openai/gpt-oss-120b",
    messages=[
        {"role": "user", "content": prompt}
    ]
)
print("Test 2 raw:", repr(res2.choices[0].message.content))

# Test 3: qwen/qwen3.8-27b
print("--- Test 3: qwen/qwen3.8-27b ---")
res3 = client.chat.completions.create(
    model="qwen/qwen3.8-27b",
    messages=[
        {"role": "user", "content": prompt}
    ]
)
print("Test 3 raw:", repr(res3.choices[0].message.content))
