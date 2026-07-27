import time
import numpy as np
from pathlib import Path
from typing import Dict, Any, List, Optional
import onnxruntime as ort
from transformers import AutoTokenizer

from app.scanners.l1_heuristics import L1HeuristicScanner
from app.scanners.l3_output_guard import L3OutputGuardrailScanner

class AegisPipeline:
    """
    Unified Security Pipeline for Aegis Proxy.
    Sequentially handles L1 (Heuristics) -> L2 (DistilBERT ONNX) -> L3 (Output Guardrails).
    """
    def __init__(
        self,
        l2_model_dir: str = "./models/l2_intent_model",
        canary_tokens: Optional[List[str]] = None,
        l2_confidence_threshold: float = 0.85
    ):
        self.l2_threshold = l2_confidence_threshold
        
        # 1. Initialize Layer 1 Scanner
        print("--- Initializing L1 Heuristics Engine ---")
        self.l1_scanner = L1HeuristicScanner()

        # 2. Initialize Layer 2 ONNX Scanner
        print("--- Initializing L2 DistilBERT ONNX Engine ---")
        model_path = Path(l2_model_dir) / "aegis_l2_classifier_quant.onnx"
        tok_path = Path(l2_model_dir) / "tokenizer"

        if not model_path.exists() or not tok_path.exists():
            raise FileNotFoundError(f"❌ L2 Model/Tokenizer missing in {l2_model_dir}")

        self.tokenizer = AutoTokenizer.from_pretrained(tok_path)
        
        opts = ort.SessionOptions()
        opts.intra_op_num_threads = 2
        opts.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
        opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        
        self.l2_session = ort.InferenceSession(str(model_path), opts, providers=["CPUExecutionProvider"])

        # 3. Initialize Layer 3 Scanner
        print("--- Initializing L3 Output Guardrail Engine ---")
        self.l3_scanner = L3OutputGuardrailScanner(canary_tokens=canary_tokens or [])

    def _softmax(self, logits: np.ndarray) -> np.ndarray:
        exp_logits = np.exp(logits - np.max(logits, axis=-1, keepdims=True))
        return exp_logits / np.sum(exp_logits, axis=-1, keepdims=True)

    def scan_input(self, prompt: str) -> Dict[str, Any]:
        """
        Runs input security checks (L1 -> L2).
        Returns action "PASS" or "BLOCK" with metadata and latency.
        """
        overall_start = time.perf_counter()

        # ------------------- LAYER 1 SCAN -------------------
        l1_start = time.perf_counter()
        l1_res = self.l1_scanner.scan(prompt)
        l1_time = (time.perf_counter() - l1_start) * 1000

        if l1_res["flagged"]:
            total_time = (time.perf_counter() - overall_start) * 1000
            return {
                "action": "BLOCK",
                "blocked_by": "L1_HEURISTICS",
                "reason": l1_res["reason"],
                "l1_latency_ms": l1_time,
                "l2_latency_ms": 0.0,
                "total_latency_ms": total_time,
                "confidence": 1.0
            }

        # ------------------- LAYER 2 SCAN -------------------
        l2_start = time.perf_counter()
        inputs = self.tokenizer(
            prompt,
            truncation=True,
            max_length=256,
            padding=True,
            return_tensors="np"
        )
        
        onnx_inputs = {
            "input_ids": inputs["input_ids"].astype(np.int64),
            "attention_mask": inputs["attention_mask"].astype(np.int64)
        }

        outputs = self.l2_session.run(None, onnx_inputs)
        probs = self._softmax(outputs[0])[0]
        predicted_class = int(np.argmax(probs))
        confidence = float(probs[predicted_class])
        l2_time = (time.perf_counter() - l2_start) * 1000

        total_time = (time.perf_counter() - overall_start) * 1000

        # Class 1 = Malicious / Injection
        if predicted_class == 1 and confidence >= self.l2_threshold:
            return {
                "action": "BLOCK",
                "blocked_by": "L2_DISTILBERT",
                "reason": f"L2 Intent Detection Triggered (Confidence: {confidence*100:.1f}%)",
                "l1_latency_ms": l1_time,
                "l2_latency_ms": l2_time,
                "total_latency_ms": total_time,
                "confidence": confidence
            }

        # Clean Request
        return {
            "action": "PASS",
            "blocked_by": None,
            "reason": "Input Passed All Security Layers",
            "l1_latency_ms": l1_time,
            "l2_latency_ms": l2_time,
            "total_latency_ms": total_time,
            "confidence": confidence
        }

    def scan_output(self, response_text: str, redact: bool = True) -> Dict[str, Any]:
        """Runs L3 output checks on LLM completions."""
        start_time = time.perf_counter()
        l3_res = self.l3_scanner.scan(response_text, redact=redact)
        l3_time = (time.perf_counter() - start_time) * 1000

        l3_res["latency_ms"] = l3_time
        return l3_res