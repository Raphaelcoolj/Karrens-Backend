from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from datetime import datetime

from app.strategies.swing_smc import SwingSMCStrategy, SwingSMCConfig, Candle
from app.services.market_data import MarketDataService

router = APIRouter(prefix="/api/analysis/swing-smc", tags=["swing-smc"])
market_service = MarketDataService()


class SwingSMCRequest(BaseModel):
    symbol: str
    htf: str = "1D"
    structure_timeframe: str = "4H"
    entry_timeframe: str = "1H"


class EntryZone(BaseModel):
    low: Optional[float] = None
    high: Optional[float] = None


class TakeProfits(BaseModel):
    tp1: Optional[float] = None
    tp2: Optional[float] = None
    tp3: Optional[float] = None


class StructureInfo(BaseModel):
    bos: Optional[str] = None
    choch: Optional[str] = None


class LiquidityInfo(BaseModel):
    sweep: Optional[str] = None
    levels_detected: int = 0
    levels_swept: int = 0


class FVGInfo(BaseModel):
    direction: Optional[str] = None
    low: Optional[float] = None
    high: Optional[float] = None
    filled: bool = False


class OrderBlockInfo(BaseModel):
    direction: Optional[str] = None
    low: Optional[float] = None
    high: Optional[float] = None
    mitigated: bool = False


class SwingSMCResponse(BaseModel):
    symbol: str
    strategy: str
    market_bias: str
    signal: str
    confidence: float
    entry: EntryZone
    stop_loss: Optional[float] = None
    take_profit: TakeProfits
    risk_reward: Optional[float] = None
    structure: StructureInfo
    liquidity: LiquidityInfo
    fvg: Optional[FVGInfo] = None
    order_block: Optional[OrderBlockInfo] = None
    reasons: list[str]
    invalidation_conditions: list[str]
    current_price: Optional[float] = None
    data_provider: Optional[str] = None


def _interval_to_td(interval: str) -> str:
    mapping = {
        "1m": "1min",
        "5m": "5min",
        "15m": "15min",
        "30m": "30min",
        "1h": "1h",
        "4h": "4h",
        "1d": "1day",
        "1w": "1week",
    }
    return mapping.get(interval.lower(), interval)


@router.post("", response_model=SwingSMCResponse)
async def analyze_swing_smc(req: SwingSMCRequest):
    try:
        config = SwingSMCConfig(
            htf=req.htf,
            structure_tf=req.structure_timeframe,
            entry_tf=req.entry_timeframe,
        )

        if not config.is_valid_combo():
            raise HTTPException(
                status_code=400,
                detail=f"Invalid timeframe combination: {req.htf}/{req.structure_timeframe}/{req.entry_timeframe}. "
                       f"Valid combos: 1D/4H/1H, 4H/1H/15m, 1W/1D/4H",
            )

        interval_map = {
            "1D": "1day",
            "4H": "4h",
            "1H": "1h",
            "1W": "1week",
            "15m": "15min",
        }

        td_interval = interval_map.get(config.structure_tf, "4h")

        snapshot = await market_service.get_full_market_data(
            req.symbol.upper(), td_interval, 200
        )

        if not snapshot.candles:
            raise HTTPException(status_code=404, detail=f"No candle data for {req.symbol}")

        candles = [
            Candle(
                timestamp=c.timestamp,
                open=c.open,
                high=c.high,
                low=c.low,
                close=c.close,
                volume=c.volume,
            )
            for c in snapshot.candles
        ]

        strategy = SwingSMCStrategy(config)
        result = strategy.analyze(candles)

        current_price = candles[-1].close if candles else 0

        bos_events = [e for e in result.structure_events if e.type == "BOS"]
        choch_events = [e for e in result.structure_events if e.type == "CHOCH"]

        bos_dir = bos_events[-1].direction if bos_events else None
        choch_dir = choch_events[-1].direction if choch_events else None

        swept = [l for l in result.liquidity_levels if l.swept]
        sweep_dir = None
        if swept:
            last_sweep = swept[-1]
            if last_sweep.type in ("EQUAL_LOW", "PREVIOUS_LOW", "SWING_LOW"):
                sweep_dir = "BULLISH"
            elif last_sweep.type in ("EQUAL_HIGH", "PREVIOUS_HIGH", "SWING_HIGH"):
                sweep_dir = "BEARISH"

        fvg_info = None
        if result.fvg:
            fvg_info = FVGInfo(
                direction=result.fvg.direction,
                low=result.fvg.low,
                high=result.fvg.high,
                filled=result.fvg.filled,
            )

        ob_info = None
        if result.order_block:
            ob_info = OrderBlockInfo(
                direction=result.order_block.direction,
                low=result.order_block.low,
                high=result.order_block.high,
                mitigated=result.order_block.mitigated,
            )

        return SwingSMCResponse(
            symbol=req.symbol.upper(),
            strategy="swing_smc",
            market_bias=result.market_bias,
            signal=result.direction,
            confidence=result.confidence,
            entry=EntryZone(low=result.entry_low, high=result.entry_high),
            stop_loss=result.stop_loss,
            take_profit=TakeProfits(
                tp1=result.take_profit_1,
                tp2=result.take_profit_2,
                tp3=result.take_profit_3,
            ),
            risk_reward=result.risk_reward,
            structure=StructureInfo(bos=bos_dir, choch=choch_dir),
            liquidity=LiquidityInfo(
                sweep=sweep_dir,
                levels_detected=len(result.liquidity_levels),
                levels_swept=len(swept),
            ),
            fvg=fvg_info,
            order_block=ob_info,
            reasons=result.reasons,
            invalidation_conditions=result.invalidation_conditions,
            current_price=current_price,
            data_provider=snapshot.data_provider,
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")
