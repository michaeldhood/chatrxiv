from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from datetime import datetime
import numpy as np
from enum import Enum

@dataclass
class AnalyzedMessage:
    """
    Extended message model for analysis purposes.
    Wraps the core message ID but adds embedding support.
    """
    id: int  # References core.models.Message.id
    chat_id: int # References core.models.Chat.id
    content: str
    role: str
    timestamp: Optional[datetime]
    embedding: Optional[np.ndarray] = None

@dataclass
class Segment:
    id: str
    chat_id: int
    start_message_idx: int
    end_message_idx: int
    anchor_embedding: np.ndarray
    summary: str
    topic_label: Optional[str] = None
    parent_segment_id: Optional[str] = None
    divergence_score: float = 0.0

@dataclass
class SegmentLink:
    id: str
    source_segment_id: str
    target_segment_id: str
    link_type: str  # 'continues', 'references', 'branches_from', 'resolves'

class MessageRelation(Enum):
    CONTINUING = "continuing"
    CLARIFYING = "clarifying"
    DRILLING = "drilling"
    BRANCHING = "branching"
    TANGENT = "tangent"
    CONCLUDING = "concluding"
    RETURNING = "returning"

@dataclass
class AnalyzedChat:
    """
    Enriched Chat object with segmentation data.
    """
    id: int
    messages: List[AnalyzedMessage]
    segments: List[Segment]
    root_segment_id: Optional[str] = None

@dataclass
class DivergenceReport:
    chat_id: int
    overall_score: float
    
    # Component scores
    embedding_drift_score: float
    topic_entropy_score: float
    topic_transition_score: float
    llm_relevance_score: Optional[float]
    
    # Segment info
    num_segments: int
    segments: List[Segment]
    
    # Recommendations
    should_split: bool
    suggested_split_points: List[int]
    
    # For linking
    topic_summaries: List[str]
