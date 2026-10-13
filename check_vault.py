import sys
from core.vault import get_secret

def main():
    print(f"Running check_vault.py with interpreter: {sys.executable}")
    secrets_to_check = ["gemini_api_key", "openai_api_key"]
    
    for secret in secrets_to_check:
        # We suppress the warning logger for check_vault
        val = get_secret(secret)
        if val:
            print(f"{secret}: PRESENT")
        else:
            print(f"{secret}: MISSING")

if __name__ == "__main__":
    main()
