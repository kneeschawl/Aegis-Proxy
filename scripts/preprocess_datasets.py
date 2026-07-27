import os
import pandas as pd
from pathlib import Path

# Paths relative to project root
BASE_DIR = Path(__file__).resolve().parent.parent
RAW_DIR = BASE_DIR / "data" / "raw"
PROCESSED_DIR = BASE_DIR / "data" / "processed"
PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

def process_jbb() -> pd.DataFrame:
    """JailbreakBench: Harmful behaviors -> Adversarial (label=1)"""
    file_path = RAW_DIR / "jbb_harmful.csv"
    if not file_path.exists():
        print("  ⚠️ JBB harmful dataset missing, skipping...")
        return pd.DataFrame()
    
    df = pd.read_csv(file_path)
    # Target column is usually 'Goal' or 'prompt'
    col_name = 'Goal' if 'Goal' in df.columns else df.columns[0]
    
    clean_df = pd.DataFrame({
        "text": df[col_name].astype(str).str.strip(),
        "label": 1,
        "category": "jailbreak",
        "source": "jbb_harmful"
    })
    return clean_df

def process_adv_glue() -> pd.DataFrame:
    """AdvGLUE: Adversarial text perturbations -> Adversarial (label=1)"""
    file_path = RAW_DIR / "adv_glue_sst2.csv"
    if not file_path.exists():
        print("  ⚠️ AdvGLUE dataset missing, skipping...")
        return pd.DataFrame()

    df = pd.read_csv(file_path)
    col_name = 'sentence' if 'sentence' in df.columns else df.columns[0]

    clean_df = pd.DataFrame({
        "text": df[col_name].astype(str).str.strip(),
        "label": 1,
        "category": "adversarial_perturbation",
        "source": "adv_glue"
    })
    return clean_df

def process_deepset_injections() -> pd.DataFrame:
    """Deepset Prompt Injections -> Mixed (label derived from 'label' column)"""
    file_path = RAW_DIR / "kaggle_injection" / "prompt_injections.csv"
    if not file_path.exists():
        print("  ⚠️ Deepset prompt injections dataset missing, skipping...")
        return pd.DataFrame()

    df = pd.read_csv(file_path)
    text_col = 'text' if 'text' in df.columns else df.columns[0]
    label_col = 'label' if 'label' in df.columns else df.columns[1]

    clean_df = pd.DataFrame({
        "text": df[text_col].astype(str).str.strip(),
        "label": df[label_col].astype(int),
        "category": df[label_col].apply(lambda x: "prompt_injection" if x == 1 else "benign"),
        "source": "deepset_injections"
    })
    return clean_df

def process_alpaca() -> pd.DataFrame:
    """Alpaca Cleaned -> Benign Control (label=0)"""
    file_path = RAW_DIR / "alpaca_cleaned.csv"
    if not file_path.exists():
        print("  ⚠️ Alpaca Cleaned missing, skipping...")
        return pd.DataFrame()

    df = pd.read_csv(file_path)
    
    # Combine instruction and optional input
    def build_text(row):
        inst = str(row.get('instruction', '')).strip()
        inp = str(row.get('input', '')).strip()
        return f"{inst}\n{inp}".strip() if inp else inst

    texts = df.apply(build_text, axis=1)
    
    clean_df = pd.DataFrame({
        "text": texts,
        "label": 0,
        "category": "benign_instruction",
        "source": "alpaca_cleaned"
    })
    return clean_df

def process_ultrachat() -> pd.DataFrame:
    """UltraChat Sample -> Benign Control (label=0)"""
    file_path = RAW_DIR / "ultrachat_sample.csv"
    if not file_path.exists():
        print("  ⚠️ UltraChat sample missing, skipping...")
        return pd.DataFrame()

    df = pd.read_csv(file_path)
    
    # Extract first user message or prompt string
    col_name = 'prompt' if 'prompt' in df.columns else df.columns[0]
    
    clean_df = pd.DataFrame({
        "text": df[col_name].astype(str).str.strip(),
        "label": 0,
        "category": "benign_conversation",
        "source": "ultrachat_200k"
    })
    return clean_df

def preprocess_all():
    print("--- Processing and Normalizing Raw Datasets ---")
    
    dfs = [
        process_jbb(),
        process_adv_glue(),
        process_deepset_injections(),
        process_alpaca(),
        process_ultrachat()
    ]
    
    # Combine all valid DataFrames
    valid_dfs = [d for d in dfs if not d.empty]
    combined_df = pd.concat(valid_dfs, ignore_index=True)
    
    # Remove empty strings and nulls
    combined_df = combined_df[combined_df["text"].str.len() > 3].dropna(subset=["text"])
    
    # Deduplicate prompts
    before_count = len(combined_df)
    combined_df.drop_duplicates(subset=["text"], keep="first", inplace=True)
    after_count = len(combined_df)
    
    print(f"\n✓ Processed {after_count} total entries (Removed {before_count - after_count} duplicates).")
    
    # Print label distribution
    distribution = combined_df["label"].value_counts().to_dict()
    print(f"  Distribution -> Benign (0): {distribution.get(0, 0)} | Adversarial (1): {distribution.get(1, 0)}")

    # Save complete merged set
    combined_path = PROCESSED_DIR / "aegis_dataset_full.csv"
    combined_df.to_csv(combined_path, index=False)
    print(f"  ✓ Full merged dataset saved to `{combined_path.resolve()}`")

    # Extract adversarial-only subset for L1 Vector Cache
    adversarial_df = combined_df[combined_df["label"] == 1]
    l1_cache_path = PROCESSED_DIR / "l1_signatures.csv"
    adversarial_df.to_csv(l1_cache_path, index=False)
    print(f"  ✓ L1 Signature Cache subset ({len(adversarial_df)} rows) saved to `{l1_cache_path.resolve()}`")

if __name__ == "__main__":
    preprocess_all()