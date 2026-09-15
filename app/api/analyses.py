from fastapi import APIRouter, HTTPException
from typing import Optional
from app.core.database import get_db
from bson import ObjectId

router = APIRouter(prefix="/api/analyses", tags=["analyses"])


def serialize_doc(doc):
    if doc is None:
        return None
    doc["id"] = str(doc.pop("_id"))
    return doc


@router.get("")
async def list_analyses(
    pair: Optional[str] = None,
    timeframe: Optional[str] = None,
    limit: int = 50,
    skip: int = 0,
):
    db = get_db()
    query = {}
    if pair:
        query["pair"] = pair.upper()
    if timeframe:
        query["timeframe"] = timeframe

    cursor = db.analyses.find(query).sort("timestamp", -1).skip(skip).limit(limit)
    docs = await cursor.to_list(length=limit)
    return [serialize_doc(d) for d in docs]


@router.get("/{analysis_id}")
async def get_analysis(analysis_id: str):
    db = get_db()
    doc = await db.analyses.find_one({"_id": ObjectId(analysis_id)})
    if not doc:
        raise HTTPException(status_code=404, detail="Analysis not found")
    return serialize_doc(doc)
