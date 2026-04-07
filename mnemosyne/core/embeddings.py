"""
Mnemosyne Dense Retrieval
Local embedding-based memory retrieval using fastembed (ONNX, no PyTorch).
Falls back to keyword-only if fastembed is unavailable.
"""

import json
import numpy as np
from typing import List, Optional

# Optional dependency
try:
    from fastembed import TextEmbedding
    _FASTEMBED_AVAILABLE = True
except Exception:
    _FASTEMBED_AVAILABLE = False
    TextEmbedding = None

_DEFAULT_MODEL = "BAAI/bge-small-en-v1.5"
_embedding_model = None


def _get_model() -> Optional[TextEmbedding]:
    """Lazy-load the embedding model."""
    global _embedding_model
    if not _FASTEMBED_AVAILABLE:
        return None
    if _embedding_model is None:
        _embedding_model = TextEmbedding(model_name=_DEFAULT_MODEL)
    return _embedding_model


def available() -> bool:
    """Check if dense retrieval is available."""
    return _FASTEMBED_AVAILABLE and _get_model() is not None


def embed(texts: List[str]) -> Optional[np.ndarray]:
    """
    Encode texts into dense vectors.
    
    Args:
        texts: List of strings to encode
        
    Returns:
        Numpy array of shape (n_texts, embedding_dim) or None if unavailable
    """
    model = _get_model()
    if model is None or not texts:
        return None
    # fastembed.embed returns a generator of numpy arrays
    vectors = list(model.embed(texts))
    return np.stack(vectors).astype(np.float32)


def cosine_similarity(query_vec: np.ndarray, doc_vecs: np.ndarray) -> np.ndarray:
    """
    Compute cosine similarity between query and documents.
    
    Args:
        query_vec: shape (dim,)
        doc_vecs: shape (n_docs, dim)
        
    Returns:
        similarities: shape (n_docs,)
    """
    query_norm = query_vec / (np.linalg.norm(query_vec) + 1e-10)
    docs_norm = doc_vecs / (np.linalg.norm(doc_vecs, axis=1, keepdims=True) + 1e-10)
    return docs_norm @ query_norm


def serialize(vec: np.ndarray) -> str:
    """Serialize embedding to JSON string."""
    return json.dumps(vec.tolist())


def deserialize(text: str) -> Optional[np.ndarray]:
    """Deserialize embedding from JSON string."""
    if not text:
        return None
    return np.array(json.loads(text), dtype=np.float32)
