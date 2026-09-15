from fastapi import APIRouter, HTTPException
from app.services.market_data import MarketDataService

router = APIRouter(prefix="/api/markets", tags=["markets"])
market_service = MarketDataService()


@router.get("/search")
async def search_pairs(q: str = ""):
    if not q:
        return []
    try:
        results = await market_service.search_pairs(q)
        return [r.model_dump() for r in results]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{symbol}")
async def get_ticker(symbol: str):
    try:
        ticker = await market_service.get_ticker(symbol.upper())
        return ticker.model_dump()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{symbol}/data")
async def get_market_data(symbol: str, interval: str = "4h", limit: int = 200):
    try:
        snapshot = await market_service.get_full_market_data(
            symbol.upper(), interval, limit
        )
        return snapshot.model_dump()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
