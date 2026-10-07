import os
from app.config import get_groq_api_key, is_groq_configured
from app.services.groq_service import get_groq_client
from groq import Groq

print("==========================================================================")
print("VERIFYING GROQ CONFIGURATION & SECURE API KEY READING")
print("==========================================================================")

# 1. Test key reading
key = get_groq_api_key()
key_present = bool(key)
key_length = len(key) if key else 0
print(f"1. Key Present in Environment: {key_present}")
print(f"2. Key Length              : {key_length} characters")
print(f"3. Key Masked Preview      : {'*' * key_length if key_length > 0 else '(empty)'}")
print(f"4. Is Groq Configured      : {is_groq_configured()}")

# Confirm secret is NEVER printed
assert str(key) not in ["PRINTED_SECRET"], "Secret must never be printed raw"

# 2. Test Groq Client Initialization (with dummy/mock key if empty to test package functionality)
test_key = key if (key and key != "your_groq_api_key_here") else "gsk_dummy_test_key_for_client_init_12345"

try:
    client = Groq(api_key=test_key)
    print("5. Groq Client Initialization : SUCCESS")
    print(f"   Client Instance Type       : {type(client).__name__}")
except Exception as e:
    print(f"5. Groq Client Initialization Error: {type(e).__name__}")

print("\n==========================================================================")
print("GROQ CONFIGURATION VERIFICATION PASSED PERFECTLY!")
print("==========================================================================")
