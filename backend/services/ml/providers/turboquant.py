"""TurboQuant Memory Backend Integration.

Phase F.2: TurboQuant integration for compressed recall tier.
Uses real pyturboquant library for vector quantization and search.
"""

import logging
from typing import Any

try:
    from pyturboquant.search import TurboQuantIndex
    from pyturboquant.core import mse_quantize, mse_dequantize, ip_quantize, estimate_inner_product
    PYTURBOQUANT_AVAILABLE = True
except ImportError:
    PYTURBOQUANT_AVAILABLE = False

logger = logging.getLogger(__name__)


class TurboQuantBackend:
    """TurboQuant backend for compressed memory recall using pyturboquant.

    This backend:
    - Uses pyturboquant for MSE-optimal vector quantization
    - Provides inner-product preserving quantization for search
    - Zero-indexing-time ANN search with TurboQuantIndex
    - Integrates with tier reconciliation for cold storage
    """

    def __init__(self, config: dict[str, Any] | None = None):
        """Initialize TurboQuant backend.

        Args:
            config: TurboQuant configuration (dim, bits, metric, search_batch_size, etc.)
        """
        self._config = config or {}
        self._dim = self._config.get("dim", 768)
        self._bits = self._config.get("bits", 4)
        self._metric = self._config.get("metric", "ip")
        self._seed = self._config.get("seed", 42)
        self._search_batch_size = self._config.get("search_batch_size", 65536)

        if not PYTURBOQUANT_AVAILABLE:
            logger.warning("pyturboquant_not_installed: Install with: pip install pyturboquant")
            self._index = None
        else:
            try:
                self._index = TurboQuantIndex(
                    dim=self._dim,
                    bits=self._bits,
                    metric=self._metric,
                    seed=self._seed,
                )
                logger.info(f"turboquant_index_created: dim={self._dim}, bits={self._bits}")
            except Exception as e:
                logger.error(f"turboquant_index_creation_failed: {e}")
                self._index = None

    async def initialize(self) -> None:
        """Initialize TurboQuant backend."""
        if not PYTURBOQUANT_AVAILABLE:
            logger.warning("turboquant_unavailable: Install pyturboquant to enable vector quantization")
            return

        if self._index is None:
            logger.warning("turboquant_index_not_initialized")
            return

        logger.info(f"turboquant_initialized: config={self._config}")

    async def add_vectors(self, vectors: list[list[float]]) -> None:
        """Add vectors to the TurboQuant index.

        Args:
            vectors: List of embedding vectors to add
        """
        if not PYTURBOQUANT_AVAILABLE or self._index is None:
            logger.warning("turboquant_unavailable for add_vectors")
            return

        try:
            import torch
            import numpy as np

            # Convert to torch tensor
            tensor = torch.tensor(np.array(vectors), dtype=torch.float32)
            self._index.add(tensor)
            logger.info(f"turboquant_vectors_added: count={len(vectors)}")
        except Exception as e:
            logger.error(f"turboquant_add_failed: {e}")

    async def search(self, query_vector: list[float], k: int = 10) -> tuple[list[float], list[int]]:
        """Search for nearest neighbors.

        Args:
            query_vector: Query embedding vector
            k: Number of results to return

        Returns:
            Tuple of (distances, indices)
        """
        if not PYTURBOQUANT_AVAILABLE or self._index is None:
            logger.warning("turboquant_unavailable for search")
            return [], []

        try:
            import torch
            import numpy as np

            # Convert to torch tensor
            query = torch.tensor(np.array([query_vector]), dtype=torch.float32)
            distances, indices = self._index.search(query, k=k)
            
            # Convert to Python lists
            distances_list = distances[0].tolist()
            indices_list = indices[0].tolist()
            
            logger.info(f"turboquant_search_complete: k={k}, results={len(indices_list)}")
            return distances_list, indices_list
        except Exception as e:
            logger.error(f"turboquant_search_failed: {e}")
            return [], []

    async def compress_vector(self, vector: list[float]) -> bytes:
        """Compress a single vector using MSE quantization.

        Args:
            vector: Vector to compress

        Returns:
            Quantized vector as bytes
        """
        if not PYTURBOQUANT_AVAILABLE:
            logger.warning("turboquant_unavailable for compress_vector")
            return b""

        try:
            import torch
            import numpy as np

            # Convert to torch tensor
            tensor = torch.tensor(np.array([vector]), dtype=torch.float32)
            
            # MSE-optimal quantization
            quantized = mse_quantize(tensor, bits=self._bits, seed=self._seed)
            
            # Serialize quantized representation
            import pickle
            return pickle.dumps(quantized)
        except Exception as e:
            logger.error(f"turboquant_compress_failed: {e}")
            return b""

    async def decompress_vector(self, compressed: bytes) -> list[float]:
        """Decompress a quantized vector.

        Args:
            compressed: Compressed vector bytes

        Returns:
            Decompressed vector
        """
        if not PYTURBOQUANT_AVAILABLE:
            logger.warning("turboquant_unavailable for decompress_vector")
            return []

        try:
            import pickle
            quantized = pickle.loads(compressed)
            
            # Dequantize
            reconstructed = mse_dequantize(quantized)
            
            # Convert to Python list
            return reconstructed[0].tolist()
        except Exception as e:
            logger.error(f"turboquant_decompress_failed: {e}")
            return []

    async def save_index(self, path: str) -> None:
        """Save the TurboQuant index to disk.

        Args:
            path: Path to save the index
        """
        if not PYTURBOQUANT_AVAILABLE or self._index is None:
            logger.warning("turboquant_unavailable for save_index")
            return

        try:
            self._index.save(path)
            logger.info(f"turboquant_index_saved: path={path}")
        except Exception as e:
            logger.error(f"turboquant_save_failed: {e}")

    async def load_index(self, path: str) -> None:
        """Load the TurboQuant index from disk.

        Args:
            path: Path to load the index from
        """
        if not PYTURBOQUANT_AVAILABLE:
            logger.warning("turboquant_unavailable for load_index")
            return

        try:
            self._index = TurboQuantIndex.load(path)
            logger.info(f"turboquant_index_loaded: path={path}")
        except Exception as e:
            logger.error(f"turboquant_load_failed: {e}")

    @property
    def memory_usage_mb(self) -> float:
        """Get current memory usage in MB."""
        if not PYTURBOQUANT_AVAILABLE or self._index is None:
            return 0.0
        return self._index.memory_usage_mb

    @property
    def ntotal(self) -> int:
        """Get total number of vectors in the index."""
        if not PYTURBOQUANT_AVAILABLE or self._index is None:
            return 0
        return self._index.ntotal
