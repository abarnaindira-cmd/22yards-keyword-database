import os
from app.services.groq_service import get_groq_client

client = get_groq_client()
print("Client:", client)
if client:
    try:
        models = client.models.list()
        print("Available Groq Models:")
        for m in models.data:
            print(f" - {m.id}")
    except Exception as e:
        print("Error listing models:", type(e), e)

    test_models = ["llama-3.3-70b-versatile", "llama-3.1-8b-instant", "llama3-70b-8192", "mixtral-8x7b-32768", "gemma2-9b-it", "openai/gpt-oss-120b"]
    for m in test_models:
        try:
            res = client.chat.completions.create(
                model=m,
                messages=[{"role": "user", "content": "Hello"}],
                max_tokens=10
            )
            print(f"SUCCESS with model '{m}':", res.choices[0].message.content)
            break
        except Exception as e:
            print(f"FAILED with model '{m}':", type(e), e)
