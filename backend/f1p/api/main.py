"""FastAPI application. Run with ``uvicorn f1p.api.main:app --reload``; docs at ``/docs``."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from f1p import __version__
from f1p.api.routers import game, predictions, races, simulate

app = FastAPI(
    title="PitWall API",
    version=__version__,
    description="Probabilistic Grand Prix finishing-order predictions, results and track record.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["GET", "POST", "PUT"],
    allow_headers=["Content-Type", "X-Player-Token"],
)

app.include_router(races.router)
app.include_router(predictions.router)
app.include_router(simulate.router)
app.include_router(game.router)


@app.get("/health", tags=["meta"])
def health() -> dict[str, str]:
    return {"status": "ok", "version": __version__}
