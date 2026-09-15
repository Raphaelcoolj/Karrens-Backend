from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
import tempfile
import os
from app.core.database import get_db
from app.strategies.ingestion import process_strategy, extract_text
from app.models.strategy import StrategyDocument, StrategyRules, StrategyStatus
from bson import ObjectId

router = APIRouter(prefix="/api/strategies", tags=["strategies"])


def serialize_doc(doc):
    if doc is None:
        return None
    doc["id"] = str(doc.pop("_id"))
    return doc


@router.get("")
async def list_strategies():
    db = get_db()
    cursor = db.strategies.find().sort("created_at", -1)
    docs = await cursor.to_list(length=50)
    return [serialize_doc(d) for d in docs]


@router.get("/{strategy_id}")
async def get_strategy(strategy_id: str):
    db = get_db()
    doc = await db.strategies.find_one({"_id": ObjectId(strategy_id)})
    if not doc:
        raise HTTPException(status_code=404, detail="Strategy not found")
    return serialize_doc(doc)


@router.post("/upload")
async def upload_strategy(file: UploadFile = File(...), name: str = Form(...)):
    allowed_types = [".pdf", ".txt", ".md"]
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in allowed_types:
        raise HTTPException(status_code=400, detail=f"Unsupported file type. Allowed: {allowed_types}")

    content = await file.read()
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File too large. Max 10MB.")

    with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
        tmp.write(content)
        tmp_path = tmp.name

    try:
        text = extract_text(tmp_path, ext.lstrip("."))
        result = process_strategy(text, file.filename)

        db = get_db()
        strategy_doc = {
            "name": name,
            "source_type": result["source_type"],
            "original_filename": file.filename,
            "status": StrategyStatus.READY,
            "metadata": result["metadata"],
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
        }
        insert_result = await db.strategies.insert_one(strategy_doc)
        strategy_id = str(insert_result.inserted_id)

        chunks = [
            {
                "strategy_id": strategy_id,
                "section": chunk[:100],
                "content": chunk,
                "chunk_index": i,
                "metadata": {},
                "created_at": datetime.utcnow(),
            }
            for i, chunk in enumerate(result["chunks"])
        ]
        if chunks:
            await db.strategy_chunks.insert_many(chunks)

        rules_doc = {
            "strategy_id": strategy_id,
            **result["rules"],
            "raw_text": result["cleaned_text"][:5000],
            "created_at": datetime.utcnow(),
        }
        await db.strategy_rules.insert_one(rules_doc)

        return {
            "id": strategy_id,
            "name": name,
            "status": "ready",
            "metadata": result["metadata"],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Processing failed: {str(e)}")
    finally:
        os.unlink(tmp_path)


@router.post("/text")
async def create_strategy_from_text(name: str, text: str):
    result = process_strategy(text, f"{name}.txt")

    db = get_db()
    strategy_doc = {
        "name": name,
        "source_type": "txt",
        "original_filename": f"{name}.txt",
        "status": StrategyStatus.READY,
        "metadata": result["metadata"],
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
    }
    insert_result = await db.strategies.insert_one(strategy_doc)
    strategy_id = str(insert_result.inserted_id)

    chunks = [
        {
            "strategy_id": strategy_id,
            "section": chunk[:100],
            "content": chunk,
            "chunk_index": i,
            "metadata": {},
            "created_at": datetime.utcnow(),
        }
        for i, chunk in enumerate(result["chunks"])
    ]
    if chunks:
        await db.strategy_chunks.insert_many(chunks)

    rules_doc = {
        "strategy_id": strategy_id,
        **result["rules"],
        "raw_text": result["cleaned_text"][:5000],
        "created_at": datetime.utcnow(),
    }
    await db.strategy_rules.insert_one(rules_doc)

    return {
        "id": strategy_id,
        "name": name,
        "status": "ready",
        "metadata": result["metadata"],
    }
