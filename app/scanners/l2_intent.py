import time
import numpy as np
from pathlib import Path
from typing import Dict, Any
import onnxruntime as ort
from transformers import AutoTokenizer

class L2IntentScanner:
    def __init__(
        self,
        model_dir: str = "./models/l2_deberta_v3",
        threshold: float = 0.70
    ):
        self.base_path = Path(model_dir)
        self.threshold = threshold

        # Load Tokenizer
        tokenizer_path = self.base_path / "tokenizer"
        if not tokenizer_path.exists():
            raise FileNotFoundError(f"Tokenizer missing at {tokenizer_path}")
        self.tokenizer = AutoTokenizer.from_pretrained(str(tokenizer_path))

        # Load Quantized ONNX Session
        onnx_path = self.base_path / "aegis_l2_classifier_quant.onnx"
        if not onnx_path.exists():
            # Fall back to standard ONNX model if quantized isn't available yet
            onnx_path = self.base_path / "aegis_l2_classifier.onnx"
            if not onnx_path.exists():
                raise FileNotFoundError(f"ONNX model missing at {onnx_path}")

        # Configure CPU session with optimization
        opts = ort.SessionOptions()
        opts.intra_op_num_threads = 4
        opts.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
        opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL

        self.session = ort.InferenceSession(str(onnx_path), opts, providers=["CPUExecutionProvider"])
        self._warmup()

    def _warmup(self):
        """Warm up ONNX engine to avoid cold-start penalties."""
        dummy_inputs = self.tokenizer("Warmup check", return_tensors="np", truncation=True, max_length=128)
        _ = self.session.run(None, {
            "input_ids": dummy_inputs["input_ids"],
            "attention_mask": dummy_inputs["attention_mask"]
        })

    def scan_prompt(self, prompt: str) -> Dict[str, Any]:
        """
        Runs INT8 ONNX sequence classification on the prompt.
        Target execution latency: <35ms.
        """
        start_time = time.perf_counter()

        # 1. Tokenize
        inputs = self.tokenizer(
            prompt,
            return_tensors="np",
            truncation=True,
            max_length=256,
            padding=False
        )

        # 2. Run ONNX Inference
        ort_inputs = {
            "input_ids": inputs["input_ids"].astype(np.int64),
            "attention_mask": inputs["attention_mask"].astype(np.int64)
        }
        logits = self.session.run(None, ort_inputs)[0]

        # 3. Softmax activation to convert logits to probabilities
        exp_logits = np.exp(logits - np.max(logits, axis=-1, keepdims=True))
        probs = exp_logits / np.sum(exp_logits, axis=-1, keepdims=True)
        
        malicious_prob = float(probs[0][1])  # Class 1 = Malicious / Adversarial
        latency_ms = (time.perf_counter() - start_time) * 1000

        is_blocked = malicious_prob >= self.threshold

        return {
            "is_blocked": is_blocked,
            "scanner": "L2_Intent_Classifier",
            "score": round(malicious_prob, 4),
            "threshold": self.threshold,
            "latency_ms": round(latency_ms, 2)
        }