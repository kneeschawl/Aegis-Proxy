import re
from typing import Dict, Any, List

class L3OutputGuardrailScanner:
    """
    Layer 3 Scanner: Output Verification Guardrail.
    Inspects LLM outputs to detect and redact/block:
    1. Canary/Secret Leaks (API keys, System Prompts, Database URIs)
    2. PII (Emails, Credit Cards, US SSNs, Phone Numbers)
    """
    def __init__(self, canary_tokens: List[str] = None):
        # Canary tokens are system-specific secrets you pass in to prevent leakage
        self.canary_tokens = canary_tokens or []

        # Common PII & Credential Leak Regex Patterns
        self.output_patterns = {
            "email": r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}",
            "credit_card": r"\b(?:\d[ -]*?){13,16}\b",
            "us_ssn": r"\b\d{3}-\d{2}-\d{4}\b",
            "phone_number": r"\b(?:\+?1[-. ]?)?\(?([0-9]{3})\)?[-. ]?([0-9]{3})[-. ]?([0-9]{4})\b",
            "openai_key": r"sk-(proj-|admin-|user-)?[a-zA-Z0-9_\-]{20,}",
            "database_connection_uri": r"(?i)(postgres|mongodb|mysql|redis):\/\/[^\s]+"
        }

        self.compiled_patterns = {k: re.compile(v) for k, v in self.output_patterns.items()}

    def scan(self, response_text: str, redact: bool = True) -> Dict[str, Any]:
        """
        Scans the LLM output for leaks.
        If redact=True, returns sanitized_text with sensitive fields replaced with [REDACTED].
        """
        sanitized_text = response_text
        detected_leaks = []

        # Check 1: Custom Canary Token Leak Detection
        for canary in self.canary_tokens:
            if canary and canary in response_text:
                detected_leaks.append("CANARY_LEAK")
                if redact:
                    sanitized_text = sanitized_text.replace(canary, "[REDACTED_SYSTEM_CANARY]")

        # Check 2: PII and Credential Patterns
        for leak_type, pattern in self.compiled_patterns.items():
            if pattern.search(sanitized_text):
                detected_leaks.append(leak_type.upper())
                if redact:
                    sanitized_text = pattern.sub(f"[REDACTED_{leak_type.upper()}]", sanitized_text)

        if detected_leaks:
            return {
                "flagged": True,
                "action": "REDACT" if redact else "BLOCK",
                "detected_leaks": list(set(detected_leaks)),
                "sanitized_text": sanitized_text,
                "reason": f"L3 Guard Triggered: Detected {', '.join(set(detected_leaks))}"
            }

        return {
            "flagged": False,
            "action": "PASS",
            "detected_leaks": [],
            "sanitized_text": response_text,
            "reason": "L3 Output Verification Passed"
        }