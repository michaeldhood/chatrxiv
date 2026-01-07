"""
Topic Divergence Detection & Conversation Segmentation.

This module provides tools to:
1. Measure topic divergence in chat conversations
2. Detect natural segment boundaries
3. Enable segment-level linking between chats

Three approaches are implemented:
- Embedding drift analysis (semantic similarity over time)
- Topic modeling with BERTopic (discrete topic extraction)
- LLM-as-Judge (Claude-based classification)

These are combined via ensemble to produce robust segmentation.
"""
from .models import (
    Segment,
    SegmentLink,
    DivergenceReport,
    DivergenceMetrics,
    MessageRelation,
)
from .embedding_drift import EmbeddingDriftAnalyzer
from .topic_modeling import TopicDivergenceAnalyzer
from .llm_judge import LLMDivergenceAnalyzer
from .segmenter import ConversationSegmenter
from .processor import DivergenceProcessor

__all__ = [
    # Models
    "Segment",
    "SegmentLink",
    "DivergenceReport",
    "DivergenceMetrics",
    "MessageRelation",
    # Analyzers
    "EmbeddingDriftAnalyzer",
    "TopicDivergenceAnalyzer",
    "LLMDivergenceAnalyzer",
    # Segmenter
    "ConversationSegmenter",
    # Processor
    "DivergenceProcessor",
]
