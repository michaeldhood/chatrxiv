"""
Health check API route.

Provides endpoint for checking server readiness and ingestion status.
"""
from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
def health():
    """
    Health check endpoint.

    Returns server status and whether initial ingestion has completed.
    Server is ready to handle requests immediately, but data may be
    incomplete until ingestion completes.
    """
    # Import here to avoid circular dependency
    from src.api.main import _ingestion_complete

    return {
        "status": "ready",
        "ingestion_complete": _ingestion_complete.is_set(),
    }
