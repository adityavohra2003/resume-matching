import os
from typing import List

from sentence_transformers import SentenceTransformer

_model = None

def get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        name = os.getenv("EMBEDDING_MODEL_NAME", "all-MiniLM-L6-v2")
        _model = SentenceTransformer(name)
    return _model

def embed_text(text: str) -> List[float]:
    model = get_model()
    vec = model.encode(text, normalize_embeddings=True)
    return vec.tolist()
