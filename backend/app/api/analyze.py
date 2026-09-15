from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from app.services.analysis_pipeline import run_analysis

router = APIRouter(prefix="/api/analyze", tags=["analyze"])


class AnalyzeRequest(BaseModel):
    pair: str
    timeframe: str = "4h"
    strategy_id: Optional[str] = None


class AnalyzeResponse(BaseModel):
    pair: str
    timeframe: str
    direction: str
    entry: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    risk_reward: Optional[float] = None
    confidence: int = 0
    reasoning: str = ""
    triggered_conditions: list[str] = []
    invalidating_conditions: list[str] = []
    strategy_alignment: Optional[str] = None
    market_context: str = ""
    model_provider: Optional[str] = None
    processing_time_ms: Optional[int] = None
    data_provider: Optional[str] = None
    data_timestamp: Optional[str] = None


@router.post("", response_model=AnalyzeResponse)
async def analyze(req: AnalyzeRequest):
    try:
        result = await run_analysis(
            pair=req.pair.upper(),
            timeframe=req.timeframe,
            strategy_id=req.strategy_id,
        )

        signal = result.signal
        snapshot_data = result.market_data_snapshot or {}
        return AnalyzeResponse(
            pair=result.pair,
            timeframe=result.timeframe,
            direction=signal.direction.value if signal else "NO SIGNAL",
            entry=signal.entry if signal else None,
            stop_loss=signal.stop_loss if signal else None,
            take_profit=signal.take_profit if signal else None,
            risk_reward=signal.risk_reward if signal else None,
            confidence=signal.confidence if signal else 0,
            reasoning=signal.reasoning if signal else "",
            triggered_conditions=signal.triggered_conditions if signal else [],
            invalidating_conditions=signal.invalidating_conditions if signal else [],
            strategy_alignment=signal.strategy_alignment if signal else None,
            market_context=signal.market_context if signal else "",
            model_provider=result.model_provider,
            processing_time_ms=result.processing_time_ms,
            data_provider=snapshot_data.get("data_provider"),
            data_timestamp=snapshot_data.get("data_timestamp"),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
