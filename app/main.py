import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from app.core.config import get_settings
from app.core.database import connect_db, close_db
from app.api import markets, analyze, strategies, analyses, swing_smc, advanced_smc

logging.basicConfig(level=logging.INFO)

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await connect_db()
    yield
    await close_db()


app = FastAPI(
    title="Karren",
    description="Private AI Trading Signal Intelligence System",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(markets.router)
app.include_router(analyze.router)
app.include_router(strategies.router)
app.include_router(analyses.router)
app.include_router(swing_smc.router)
app.include_router(advanced_smc.router)


@app.get("/")
async def root():
    return {"name": "Karren", "version": "0.1.0", "status": "running"}


@app.get("/health")
async def health():
    return {"status": "ok"}
