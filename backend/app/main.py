"""FastAPI application entry point.

Run: uvicorn backend.app.main:app --reload --port 8000
"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .routers import codegen, discovery, gaps, health, runs

app = FastAPI(
    title="Discovery Agent",
    version="1.0.0",
    description="Agent 3 — discovers systems from documents, finds integration gaps, "
                "and generates connector code. Levels 1-3.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # demo; tighten for production
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(discovery.router)
app.include_router(gaps.router)
app.include_router(codegen.router)
app.include_router(runs.router)


@app.get("/")
def root() -> dict:
    return {"service": "discovery-agent", "docs": "/docs", "health": "/health"}
