import pandas as pd
from pathlib import Path
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct
from sentence_transformers import SentenceTransformer
import time

BASE_DIR = Path(__file__).resolve().parent.parent
SIGNATURES_FILE = BASE_DIR / "data" / "processed" / "l1_signatures.csv"
COLLECTION_NAME = "aegis_l1_signatures"
EMBEDDING_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"

def main():
    if not SIGNATURES_FILE.exists():
        raise FileNotFoundError(f"Signatures file missing at `{SIGNATURES_FILE}`. Run `preprocess_datasets.py` first.")

    print(f"--- Loading Signatures Dataset from `{SIGNATURES_FILE.name}` ---")
    df = pd.read_csv(SIGNATURES_FILE)
    print(f"  ✓ Loaded {len(df)} signature records.")

    print(f"\n--- Loading Embedding Model ({EMBEDDING_MODEL_NAME}) ---")
    model = SentenceTransformer(EMBEDDING_MODEL_NAME)
    
    # Initialize Qdrant client (localhost)
    client = QdrantClient(host="localhost", port=6333)

    # Re-create collection
    print(f"\n--- Preparing Qdrant Collection: `{COLLECTION_NAME}` ---")
    if client.collection_exists(COLLECTION_NAME):
        client.delete_collection(COLLECTION_NAME)
        print("  ✓ Removed existing collection.")

    client.create_collection(
        collection_name=COLLECTION_NAME,
        vectors_config=VectorParams(size=384, distance=Distance.COSINE),
    )
    print("  ✓ Created new Qdrant vector collection.")

    # Compute Embeddings
    print("\n--- Generating Embeddings ---")
    start_time = time.time()
    prompts = df["text"].tolist()
    embeddings = model.encode(prompts, show_progress_bar=True, batch_size=64)
    duration = time.time() - start_time
    print(f"  ✓ Embedded {len(prompts)} vectors in {duration:.2f} seconds.")

    # Build Qdrant Point Payload
    print("\n--- Uploading Points to Qdrant ---")
    points = []
    for idx, (row, vector) in enumerate(zip(df.itertuples(), embeddings)):
        points.append(
            PointStruct(
                id=idx,
                vector=vector.tolist(),
                payload={
                    "text": row.text,
                    "category": getattr(row, "category", "malicious"),
                    "source": getattr(row, "source", "unknown"),
                    "label": int(getattr(row, "label", 1)),
                }
            )
        )

    # Batch upsert
    client.upsert(collection_name=COLLECTION_NAME, points=points)
    print(f"  ✓ Indexed {len(points)} threat signatures into Qdrant successfully.")

if __name__ == "__main__":
    main()