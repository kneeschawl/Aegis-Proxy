import re
import math
from typing import Dict, Any, List

class L1HeuristicScanner:
    """
    Layer 1 Scanner: Fast (<1ms) deterministic security checks.
    Includes regex pattern matching for prompt injections and high-entropy secret detection.
    """
    def __init__(self):
        # High-risk prompt injection keywords and jailbreak patterns
        self.injection_patterns = [
            r"(?i)ignore\s+(all\s+)?(previous|prior)\s+instructions?",
            r"(?i)disregard\s+(all\s+)?(previous|prior)\s+(rules|instructions)",
            r"(?i)system\s*override",
            r"(?i)developer\s*mode\s*activated",
            r"(?i)you\s+are\s+now\s+(unrestricted|free|DAN|jailbroken)",
            r"(?i)print\s+(the\s+)?(system\s+prompt|internal\s+instructions)",
            r"(?i)reveal\s+(your\s+)?(system\s+prompt|instructions|secret\s+key)",
            r"(?i)do\s+anything\s+now",
        ]
        
        # Secret / Canary token detection patterns (API Keys, Bearer Tokens, Private Keys)
        self.secret_patterns = {
            "openai_api_key": r"sk-(proj-|admin-|user-)?[a-zA-Z0-9_\-]{20,}",
            "generic_api_key": r"(?i)(api_key|access_token|secret_key)\s*[:=]\s*['\"]?[a-zA-Z0-9_\-]{16,}['\"]?",
            "pem_private_key": r"-----BEGIN\s+(RSA|EC|PRIVATE)\s+KEY-----",
            "bearer_token": r"(?i)bearer\s+[a-zA-Z0-9\-\._~\+\/]+=*",
            "aws_access_key": r"(A3T[A-Z0-9]|AKIA|AGPA|AIDA|AROA|AIPA|ANPA|ANVA|ASIA)[A-Z0-9]{16}"
        }

        # Compile regexes for maximum execution speed
        self.compiled_injections = [re.compile(p) for p in self.injection_patterns]
        self.compiled_secrets = {k: re.compile(v) for k, v in self.secret_patterns.items()}

    def calculate_entropy(self, text: str) -> float:
        """Calculates Shannon entropy to detect random or encoded string payloads."""
        if not text:
            return 0.0
        prob = [float(text.count(c)) / len(text) for c in set(text)]
        return -sum([p * math.log(p, 2) for p in prob])

    def scan(self, prompt: str) -> Dict[str, Any]:
        """
        Scans a prompt against L1 heuristic rules.
        Returns a dict indicating whether the prompt is flagged, the reason, and latency.
        """
        # Check 1: Prompt Injection / Jailbreak Patterns
        for pattern in self.compiled_injections:
            match = pattern.search(prompt)
            if match:
                return {
                    "flagged": True,
                    "reason": f"L1: Prompt Injection Pattern Detected ('{match.group(0)}')",
                    "action": "BLOCK",
                    "rule": "INJECTION_PATTERN"
                }

        # Check 2: Embedded Secrets or Credentials
        for secret_type, pattern in self.compiled_secrets.items():
            if pattern.search(prompt):
                return {
                    "flagged": True,
                    "reason": f"L1: Credential Leak Detected ({secret_type})",
                    "action": "BLOCK",
                    "rule": "SECRET_LEAK"
                }

        # Check 3: Exceptionally High Entropy (Detects obfuscated Base64 / Hex payloads)
        # Only check strings long enough to avoid false positives
        if len(prompt) > 80 and self.calculate_entropy(prompt) > 5.8:
            return {
                "flagged": True,
                "reason": "L1: Suspicious High-Entropy String (Possible Obfuscated Payload)",
                "action": "BLOCK",
                "rule": "HIGH_ENTROPY"
            }

        return {
            "flagged": False,
            "reason": "L1 Check Passed",
            "action": "PASS",
            "rule": "CLEAN"
        }