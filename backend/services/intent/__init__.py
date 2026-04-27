"""Intent building service for Butler.

Pre-retrieval layer that normalizes user input and extracts intent context
before tool retrieval.
"""

from services.intent.intent_builder import IntentBuilder, IntentContext, IntentConstraints

__all__ = ["IntentBuilder", "IntentContext", "IntentConstraints"]
