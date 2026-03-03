"""
Segments API routes for topic divergence analysis.

Provides endpoints for viewing and triggering topic analysis on chats.
"""

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from src.api.deps import get_db
from src.core.db import ChatDatabase

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/chats/{chat_id}/segments")
def get_chat_segments(
    chat_id: int,
    db: ChatDatabase = Depends(get_db),
) -> Dict[str, Any]:
    """
    Get topic analysis and segments for a chat.

    Returns the divergence report, segments, and LLM judgements
    if analysis has been run for this chat.

    Parameters
    ----------
    chat_id : int
        Chat ID to retrieve analysis for.
    db : ChatDatabase
        Database instance (injected via dependency).

    Returns
    -------
    dict
        Analysis report with segments and judgements.

    Raises
    ------
    HTTPException
        404 if no analysis found for the chat.
    """
    analysis = db.segments.get_topic_analysis(chat_id)
    if not analysis:
        raise HTTPException(
            status_code=404,
            detail=f"No topic analysis found for chat {chat_id}. Run analysis first.",
        )

    segments = db.segments.get_chat_segments(chat_id)
    judgements = db.segments.get_message_judgements(chat_id)

    # Strip anchor_embedding from response (large, not useful for API consumers)
    for seg in segments:
        seg.pop("anchor_embedding", None)

    return {
        "chat_id": chat_id,
        "analysis": analysis,
        "segments": segments,
        "judgements": judgements,
    }


@router.post("/chats/{chat_id}/segments/analyze")
def analyze_chat_segments(
    chat_id: int,
    use_llm: bool = Query(True, description="Enable LLM judge signal"),
    topic_backend: str = Query("auto", description="Topic backend: auto, bertopic, tfidf"),
    drift_threshold: float = Query(0.35, description="Cosine distance threshold for drift"),
    min_segment_messages: int = Query(3, description="Minimum messages per segment"),
    db: ChatDatabase = Depends(get_db),
) -> Dict[str, Any]:
    """
    Run topic divergence analysis on a specific chat.

    Executes the three-signal ensemble (embedding drift, topic modeling,
    optional LLM judge) and stores results.

    Parameters
    ----------
    chat_id : int
        Chat ID to analyze.
    use_llm : bool
        Whether to include LLM judge signal.
    topic_backend : str
        Topic modeling backend (auto, bertopic, tfidf).
    drift_threshold : float
        Cosine distance threshold for embedding drift detection.
    min_segment_messages : int
        Minimum number of messages per segment.
    db : ChatDatabase
        Database instance (injected via dependency).

    Returns
    -------
    dict
        Analysis results including overall score, segments, and metadata.

    Raises
    ------
    HTTPException
        404 if chat not found or has no messages.
        500 if analysis fails.
    """
    from src.services.topic_analysis import TopicAnalysisService

    service = TopicAnalysisService(
        db=db,
        embedder_backend="tfidf" if topic_backend == "tfidf" else "auto",
        topic_backend=topic_backend,
        use_llm=use_llm,
        drift_threshold=drift_threshold,
        min_segment_messages=min_segment_messages,
    )

    try:
        report = service.analyze_chat(chat_id)
    except Exception as e:
        logger.error("Topic analysis failed for chat %d: %s", chat_id, e, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Topic analysis failed: {str(e)}",
        )

    if not report:
        raise HTTPException(
            status_code=404,
            detail=f"Chat {chat_id} not found or has no messages.",
        )

    return {
        "chat_id": chat_id,
        "overall_score": report.overall_score,
        "should_split": report.should_split,
        "num_segments": len(report.suggested_split_points) + 1,
        "suggested_split_points": report.suggested_split_points,
    }


@router.get("/segments/high-divergence")
def get_high_divergence_chats(
    threshold: float = Query(0.5, description="Minimum divergence score"),
    limit: int = Query(20, ge=1, le=100, description="Maximum results"),
    db: ChatDatabase = Depends(get_db),
) -> Dict[str, Any]:
    """
    List chats with high topic divergence scores.

    Parameters
    ----------
    threshold : float
        Minimum divergence score to include.
    limit : int
        Maximum number of results.
    db : ChatDatabase
        Database instance (injected via dependency).

    Returns
    -------
    dict
        List of high-divergence chats with scores and metadata.
    """
    results = db.segments.get_high_divergence_chats(threshold=threshold, limit=limit)
    return {
        "threshold": threshold,
        "count": len(results),
        "chats": results,
    }


@router.get("/segments/stats")
def get_segment_stats(
    db: ChatDatabase = Depends(get_db),
) -> Dict[str, Any]:
    """
    Get summary statistics for topic analysis.

    Returns
    -------
    dict
        Statistics including total analyzed, score distribution, etc.
    """
    return db.segments.get_stats()
