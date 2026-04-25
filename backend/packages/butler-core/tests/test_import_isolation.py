"""Test that butler-core does not import heavy ML dependencies."""

import sys


def test_butler_core_imports_no_torch():
    """Test that importing butler-core does not import torch."""
    # Clear any previous imports
    for module in list(sys.modules.keys()):
        if "torch" in module:
            del sys.modules[module]

    # Import butler-core
    from butler_core.ml.embeddings import EmbeddingProvider
    from butler_core.ml.routing import RoutingDecision, RoutingResult
    from butler_core.ml.semantic_router import SemanticEmbeddingRouter

    # Verify torch is not imported
    assert "torch" not in sys.modules, "torch should not be imported when importing butler-core"


def test_butler_core_imports_no_sentence_transformers():
    """Test that importing butler-core does not import sentence_transformers."""
    # Clear any previous imports
    for module in list(sys.modules.keys()):
        if "sentence_transformers" in module:
            del sys.modules[module]

    # Import butler-core
    from butler_core.ml.embeddings import EmbeddingProvider
    from butler_core.ml.routing import RoutingDecision, RoutingResult
    from butler_core.ml.semantic_router import SemanticEmbeddingRouter

    # Verify sentence_transformers is not imported
    assert "sentence_transformers" not in sys.modules, "sentence_transformers should not be imported when importing butler-core"


def test_butler_core_imports_no_onnxruntime():
    """Test that importing butler-core does not import onnxruntime."""
    # Clear any previous imports
    for module in list(sys.modules.keys()):
        if "onnxruntime" in module:
            del sys.modules[module]

    # Import butler-core
    from butler_core.ml.embeddings import EmbeddingProvider
    from butler_core.ml.routing import RoutingDecision, RoutingResult
    from butler_core.ml.semantic_router import SemanticEmbeddingRouter

    # Verify onnxruntime is not imported
    assert "onnxruntime" not in sys.modules, "onnxruntime should not be imported when importing butler-core"
