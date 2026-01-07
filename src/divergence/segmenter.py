"""
Ensemble Conversation Segmenter.

Combines all three analysis approaches (embedding drift, topic modeling,
LLM judge) to produce robust segment boundaries and divergence scores.
"""
import logging
import uuid
from typing import List, Dict, Any, Optional, Tuple
from collections import Counter
import numpy as np

from .models import (
    Segment,
    SegmentLink,
    DivergenceReport,
    DivergenceMetrics,
    LinkType,
)
from .embedding_drift import EmbeddingDriftAnalyzer
from .topic_modeling import TopicDivergenceAnalyzer
from .llm_judge import LLMDivergenceAnalyzer

logger = logging.getLogger(__name__)


class ConversationSegmenter:
    """
    Ensemble segmenter that combines multiple analysis approaches.
    
    Provides robust segment detection by requiring agreement between
    multiple signals before confirming a segment boundary.
    
    Strategy:
    1. Run embedding drift analysis
    2. Run topic modeling (if enough messages)
    3. Run LLM analysis (optional, for high-value insights)
    4. Combine signals:
       - Embedding drift > threshold = potential boundary
       - Topic model transition = potential boundary
       - LLM says segment_break = strong signal
    5. Require 2+ signals to confirm boundary (unless LLM is very confident)
    
    Attributes
    ----------
    embedding_analyzer : EmbeddingDriftAnalyzer
        Semantic drift analyzer
    topic_analyzer : TopicDivergenceAnalyzer
        BERTopic-based analyzer
    llm_analyzer : LLMDivergenceAnalyzer, optional
        Claude-based analyzer (created on demand)
    use_llm : bool
        Whether to use LLM analysis
    """
    
    def __init__(
        self,
        embedding_model: str = "all-MiniLM-L6-v2",
        use_llm: bool = True,
        llm_model: str = "claude-sonnet-4-20250514",
    ):
        """
        Initialize the ensemble segmenter.
        
        Parameters
        ----------
        embedding_model : str
            Sentence transformer model for embeddings
        use_llm : bool
            Whether to use LLM-based analysis (default: True)
        llm_model : str
            Claude model for LLM analysis
        """
        self.embedding_analyzer = EmbeddingDriftAnalyzer(model_name=embedding_model)
        self.topic_analyzer = TopicDivergenceAnalyzer(
            embedding_model=embedding_model,
            min_topic_size=2,
        )
        self.use_llm = use_llm
        self.llm_model = llm_model
        self._llm_analyzer = None
    
    @property
    def llm_analyzer(self) -> LLMDivergenceAnalyzer:
        """Lazy load LLM analyzer."""
        if self._llm_analyzer is None:
            self._llm_analyzer = LLMDivergenceAnalyzer(model=self.llm_model)
        return self._llm_analyzer
    
    def segment_chat(
        self,
        chat_id: int,
        messages: List[Dict[str, str]],
        drift_threshold: float = 0.35,
        min_segment_messages: int = 3,
        use_llm_override: Optional[bool] = None,
    ) -> List[Segment]:
        """
        Detect segment boundaries using ensemble of approaches.
        
        Parameters
        ----------
        chat_id : int
            Database ID of the chat
        messages : List[Dict[str, str]]
            Messages with 'role' and 'text' keys
        drift_threshold : float
            Threshold for embedding drift (default: 0.35)
        min_segment_messages : int
            Minimum messages per segment (default: 3)
        use_llm_override : bool, optional
            Override default LLM usage for this call
            
        Returns
        -------
        list[Segment]
            Detected segments with boundaries and metadata
        """
        if not messages or len(messages) < min_segment_messages:
            # Single segment for short conversations
            return [self._create_single_segment(chat_id, messages)]
        
        # Extract message texts
        message_texts = [msg.get('text', '') for msg in messages]
        
        # Run all analyzers
        embedding_result = self.embedding_analyzer.analyze_chat(
            message_texts,
            drift_threshold=drift_threshold,
            min_segment_length=min_segment_messages,
        )
        
        topic_result = self.topic_analyzer.analyze_chat(message_texts)
        
        # Get changepoints from each approach
        embedding_changepoints = set(embedding_result.get('changepoints', []))
        topic_changepoints = set(self.topic_analyzer.get_segment_boundaries(
            topic_result.get('topics', [])
        ))
        
        llm_changepoints = set()
        llm_result = None
        
        use_llm = use_llm_override if use_llm_override is not None else self.use_llm
        if use_llm and len(messages) > min_segment_messages:
            try:
                llm_result = self.llm_analyzer.analyze_full_chat(messages)
                llm_changepoints = set(llm_result.get('suggested_changepoints', []))
            except Exception as e:
                logger.warning("LLM analysis failed, continuing without: %s", e)
        
        # Combine signals with voting
        all_candidates = embedding_changepoints | topic_changepoints | llm_changepoints
        confirmed_boundaries = []
        
        for idx in sorted(all_candidates):
            if idx < min_segment_messages:
                continue  # Too close to start
            if confirmed_boundaries and idx - confirmed_boundaries[-1] < min_segment_messages:
                continue  # Too close to previous boundary
            
            votes = 0
            if idx in embedding_changepoints:
                votes += 1
            if idx in topic_changepoints:
                votes += 1
            if idx in llm_changepoints:
                votes += 2  # LLM gets double weight
            
            # Require at least 2 votes (or 1 if from LLM with high confidence)
            if votes >= 2:
                confirmed_boundaries.append(idx)
        
        # Create segments from boundaries
        segments = self._create_segments_from_boundaries(
            chat_id=chat_id,
            messages=messages,
            boundaries=confirmed_boundaries,
            embeddings=embedding_result.get('embeddings'),
            drift_scores=embedding_result.get('drift_scores', []),
        )
        
        return segments
    
    def _create_single_segment(
        self,
        chat_id: int,
        messages: List[Dict[str, str]],
    ) -> Segment:
        """Create a single segment covering all messages."""
        segment_id = str(uuid.uuid4())
        
        # Compute anchor embedding if possible
        anchor_embedding = None
        message_texts = [msg.get('text', '') for msg in messages]
        if message_texts:
            try:
                anchor_embedding = self.embedding_analyzer.embed_messages(message_texts)
            except Exception:
                pass
        
        return Segment(
            id=segment_id,
            chat_id=chat_id,
            start_message_idx=0,
            end_message_idx=len(messages) - 1 if messages else 0,
            anchor_embedding=anchor_embedding,
            summary="",  # Will be generated later if needed
            topic_label="main topic",
            parent_segment_id=None,
            divergence_score=0.0,
        )
    
    def _create_segments_from_boundaries(
        self,
        chat_id: int,
        messages: List[Dict[str, str]],
        boundaries: List[int],
        embeddings: Optional[np.ndarray] = None,
        drift_scores: List[float] = None,
    ) -> List[Segment]:
        """
        Create Segment objects from detected boundaries.
        
        Parameters
        ----------
        chat_id : int
            Chat database ID
        messages : List[Dict[str, str]]
            All messages
        boundaries : List[int]
            Indices where new segments start
        embeddings : np.ndarray, optional
            Pre-computed embeddings for efficiency
        drift_scores : List[float], optional
            Drift scores for computing divergence
            
        Returns
        -------
        list[Segment]
            Segment objects
        """
        segments = []
        root_segment_id = str(uuid.uuid4())
        
        # Add 0 as implicit start and len(messages) as implicit end
        all_boundaries = [0] + boundaries + [len(messages)]
        
        for i in range(len(all_boundaries) - 1):
            start_idx = all_boundaries[i]
            end_idx = all_boundaries[i + 1] - 1  # Inclusive
            
            segment_id = root_segment_id if i == 0 else str(uuid.uuid4())
            
            # Compute anchor embedding for this segment
            anchor_embedding = None
            if embeddings is not None and len(embeddings) > 0:
                segment_embeddings = embeddings[start_idx:end_idx + 1]
                if len(segment_embeddings) > 0:
                    anchor_embedding = np.mean(segment_embeddings, axis=0)
                    norm = np.linalg.norm(anchor_embedding)
                    if norm > 0:
                        anchor_embedding = anchor_embedding / norm
            
            # Compute divergence score for this segment
            divergence_score = 0.0
            if drift_scores and start_idx < len(drift_scores):
                segment_drifts = drift_scores[start_idx:end_idx + 1]
                if segment_drifts:
                    divergence_score = float(np.mean(segment_drifts))
            
            segment = Segment(
                id=segment_id,
                chat_id=chat_id,
                start_message_idx=start_idx,
                end_message_idx=end_idx,
                anchor_embedding=anchor_embedding,
                summary="",  # Will be generated if needed
                topic_label=None,
                parent_segment_id=root_segment_id if i > 0 else None,
                divergence_score=divergence_score,
            )
            segments.append(segment)
        
        return segments
    
    def compute_divergence_score(
        self,
        messages: List[Dict[str, str]],
        use_llm_override: Optional[bool] = None,
    ) -> DivergenceReport:
        """
        Compute overall divergence score for a chat.
        
        Returns a composite score with breakdown by method.
        
        Parameters
        ----------
        messages : List[Dict[str, str]]
            Chat messages
        use_llm_override : bool, optional
            Override default LLM usage
            
        Returns
        -------
        DivergenceReport
            Complete divergence analysis
        """
        if not messages:
            return DivergenceReport(
                chat_id=0,
                overall_score=0.0,
                interpretation="No messages to analyze",
            )
        
        message_texts = [msg.get('text', '') for msg in messages]
        
        # Run embedding analysis
        embedding_result = self.embedding_analyzer.compute_drift_curve(message_texts)
        embedding_metrics = embedding_result['metrics']
        
        # Run topic analysis
        topic_result = self.topic_analyzer.analyze_chat(message_texts)
        topic_metrics = topic_result['metrics']
        
        # Run LLM analysis if enabled
        llm_metrics = None
        use_llm = use_llm_override if use_llm_override is not None else self.use_llm
        if use_llm:
            try:
                llm_result = self.llm_analyzer.analyze_full_chat(messages)
                llm_metrics = llm_result['metrics']
            except Exception as e:
                logger.warning("LLM analysis failed: %s", e)
        
        # Compute component scores (normalized to 0-1)
        embedding_drift_score = min(1.0, embedding_metrics['mean_drift'] / 0.5)
        topic_entropy_score = min(1.0, topic_metrics['topic_entropy'] / 3.0)
        topic_transition_score = min(1.0, topic_metrics['transition_rate'] * 2)
        
        llm_relevance_score = None
        if llm_metrics:
            # Convert relevance (0-10, higher=more relevant) to divergence (0-1, higher=more divergent)
            llm_relevance_score = 1.0 - (llm_metrics['mean_relevance'] / 10.0)
        
        # Compute composite score
        # Weight: embedding 40%, topic entropy 20%, topic transition 20%, LLM 20%
        if llm_relevance_score is not None:
            composite = (
                0.35 * embedding_drift_score +
                0.20 * topic_entropy_score +
                0.20 * topic_transition_score +
                0.25 * llm_relevance_score
            )
        else:
            # Without LLM, redistribute weights
            composite = (
                0.45 * embedding_drift_score +
                0.30 * topic_entropy_score +
                0.25 * topic_transition_score
            )
        
        composite = min(1.0, max(0.0, composite))
        
        # Build metrics object
        metrics = DivergenceMetrics(
            max_drift=embedding_metrics['max_drift'],
            mean_drift=embedding_metrics['mean_drift'],
            drift_velocity=embedding_metrics['drift_velocity'],
            return_count=embedding_metrics['return_count'],
            final_drift=embedding_metrics['final_drift'],
            num_topics=topic_metrics['num_topics'],
            topic_entropy=topic_metrics['topic_entropy'],
            transition_rate=topic_metrics['transition_rate'],
            dominant_topic_ratio=topic_metrics['dominant_topic_ratio'],
            mean_relevance=llm_metrics['mean_relevance'] if llm_metrics else 10.0,
            branch_count=llm_metrics['branch_count'] if llm_metrics else 0,
        )
        
        # Get segment boundaries
        embedding_changepoints = self.embedding_analyzer.detect_changepoints(
            embedding_result['drift_scores']
        )
        topic_boundaries = self.topic_analyzer.get_segment_boundaries(
            topic_result.get('topics', [])
        )
        
        # Merge boundaries
        all_boundaries = sorted(set(embedding_changepoints) | set(topic_boundaries))
        num_segments = len(all_boundaries) + 1
        
        # Determine if split is recommended
        should_split = composite > 0.5 or num_segments > 3
        
        # Generate interpretation
        interpretation = self._interpret_score(composite)
        
        return DivergenceReport(
            chat_id=0,  # Will be set by caller
            overall_score=composite,
            embedding_drift_score=embedding_drift_score,
            topic_entropy_score=topic_entropy_score,
            topic_transition_score=topic_transition_score,
            llm_relevance_score=llm_relevance_score,
            metrics=metrics,
            num_segments=num_segments,
            segments=[],  # Will be populated by segment_chat if needed
            should_split=should_split,
            suggested_split_points=all_boundaries,
            topic_summaries=[],  # Will be generated if needed
            interpretation=interpretation,
        )
    
    def _interpret_score(self, score: float) -> str:
        """Generate human-readable interpretation of divergence score."""
        if score < 0.2:
            return "Highly focused - single topic throughout"
        elif score < 0.4:
            return "Mostly focused with minor tangents"
        elif score < 0.6:
            return "Moderate divergence - multiple related topics"
        elif score < 0.8:
            return "Significant divergence - distinct topic branches"
        else:
            return "Highly divergent - consider splitting into child chats"
    
    def analyze_chat_full(
        self,
        chat_id: int,
        messages: List[Dict[str, str]],
        generate_summaries: bool = False,
    ) -> Tuple[DivergenceReport, List[Segment]]:
        """
        Full analysis: divergence score + segmentation.
        
        Convenience method that returns both the divergence report
        and the detected segments.
        
        Parameters
        ----------
        chat_id : int
            Chat database ID
        messages : List[Dict[str, str]]
            Chat messages
        generate_summaries : bool
            Whether to generate LLM summaries for segments
            
        Returns
        -------
        Tuple[DivergenceReport, List[Segment]]
            (report, segments)
        """
        # Compute divergence score
        report = self.compute_divergence_score(messages)
        report.chat_id = chat_id
        
        # Segment the chat
        segments = self.segment_chat(
            chat_id=chat_id,
            messages=messages,
            drift_threshold=0.35,
            min_segment_messages=3,
        )
        
        report.segments = segments
        report.num_segments = len(segments)
        
        # Generate summaries if requested
        if generate_summaries and self.use_llm:
            summaries = []
            for segment in segments:
                segment_messages = messages[segment.start_message_idx:segment.end_message_idx + 1]
                try:
                    summary = self.llm_analyzer.generate_segment_summary(segment_messages)
                    segment.summary = summary
                    summaries.append(summary)
                except Exception as e:
                    logger.warning("Failed to generate summary for segment: %s", e)
                    summaries.append("")
            report.topic_summaries = summaries
        
        return report, segments


