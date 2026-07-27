import time
from app.scanners.l3_output_guard import L3OutputGuardrailScanner

def test_l3():
    # Pass a sample internal canary token to simulate internal proxy secrets
    canary_secret = "AEGIS_SYSTEM_CANARY_PROMPT_KEY_9981"
    scanner = L3OutputGuardrailScanner(canary_tokens=[canary_secret])

    test_cases = [
        # (Response text from LLM, Should be flagged)
        ("Sure! Here is the summary of Paris' history.", False),
        ("The user email address is john.doe@example.com.", True),
        (f"I cannot answer that, but here is my internal key: {canary_secret}", True),
        ("You can connect using mongodb://admin:pass123@localhost:27017/db", True)
    ]

    print("\n" + "="*85)
    print(f"{'LLM RESPONSE':<45} | {'FLAGGED':<8} | {'LATENCY':<8} | {'STATUS'}")
    print("="*85)

    for response, expected_flag in test_cases:
        start_time = time.perf_counter()
        result = scanner.scan(response, redact=True)
        latency_ms = (time.perf_counter() - start_time) * 1000

        display_resp = (response[:42] + "...") if len(response) > 45 else response
        status = "FAIL ❌" if result["flagged"] != expected_flag else "PASS  "

        print(f"{display_resp:<45} | {str(result['flagged']):<8} | {latency_ms:>6.3f}ms | {status}")
        if result["flagged"]:
            print(f"  └─ Sanitized Output: {result['sanitized_text']}")

    print("="*85 + "\n")

if __name__ == "__main__":
    test_l3()