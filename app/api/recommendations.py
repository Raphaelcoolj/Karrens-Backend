from fastapi import APIRouter, Query
from typing import Optional
from datetime import datetime
from app.models.recommendation import (
    RecommendationResponse,
    RecommendationsListResponse,
    TopRecommendationResponse,
)
from app.services.recommendation_engine import (
    get_recommendations,
    get_top_recommendation,
    ensure_recommendation_indexes,
)

router = APIRouter(prefix="/api/recommendations", tags=["recommendations"])


@router.on_event("startup")
async def startup_recommendations():
    await ensure_recommendation_indexes()


def _rec_to_response(rec: dict) -> RecommendationResponse:
    return RecommendationResponse(
        id=str(rec.get("_id", "")),
        symbol=rec.get("symbol", ""),
        asset_class=rec.get("asset_class", "unknown"),
        timeframe=rec.get("timeframe", ""),
        direction=rec.get("direction", "NEUTRAL"),
        score=rec.get("score", 0),
        quality=rec.get("quality", "UNKNOWN"),
        status=rec.get("status", "WATCH"),
        trade_status=rec.get("trade_status", "NO_SETUP"),
        entry=rec.get("entry"),
        sl=rec.get("sl"),
        tp=rec.get("tp"),
        rr=rec.get("rr"),
        strategy=rec.get("strategy", "advanced_smc"),
        reasons=rec.get("reasons", []),
        negative_factors=rec.get("negative_factors", []),
        confirmation_state=rec.get("confirmation_state", ""),
        structure_summary=rec.get("structure_summary", ""),
        liquidity_summary=rec.get("liquidity_summary", ""),
        poi_summary=rec.get("poi_summary", ""),
        htf_bias=rec.get("htf_bias", "NEUTRAL"),
        middle_bias=rec.get("middle_bias", "NEUTRAL"),
        ltf_confirmation=rec.get("ltf_confirmation", "NONE"),
        created_at=rec.get("created_at", datetime.utcnow()).isoformat() if isinstance(rec.get("created_at"), datetime) else str(rec.get("created_at", "")),
        updated_at=rec.get("updated_at", datetime.utcnow()).isoformat() if isinstance(rec.get("updated_at"), datetime) else str(rec.get("updated_at", "")),
        expires_at=rec.get("expires_at").isoformat() if isinstance(rec.get("expires_at"), datetime) else None,
    )


@router.get("", response_model=RecommendationsListResponse)
async def list_recommendations(
    limit: int = Query(default=20, ge=1, le=100),
    asset_class: Optional[str] = Query(default=None),
    timeframe: Optional[str] = Query(default=None),
    status: Optional[str] = Query(default=None),
    direction: Optional[str] = Query(default=None),
):
    recs = get_recommendations(limit, asset_class, timeframe, status, direction)
    return RecommendationsListResponse(
        recommendations=[_rec_to_response(r) for r in recs],
        total=len(recs),
        generated_at=datetime.utcnow().isoformat(),
    )


@router.get("/top", response_model=TopRecommendationResponse)
async def top_recommendation():
    rec = get_top_recommendation()
    return TopRecommendationResponse(
        recommendation=_rec_to_response(rec) if rec else None,
        generated_at=datetime.utcnow().isoformat(),
    )
