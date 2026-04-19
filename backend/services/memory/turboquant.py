import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

# Try to import torch and pyturboquant, fallback to stubs if not installed
try:
    import torch
    import numpy as np
    from pyturboquant import TurboQuantIndex
    HAS_TURBOQUANT = True
except ImportError:
    HAS_TURBOQUANT = False
    logger.warning("pyturboquant, torch, or numpy not installed. TurboQuantMemoryBackend will run in simulated mode.")

class TurboQuantMemoryBackend:
    """
    Online vector compression backend for embedding stores.
    As per EXTERNAL_TECH.md Phase 1 integration.
    """
    
    def __init__(self, dim: int, bits: int = 4, metric: str = "ip"):
        self.dim = dim
        self.bits = bits
        self.metric = metric
        self.ids: List[str] = []
        self.meta: List[Dict[str, Any]] = []
        
        if HAS_TURBOQUANT:
            self.index = TurboQuantIndex(dim=dim, bits=bits, metric=metric)
        else:
            self.index = None
            self._simulated_store = []

    def add(self, ids: List[str], vectors: 'np.ndarray', metadata: List[Dict[str, Any]]) -> None:
        """Add vectors and their associated metadata to the compressed index."""
        if HAS_TURBOQUANT:
            tensor = torch.tensor(vectors, dtype=torch.float32)
            self.index.add(tensor)
        else:
            self._simulated_store.append((ids, metadata))
            
        self.ids.extend(ids)
        self.meta.extend(metadata)
        logger.debug(f"Added {len(ids)} items to TurboQuant index. Total size: {len(self.ids)}")

    def search(self, query_vector: 'np.ndarray', k: int = 20) -> List[Dict[str, Any]]:
        """Search the compressed index for top-k nearest neighbors."""
        results = []
        
        if HAS_TURBOQUANT:
            q = torch.tensor(query_vector[None, :], dtype=torch.float32)
            distances, indices = self.index.search(q, k=k)
            for score, idx in zip(distances[0].tolist(), indices[0].tolist()):
                if idx >= 0 and idx < len(self.ids):
                    results.append({
                        "id": self.ids[idx],
                        "score": score,
                        "metadata": self.meta[idx],
                    })
        else:
            # Simulated return if library missing
            logger.debug("Simulated hit on TurboQuant index")
            for i, (m_id, m_meta) in enumerate(zip(self.ids, self.meta)):
                if len(results) >= k:
                    break
                results.append({
                    "id": m_id,
                    "score": 0.95 - (i * 0.01),
                    "metadata": m_meta
                })
                
        return results
