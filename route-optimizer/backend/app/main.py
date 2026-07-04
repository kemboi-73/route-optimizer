"""
main.py
-------
FastAPI application entrypoint. Configures logging, CORS (so the React
dev server / production frontend can call this API from a different
origin), and mounts the API router. Swagger UI is auto-available at
/docs and ReDoc at /redoc thanks to FastAPI's OpenAPI generation.
"""
import logging
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router as api_router

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Route Optimization API",
    description=(
        "Production-style delivery route optimization service. Uses Google "
        "OR-Tools to solve the Traveling Salesman Problem over real road "
        "network data (distances/durations) from OSRM, with addresses "
        "resolved via OpenStreetMap Nominatim."
    ),
    version="1.0.0",
)

allowed_origins = os.getenv("CORS_ALLOWED_ORIGINS", "http://localhost:3000,http://localhost:5173").split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix="/api")


@app.get("/health", tags=["meta"], summary="Liveness/readiness probe")
async def health():
    return {"status": "ok"}


@app.on_event("startup")
async def on_startup():
    logger.info("Route Optimization API starting up. CORS origins: %s", allowed_origins)
