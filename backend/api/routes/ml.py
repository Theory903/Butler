from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel
from typing import List, Optional, Any, Dict
from domain.auth.contracts import AccountContext
from api.routes.gateway import get_current_account
from core.deps import get_db, get_cache, get_ml_runtime, get_feature_service
from services.ml import MLService
from domain.ml.contracts import RetrievalCandidate

async def get_ml_service(cache=Depends(get_cache)) -> MLService:
    from services.ml.embeddings import EmbeddingService
    from services.ml.intent import IntentClassifier
    from services.ml.ranking import HeavyRanker # Restored
    from services.ml.runtime import MLRuntimeManager
    from services.ml.registry import ModelRegistry
    from services.ml.features import FeatureService
    from services.ml.mixer import CandidateMixer, SignalManager
    from services.ml.admin import MLAdmin
    
    runtime = get_ml_runtime()
    classifier = IntentClassifier(runtime=runtime)
    embedder = EmbeddingService()
    registry = ModelRegistry()
    features = get_feature_service(redis=cache)
    
    # HeavyRanker handles high-fidelity scoring with behavioral signals
    ranking = HeavyRanker(registry=registry, feature_service=features)
    
    mixer = CandidateMixer()
    signals = SignalManager(feature_svc=features)
    admin_svc = MLAdmin()
    
    return MLService(
        classifier, embedder, registry, runtime, 
        ranking, features, mixer, signals, admin_svc
    )

router = APIRouter(prefix="/ml", tags=["ml"])

# ── Schemas ───────────────────────────────────────────────────────────────────

class ClassifyRequest(BaseModel):
    text: str

class EmbedRequest(BaseModel):
    text: str

class RerankRequest(BaseModel):
    query: str
    candidates: List[RetrievalCandidate]

class MixRequest(BaseModel):
    query: str
    entity_id: str
    limit: Optional[int] = 10

class AdminFlagRequest(BaseModel):
    name: str
    value: Any

# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/intent/classify")
async def classify_intent(
    req: ClassifyRequest, 
    account: AccountContext = Depends(get_current_account),
    svc: MLService = Depends(get_ml_service)
):
    """Rich intent classification with entity extraction and tiering."""
    res = await svc.classify_intent(req.text)
    return {
        "label": res.label,
        "confidence": res.confidence,
        "tier": res.tier,
        "complexity": res.complexity,
        "entities": res.entities,
        "requires_tools": res.requires_tools,
        "requires_memory": res.requires_memory,
        "requires_clarification": res.requires_clarification
    }

@router.post("/embed")
async def embed_text(
    req: EmbedRequest,
    account: AccountContext = Depends(get_current_account),
    svc: MLService = Depends(get_ml_service)
):
    """Dense embeddings using BGE-family models (1024-d)."""
    emb = await svc.embed(req.text)
    return {"vector": emb, "dimensions": len(emb), "model": "bge-large-en-v1.5"}

@router.post("/mix")
async def mix_and_rank(
    req: MixRequest,
    account: AccountContext = Depends(get_current_account),
    svc: MLService = Depends(get_ml_service)
):
    """Twitter-style pipeline: Federated Retrieval -> Heavy Ranking."""
    results = await svc.mix_and_rank(req.query, req.entity_id, req.limit)
    return {"results": [r.model_dump() for r in results]}

@router.post("/rerank")
async def rerank_candidates(
    req: RerankRequest,
    account: AccountContext = Depends(get_current_account),
    svc: MLService = Depends(get_ml_service)
):
    """High-precision Cross-Encoder reranking."""
    results = await svc.rerank(req.query, req.candidates)
    return {"results": [r.model_dump() for r in results]}

@router.get("/features/online")
async def get_online_features(
    entity_id: str,
    features: List[str] = Query(...),
    account: AccountContext = Depends(get_current_account),
    svc: MLService = Depends(get_ml_service)
):
    """Fetch rich RIO signals for ranking/personalization."""
    vector = await svc.get_features(entity_id, features)
    return vector.model_dump() if vector else None

@router.get("/models")
async def list_models(
    account: AccountContext = Depends(get_current_account),
    svc: MLService = Depends(get_ml_service)
):
    """List registered models with rollout and health status."""
    return svc.list_models()

@router.get("/admin/stats")
async def get_admin_stats(
    account: AccountContext = Depends(get_current_account),
    svc: MLService = Depends(get_ml_service)
):
    """Get ML Platform administrative stats and flag states."""
    return svc.get_admin_stats()

@router.post("/admin/flags")
async def set_admin_flag(
    req: AdminFlagRequest,
    account: AccountContext = Depends(get_current_account),
    svc: MLService = Depends(get_ml_service)
):
    """Set a runtime administrative flag (Dynamic Toggle)."""
    svc.set_admin_flag(req.name, req.value)
    return {"status": "ok", "flag": req.name, "value": req.value}

@router.get("/health")
async def ml_health(svc: MLService = Depends(get_ml_service)):
    """Deep ML Platform health probe (v3.0 RIO)."""
    registry = ModelRegistry()
    probe = HealthProbe(registry=registry)
    return await probe.check_readiness()