def find_best_link_target(
    source_segment: Segment,
    target_segments: List[Segment],
    analyzer: Optional[EmbeddingDriftAnalyzer] = None,
) -> Optional[Dict[str, Any]]:
    """
    Find which segment in target list best matches source segment.
    
    Useful for cross-chat linking.
    
    Parameters
    ----------
    source_segment : Segment
        Segment to find match for
    target_segments : List[Segment]
        Candidate segments to match against
    analyzer : EmbeddingDriftAnalyzer, optional
        Analyzer for computing similarity (creates new if not provided)
        
    Returns
    -------
    dict, optional
        {
            'target_segment_id': str,
            'similarity_score': float,
            'link_type': LinkType
        }
        or None if no good match found
    """
    if source_segment.anchor_embedding is None:
        return None
    
    best_match = None
    best_score = -1.0
    
    for target in target_segments:
        if target.anchor_embedding is None:
            continue
        
        # Compute cosine similarity
        similarity = float(np.dot(
            source_segment.anchor_embedding,
            target.anchor_embedding
        ))
        
        if similarity > best_score:
            best_score = similarity
            best_match = target
    
    if best_match is None or best_score < 0.3:
        return None
    
    # Infer link type from similarity and divergence
    if best_score > 0.8:
        link_type = LinkType.CONTINUES
    elif source_segment.divergence_score > 0.5:
        link_type = LinkType.BRANCHES_FROM
    else:
        link_type = LinkType.REFERENCES
    
    return {
        'target_segment_id': best_match.id,
        'similarity_score': best_score,
        'link_type': link_type,
    }
