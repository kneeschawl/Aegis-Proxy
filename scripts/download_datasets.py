import os
from pathlib import Path
from datasets import load_dataset
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Resolves project root directory dynamically (aegis-proxy/)
BASE_DIR = Path(__file__).resolve().parent.parent
RAW_DATA_DIR = BASE_DIR / "data" / "raw"
RAW_DATA_DIR.mkdir(parents=True, exist_ok=True)

def download_hf_datasets():
    print("--- Fetching Hugging Face Datasets ---")
    
    # 1. JailbreakBench (JBB-Behaviors)
    print("[1/4] Downloading JailbreakBench (JBB-Behaviors)...")
    try:
        # Config name is 'behaviors', split is 'harmful'
        jbb = load_dataset("JailbreakBench/JBB-Behaviors", "behaviors", split="harmful")
        jbb.to_csv(RAW_DATA_DIR / "jbb_harmful.csv")
        print("  ✓ JBB-Behaviors saved.")
    except Exception as e:
        print(f"  ✕ Failed JBB download: {e}")

    # 2. AdvGLUE Benchmark
    print("[2/4] Downloading AdvGLUE...")
    try:
        # Config name is 'adv_sst2'
        adv_glue = load_dataset("AI-Secure/adv_glue", "adv_sst2", split="validation")
        adv_glue.to_csv(RAW_DATA_DIR / "adv_glue_sst2.csv")
        print("  ✓ AdvGLUE saved.")
    except Exception as e:
        print(f"  ✕ Failed AdvGLUE download: {e}")

    # 3. Benign Control 1: Alpaca Cleaned
    print("[3/4] Downloading Alpaca Cleaned (Benign)...")
    try:
        alpaca = load_dataset("yahma/alpaca-cleaned", split="train")
        alpaca.to_csv(RAW_DATA_DIR / "alpaca_cleaned.csv")
        print("  ✓ Alpaca Cleaned saved.")
    except Exception as e:
        print(f"  ✕ Failed Alpaca download: {e}")

    # 4. Benign Control 2: UltraChat 200k (Open Benign Conversations)
    print("[4/4] Downloading UltraChat 200k (Open Benign Sample)...")
    try:
        # Replaces gated LMSYS with open conversational benchmark
        ultrachat = load_dataset("HuggingFaceH4/ultrachat_200k", split="train_sft[:5000]")
        ultrachat.to_csv(RAW_DATA_DIR / "ultrachat_sample.csv")
        print("  ✓ UltraChat sample saved.")
    except Exception as e:
        print(f"  ✕ Failed UltraChat download: {e}")

def download_extra_injections():
    print("\n--- Fetching Deepset Prompt Injections ---")
    try:
        injection_target = RAW_DATA_DIR / "kaggle_injection"
        injection_target.mkdir(exist_ok=True)
        
        deepset_ds = load_dataset("deepset/prompt-injections", split="train")
        deepset_ds.to_csv(injection_target / "prompt_injections.csv")
        print("  ✓ Deepset prompt injection dataset saved successfully.")
    except Exception as e:
        print(f"  ✕ Failed Deepset download: {e}")

if __name__ == "__main__":
    download_hf_datasets()
    download_extra_injections()
    print(f"\n✓ Data pipeline ingestion complete. Files stored in `{RAW_DATA_DIR.resolve()}`")