from __future__ import annotations

from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
async def health():
    return {"status": "ok"}


@router.get("/status")
async def status():
    return {
        "version": "0.1.0",
        "phase": "1D",
        "providers": [],
    }
