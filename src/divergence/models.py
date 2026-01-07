"""
Data models for topic divergence detection and conversation segmentation.
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List, Dict, Any
from enum import Enum
import numpy as np


class MessageRelation(str, Enum):
    """
    Classification of how a message relates to the conversation anchor.
    
    Used by the LLM-as-Judge approach to classify each message's relationship
    to the original topic.
    """
    CONTINUING = "continuing"      # Stays on main topic
    CLARIFYING = "clarifying"      # Asking about something to better address main topic
    DRILLING = "drilling"          # Going deeper into a subtopic (hierarchical)
    BRANCHING = "branching"        # New topic, sustained departure
    TANGENT = "tangent"            # Brief departure, likely to return
    CONCLUDING = "concluding"      # Wrapping up current topic
    RETURNING = "returning"        # Coming back to earlier topic


class LinkType(str, Enum):
    """Types of links between segments."""
    CONTINUES = "continues"         # Direct continuation of the segment
    REFERENCES = "references"       # References but doesn't continue
    BRANCHES_FROM = "branches_from" # Branched into a new topic
    RESOLVES = "resolves"          # Resolves/answers the segment's question


@dataclass
class Segment:
    """
    Represents a contiguous segment of conversation on a single topic.
    
    Segments are the fundamental unit for:
    - Topic divergence analysis
    - Cross-chat linking
    - Potential child chat creation
    
    Attributes
    ----------
    id : str
        Unique identifier for the segment
    chat_id : int
        ID of the chat this segment belongs to
    start_message_idx : int
        Index of first message in this segment (0-based)
    end_message_idx : int
        Index of last message in this segment (inclusive)
    anchor_embedding : np.ndarray, optional
        Mean embedding of messages in this segment (for similarity matching)
    summary : str
        LLM-generated summary of this segment's content
    topic_label : str, optional
        Human-readable topic label (from BERTopic or LLM)
    parent_segment_id : str, optional
        For hierarchical topics, the parent segment this diverged from
    divergence_score : float
        How far this segment diverged from parent/anchor (0-1)
    created_at : datetime
        When this segment was detected
    """
    id: str
    chat_id: int
    start_message_idx: int
    end_message_idx: int
    anchor_embedding: Optional[np.ndarray] = None
    summary: str = ""
    topic_label: Optional[str] = None
    parent_segment_id: Optional[str] = None
    divergence_score: float = 0.0
    created_at: Optional[datetime] = None
    
    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now()
    
    @property
    def message_count(self) -> int:
        """Number of messages in this segment."""
        return self.end_message_idx - self.start_message_idx + 1
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for database storage."""
        return {
            "id": self.id,
            "chat_id": self.chat_id,
            "start_message_idx": self.start_message_idx,
            "end_message_idx": self.end_message_idx,
            "summary": self.summary,
            "topic_label": self.topic_label,
            "parent_segment_id": self.parent_segment_id,
            "divergence_score": self.divergence_score,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


@dataclass
class SegmentLink:
    """
    Represents a link between two segments (same or different chats).
    
    Enables segment-to-segment linking rather than just chat-to-chat,
    allowing for more precise topic tracking across conversations.
    
    Attributes
    ----------
    id : str
        Unique identifier for the link
    source_segment_id : str
        Segment that references another
    target_segment_id : str
        Segment being referenced
    link_type : LinkType
        Type of relationship between segments
    similarity_score : float
        Semantic similarity score (0-1)
    created_at : datetime
        When this link was detected
    metadata : dict, optional
        Additional metadata about the link
    """
    id: str
    source_segment_id: str
    target_segment_id: str
    link_type: LinkType
    similarity_score: float = 0.0
    created_at: Optional[datetime] = None
    metadata: Optional[Dict[str, Any]] = None
    
    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now()
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for database storage."""
        return {
            "id": self.id,
            "source_segment_id": self.source_segment_id,
            "target_segment_id": self.target_segment_id,
            "link_type": self.link_type.value,
            "similarity_score": self.similarity_score,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "metadata": self.metadata,
        }


@dataclass
class DivergenceMetrics:
    """
    Metrics computed by divergence analysis.
    
    Each analysis approach (embedding, topic, LLM) produces metrics
    that are combined for overall scoring.
    
    Attributes
    ----------
    max_drift : float
        Furthest point from anchor (0-1 scale)
    mean_drift : float
        Average distance across conversation
    drift_velocity : float
        How quickly similarity decays (derivative of drift curve)
    return_count : int
        Number of times drift decreased significantly after increasing
    final_drift : float
        Where the conversation ended up
    num_topics : int
        Total distinct topics detected
    topic_entropy : float
        Shannon entropy of topic distribution
    transition_rate : float
        How often topics change
    dominant_topic_ratio : float
        Concentration in primary topic
    mean_relevance : float
        Average relevance score from LLM (0-10 scale)
    branch_count : int
        Number of BRANCHING classifications from LLM
    """
    # Embedding drift metrics
    max_drift: float = 0.0
    mean_drift: float = 0.0
    drift_velocity: float = 0.0
    return_count: int = 0
    final_drift: float = 0.0
    
    # Topic modeling metrics
    num_topics: int = 1
    topic_entropy: float = 0.0
    transition_rate: float = 0.0
    dominant_topic_ratio: float = 1.0
    
    # LLM judge metrics
    mean_relevance: float = 10.0
    branch_count: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "max_drift": self.max_drift,
            "mean_drift": self.mean_drift,
            "drift_velocity": self.drift_velocity,
            "return_count": self.return_count,
            "final_drift": self.final_drift,
            "num_topics": self.num_topics,
            "topic_entropy": self.topic_entropy,
            "transition_rate": self.transition_rate,
            "dominant_topic_ratio": self.dominant_topic_ratio,
            "mean_relevance": self.mean_relevance,
            "branch_count": self.branch_count,
        }


@dataclass
class DivergenceReport:
    """
    Complete divergence analysis report for a chat.
    
    Aggregates all analysis results into a single report with
    actionable recommendations.
    
    Attributes
    ----------
    chat_id : int
        Database ID of the analyzed chat
    overall_score : float
        Composite divergence score (0 = laser focused, 1 = all over the place)
    embedding_drift_score : float
        Score from embedding drift analysis
    topic_entropy_score : float
        Score from topic entropy
    topic_transition_score : float
        Score from topic transitions
    llm_relevance_score : float, optional
        Score from LLM relevance analysis
    metrics : DivergenceMetrics
        Detailed metrics from all approaches
    num_segments : int
        Number of segments detected
    segments : list[Segment]
        Detected segments
    should_split : bool
        Whether this chat should be split into child chats
    suggested_split_points : list[int]
        Message indices where splits are recommended
    topic_summaries : list[str]
        One summary per segment, for matching to other chats
    interpretation : str
        Human-readable interpretation of the score
    computed_at : datetime
        When this report was generated
    """
    chat_id: int
    overall_score: float
    
    # Component scores
    embedding_drift_score: float = 0.0
    topic_entropy_score: float = 0.0
    topic_transition_score: float = 0.0
    llm_relevance_score: Optional[float] = None
    
    # Detailed metrics
    metrics: DivergenceMetrics = field(default_factory=DivergenceMetrics)
    
    # Segment info
    num_segments: int = 1
    segments: List[Segment] = field(default_factory=list)
    
    # Recommendations
    should_split: bool = False
    suggested_split_points: List[int] = field(default_factory=list)
    
    # For linking
    topic_summaries: List[str] = field(default_factory=list)
    
    # Metadata
    interpretation: str = ""
    computed_at: Optional[datetime] = None
    
    def __post_init__(self):
        if self.computed_at is None:
            self.computed_at = datetime.now()
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for database storage."""
        return {
            "chat_id": self.chat_id,
            "overall_score": self.overall_score,
            "embedding_drift_score": self.embedding_drift_score,
            "topic_entropy_score": self.topic_entropy_score,
            "topic_transition_score": self.topic_transition_score,
            "llm_relevance_score": self.llm_relevance_score,
            "metrics": self.metrics.to_dict(),
            "num_segments": self.num_segments,
            "should_split": self.should_split,
            "suggested_split_points": self.suggested_split_points,
            "topic_summaries": self.topic_summaries,
            "interpretation": self.interpretation,
            "computed_at": self.computed_at.isoformat() if self.computed_at else None,
        }


@dataclass
class MessageClassification:
    """
    Classification result for a single message from LLM judge.
    
    Attributes
    ----------
    message_idx : int
        Index of the message in the conversation
    relation : MessageRelation
        How this message relates to the anchor
    relevance_score : float
        0-10 scale of relevance to original topic
    suggested_segment_break : bool
        Whether this message should start a new segment
    reasoning : str
        LLM's explanation for the classification
    """
    message_idx: int
    relation: MessageRelation
    relevance_score: float
    suggested_segment_break: bool
    reasoning: str
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "message_idx": self.message_idx,
            "relation": self.relation.value,
            "relevance_score": self.relevance_score,
            "suggested_segment_break": self.suggested_segment_break,
            "reasoning": self.reasoning,
        }
