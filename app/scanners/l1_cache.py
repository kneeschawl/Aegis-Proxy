import time
from typing import Dict, Any
from qdrant_client import QdrantClient
from sentence_transformers import SentenceTransformer

class L1VectorCacheScanner:
    def __init__(
        self, 
        host: str = "localhost", 
        port: int = 6333, 
        collection_name: str = "aegis_l1_signatures",
        similarity_threshold: float = 0.78  # Calibrated for semantic match range
    ):
        self.client = QdrantClient(host=host, port=port)
        self.collection_name = collection_name
        self.similarity_threshold = similarity_threshold
        
        # Load lightweight CPU embedding model & warm up
        self.model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
        self._warmup()

    def _warmup(self):
        """Warm up model weights to eliminate cold-start latency spikes."""
        _ = self.model.encode("warmup prompt", convert_to_tensor=False)

    def scan_prompt(self, prompt: str) -> Dict[str, Any]:
        """
        Embeds incoming prompt and queries Qdrant L1 cache using query_points.
        Target execution latency: <15ms.
        """
        start_time = time.perf_counter()
        
        # 1. Generate query vector
        query_vector = self.model.encode(prompt, convert_to_tensor=False).tolist()
        
        # 2. Query Qdrant using query_points API
        response = self.client.query_points(
            collection_name=self.collection_name,
            query=query_vector,
            limit=1
        )

        latency_ms = (time.perf_counter() - start_time) * 1000
        points = response.points

        if points:
            top_match = points[0]
            score = top_match.score
            
            if score >= self.similarity_threshold:
                return {
                    "is_blocked": True,
                    "scanner": "L1_Vector_Cache",
                    "score": round(float(score), 4),
                    "threshold": self.similarity_threshold,
                    "matched_category": top_match.payload.get("category", "unknown"),
                    "matched_source": top_match.payload.get("source", "unknown"),
                    "matched_signature": top_match.payload.get("text", "")[:100],
                    "latency_ms": round(latency_ms, 2)
                }

        return {
            "is_blocked": False,
            "scanner": "L1_Vector_Cache",
            "score": round(float(points[0].score), 4) if points else 0.0,
            "threshold": self.similarity_threshold,
            "latency_ms": round(latency_ms, 2)
        }