from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

from app.strategies.advanced_smc import AdvancedSMCStrategy, AdvancedSMCConfig, Candle
from app.services.market_data import MarketDataService

router = APIRouter(prefix="/api/analysis/advanced-smc", tags=["advanced-smc"])
market_service = MarketDataService()


class AdvancedSMCRequest(BaseModel):
    symbol: str
    htf: str = "1D"
    middle_tf: str = "15m"
    ltf: str = "1m"
    exit_mode: str = "CONSERVATIVE"


class StructureInfo(BaseModel):
    state: str = ""
    bos: list[dict] = []
    choch: list[dict] = []
    idm: list[dict] = []


class LiquidityInfo(BaseModel):
    levels_detected: int = 0
    levels_swept: int = 0
    sweep: Optional[str] = None


class POIInfo(BaseModel):
    type: str = ""
    zone: Optional[dict] = None


class EntryInfo(BaseModel):
    type: str = ""
    scheme: str = ""
    low: Optional[float] = None
    high: Optional[float] = None


class RiskInfo(BaseModel):
    stop_loss: Optional[float] = None
    take_profit_1: Optional[float] = None
    take_profit_2: Optional[float] = None
    take_profit_3: Optional[float] = None
    risk_reward: Optional[float] = None


class AdvancedSMCResponse(BaseModel):
    symbol: str
    strategy: str
    bias: str
    signal: str
    confidence: float
    structure: StructureInfo
    liquidity: LiquidityInfo
    poi: POIInfo
    entry: EntryInfo
    risk: RiskInfo
    reasons: list[str]
    invalidation_conditions: list[str]
    current_price: Optional[float] = None


@router.post("", response_model=AdvancedSMCResponse)
async def analyze_advanced_smc(req: AdvancedSMCRequest):
    try:
        config = AdvancedSMCConfig(
            htf=req.htf,
            middle_tf=req.middle_tf,
            ltf=req.ltf,
            exit_mode=req.exit_mode,
        )

        if not config.is_valid_combo():
            raise HTTPException(
                status_code=400,
                detail=f"Invalid timeframe combination: {req.htf}/{req.middle_tf}/{req.ltf}",
            )

        interval_map = {
            "1D": "1day", "4H": "4h", "1H": "1h",
            "1W": "1week", "15m": "15min", "1m": "1min", "5m": "5min",
        }

        td_interval = interval_map.get(config.middle_tf, "4h")

        snapshot = await market_service.get_full_market_data(
            req.symbol.upper(), td_interval, 200
        )

        if not snapshot.candles:
            raise HTTPException(status_code=404, detail=f"No candle data for {req.symbol}")

        candles = [
            Candle(
                timestamp=c.timestamp, open=c.open, high=c.high,
                low=c.low, close=c.close, volume=c.volume,
            )
            for c in snapshot.candles
        ]

        strategy = AdvancedSMCStrategy(config)
        result = strategy.analyze(candles)
        result.symbol = req.symbol.upper()

        current_price = candles[-1].close if candles else 0

        bos_list = [
            {"direction": e.direction, "price": e.price, "index": e.index, "swept": e.swept}
            for e in result.bos_events
        ]
        choch_list = [
            {"direction": e.direction, "price": e.price, "index": e.index, "swept": e.swept}
            for e in result.choch_events
        ]
        idm_list = [
            {"price": i.price, "direction": i.direction, "swept": i.swept, "index": i.index}
            for i in result.idm_events
        ]

        swept = [l for l in result.liquidity_levels if l.swept]
        sweep_dir = None
        if swept:
            last = swept[-1]
            if last.type in ("EQUAL_LOW", "PDL", "ASIAN_LOW", "LONDON_LOW", "NY_LOW", "SWING_LOW"):
                sweep_dir = "BULLISH"
            elif last.type in ("EQUAL_HIGH", "PDH", "ASIAN_HIGH", "LONDON_HIGH", "NY_HIGH", "SWING_HIGH"):
                sweep_dir = "BEARISH"

        poi_zone = None
        if result.poi_zone:
            poi_zone = {
                "type": result.poi_zone.type,
                "high": result.poi_zone.high,
                "low": result.poi_zone.low,
                "reason": result.poi_zone.reason,
            }

        return AdvancedSMCResponse(
            symbol=result.symbol,
            strategy="advanced_smc",
            bias=result.market_bias,
            signal=result.direction,
            confidence=result.confidence,
            structure=StructureInfo(
                state=result.structure_state,
                bos=bos_list,
                choch=choch_list,
                idm=idm_list,
            ),
            liquidity=LiquidityInfo(
                levels_detected=len(result.liquidity_levels),
                levels_swept=len(swept),
                sweep=sweep_dir,
            ),
            poi=POIInfo(type=result.poi_type, zone=poi_zone),
            entry=EntryInfo(
                type=result.entry_type,
                scheme=result.entry_scheme,
                low=result.entry_low,
                high=result.entry_high,
            ),
            risk=RiskInfo(
                stop_loss=result.stop_loss,
                take_profit_1=result.take_profit_1,
                take_profit_2=result.take_profit_2,
                take_profit_3=result.take_profit_3,
                risk_reward=result.risk_reward,
            ),
            reasons=result.reasons,
            invalidation_conditions=result.invalidation_conditions,
            current_price=current_price,
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")
