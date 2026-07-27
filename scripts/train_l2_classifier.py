import os
import torch
import numpy as np
import pandas as pd
from pathlib import Path
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, precision_recall_fscore_support
from transformers import (
    AutoTokenizer, 
    AutoModelForSequenceClassification, 
    Trainer, 
    TrainingArguments,
    DataCollatorWithPadding
)
import onnxruntime as ort

# Model configuration
MODEL_NAME = "microsoft/deberta-v3-small"
OUTPUT_DIR = Path("./models/l2_deberta_v3")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

ONNX_MODEL_PATH = OUTPUT_DIR / "aegis_l2_classifier.onnx"
QUANT_ONNX_PATH = OUTPUT_DIR / "aegis_l2_classifier_quant.onnx"

class AegisDataset(torch.utils.data.Dataset):
    def __init__(self, encodings, labels):
        self.encodings = encodings
        self.labels = labels

    def __getitem__(self, idx):
        item = {key: torch.tensor(val[idx]) for key, val in self.encodings.items()}
        item['labels'] = torch.tensor(self.labels[idx])
        return item

    def __len__(self):
        return len(self.labels)

def compute_metrics(eval_pred):
    logits, labels = eval_pred
    predictions = np.argmax(logits, axis=-1)
    precision, recall, f1, _ = precision_recall_fscore_support(labels, predictions, average='binary')
    acc = accuracy_score(labels, predictions)
    return {"accuracy": acc, "f1": f1, "precision": precision, "recall": recall}

def train_and_export():
    print(f"--- Loading Dataset for Fine-Tuning ---")
    data_path = Path("./data/processed/aegis_dataset_full.csv")
    if not data_path.exists():
        raise FileNotFoundError(f"Missing processed dataset at {data_path}")

    df = pd.read_csv(data_path)
    print(f"Total dataset size: {len(df)} rows")

    # Split train/validation (80/20)
    train_texts, val_texts, train_labels, val_labels = train_test_split(
        df["text"].tolist(), 
        df["label"].tolist(), 
        test_size=0.2, 
        random_state=42, 
        stratify=df["label"]
    )

    print(f"Tokenizer & Model Setup: {MODEL_NAME}")
    tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
    model = AutoModelForSequenceClassification.from_pretrained(MODEL_NAME, num_labels=2)

    train_encodings = tokenizer(train_texts, truncation=True, max_length=256)
    val_encodings = tokenizer(val_texts, truncation=True, max_length=256)

    train_dataset = AegisDataset(train_encodings, train_labels)
    val_dataset = AegisDataset(val_encodings, val_labels)

    training_args = TrainingArguments(
        output_dir=str(OUTPUT_DIR / "checkpoints"),
        num_train_epochs=3,
        per_device_train_batch_size=16,
        per_device_eval_batch_size=32,
        warmup_ratio=0.1,
        weight_decay=0.01,
        logging_steps=50,
        evaluation_strategy="epoch",
        save_strategy="epoch",
        load_best_model_at_end=True,
        metric_for_best_model="f1",
        fp16=torch.cuda.is_available(),
        report_to="none"
    )

    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=train_dataset,
        eval_dataset=val_dataset,
        tokenizer=tokenizer,
        data_collator=DataCollatorWithPadding(tokenizer=tokenizer),
        compute_metrics=compute_metrics
    )

    print("\n--- Starting Model Training ---")
    trainer.train()

    # Save tokenizer and PyTorch model weights
    model.save_pretrained(OUTPUT_DIR / "pytorch_model")
    tokenizer.save_pretrained(OUTPUT_DIR / "tokenizer")
    print("  ✓ PyTorch checkpoint saved successfully.")

    # Export to ONNX
    print("\n--- Exporting Model to ONNX Format ---")
    model.eval()
    dummy_input = tokenizer("Sample prompt to trace ONNX graph", return_tensors="pt", max_length=256, padding="max_length")
    
    torch.onnx.export(
        model,
        (dummy_input["input_ids"], dummy_input["attention_mask"]),
        str(ONNX_MODEL_PATH),
        input_names=["input_ids", "attention_mask"],
        output_names=["logits"],
        dynamic_axes={
            "input_ids": {0: "batch_size", 1: "sequence_length"},
            "attention_mask": {0: "batch_size", 1: "sequence_length"},
            "logits": {0: "batch_size"}
        },
        opset_version=14
    )
    print(f"  ✓ Exported ONNX model to `{ONNX_MODEL_PATH}`")

    # Dynamic INT8 Quantization for Fast CPU Execution
    print("\n--- Quantizing ONNX Model (INT8 for Low CPU Latency) ---")
    from onnxruntime.quantization import quantize_dynamic, QuantType
    
    quantize_dynamic(
        model_input=str(ONNX_MODEL_PATH),
        model_output=str(QUANT_ONNX_PATH),
        weight_type=QuantType.QUInt8
    )
    print(f"  ✓ Quantized ONNX model saved to `{QUANT_ONNX_PATH}`")

if __name__ == "__main__":
    train_and_export()