"""
Topic divergence detection and conversation segmentation service.

Implements a three-signal ensemble approach:
1. Embedding drift (sentence-transformers or TF-IDF fallback)
2. Topic modeling (BERTopic or TF-IDF fallback)
3. LLM-as-judge (Claude, optional)

Combines signals via voting to detect segment boundaries and compute
a composite divergence score per chat.
"""

import json
import logging
import math
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data Models
# ---------------------------------------------------------------------------

@dataclass
class SegmentRecord:
    """A contiguous block of messages on the same topic."""

    start_message_idx: int
    end_message_idx: int
    topic_label: Optional[str] = None
    summary: Optional[str] = None
    divergence_score: float = 0.0
    anchor_embedding: Optional[List[float]] = None
    parent_segment_id: Optional[int] = None


@dataclass
class DivergenceReport:
    """Per-chat divergence analysis results."""

    overall_score: float = 0.0
    embedding_drift_score: float = 0.0
    topic_entropy_score: float = 0.0
    topic_transition_score: float = 0.0
    llm_relevance_score: Optional[float] = None
    should_split: bool = False
    suggested_split_points: List[int] = field(default_factory=list)
    topic_summaries: List[str] = field(default_factory=list)
    source_last_updated_at: Optional[str] = None
    analysis_version: int = 1
    raw_json: Optional[Dict[str, Any]] = None


@dataclass
class LLMMessageJudgement:
    """LLM classification for a single message."""

    message_idx: int
    relation: str  # CONTINUING, CLARIFYING, DRILLING, BRANCHING, TANGENT, CONCLUDING, RETURNING
    relevance_score: float  # 0-10
    suggested_segment_break: bool = False
    reasoning: Optional[str] = None


# ---------------------------------------------------------------------------
# Text Embedder Interface + Implementations
# ---------------------------------------------------------------------------

class TextEmbedder(ABC):
    """Interface for converting text to vector embeddings."""

    @abstractmethod
    def embed(self, texts: List[str]) -> np.ndarray:
        """
        Embed a list of texts into vectors.

        Parameters
        ----------
        texts : list of str
            Texts to embed.

        Returns
        -------
        np.ndarray
            Array of shape (len(texts), embedding_dim).
        """
        ...


class SentenceTransformerEmbedder(TextEmbedder):
    """Embedder using sentence-transformers library."""

    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        from sentence_transformers import SentenceTransformer

        self.model = SentenceTransformer(model_name)
        logger.info("Loaded sentence-transformers model: %s", model_name)

    def embed(self, texts: List[str]) -> np.ndarray:
        return self.model.encode(texts, show_progress_bar=False)


class SklearnTfidfEmbedder(TextEmbedder):
    """
    Lightweight TF-IDF fallback embedder.

    Does not require downloading any models. Deterministic and fast.
    Used in tests and environments without GPU/large model support.
    """

    def __init__(self, max_features: int = 512):
        from sklearn.feature_extraction.text import TfidfVectorizer

        self._vectorizer = TfidfVectorizer(
            max_features=max_features,
            stop_words="english",
            sublinear_tf=True,
        )
        self._fitted = False

    def embed(self, texts: List[str]) -> np.ndarray:
        if not self._fitted:
            matrix = self._vectorizer.fit_transform(texts)
            self._fitted = True
        else:
            matrix = self._vectorizer.transform(texts)
        return matrix.toarray().astype(np.float32)


def get_embedder(backend: str = "auto") -> TextEmbedder:
    """
    Factory: return the best available embedder.

    Parameters
    ----------
    backend : str
        "auto" (try sentence-transformers, fall back to tfidf),
        "sentence-transformers", or "tfidf".

    Returns
    -------
    TextEmbedder
    """
    if backend == "tfidf":
        return SklearnTfidfEmbedder()

    if backend == "sentence-transformers":
        return SentenceTransformerEmbedder()

    # auto: try sentence-transformers first
    try:
        return SentenceTransformerEmbedder()
    except ImportError:
        logger.info("sentence-transformers not available, using TF-IDF fallback")
        return SklearnTfidfEmbedder()


# ---------------------------------------------------------------------------
# Signal 1: Embedding Drift Analyzer
# ---------------------------------------------------------------------------

class EmbeddingDriftAnalyzer:
    """
    Measures how message embeddings drift from the conversation anchor.

    The anchor is computed from the first N messages (default: 3).
    Cosine distance from anchor is tracked for each subsequent message.
    """

    def __init__(
        self,
        embedder: TextEmbedder,
        anchor_size: int = 3,
        drift_threshold: float = 0.35,
        persistence: int = 2,
    ):
        self.embedder = embedder
        self.anchor_size = anchor_size
        self.drift_threshold = drift_threshold
        self.persistence = persistence

    def compute_drift_curve(
        self, texts: List[str]
    ) -> Tuple[np.ndarray, np.ndarray, Dict[str, float]]:
        """
        Compute cosine distance from anchor for each message.

        Parameters
        ----------
        texts : list of str
            Message texts.

        Returns
        -------
        tuple of (embeddings, drift_curve, metrics)
            - embeddings: (N, D) array
            - drift_curve: (N,) array of cosine distances from anchor
            - metrics: dict with max_drift, mean_drift, drift_velocity, etc.
        """
        if len(texts) < 2:
            embeddings = self.embedder.embed(texts) if texts else np.array([])
            return embeddings, np.zeros(len(texts)), {
                "max_drift": 0.0, "mean_drift": 0.0, "drift_velocity": 0.0,
                "final_drift": 0.0, "return_count": 0,
            }

        embeddings = self.embedder.embed(texts)

        # Compute anchor as mean of first N embeddings
        anchor_n = min(self.anchor_size, len(embeddings))
        anchor = embeddings[:anchor_n].mean(axis=0)
        anchor_norm = np.linalg.norm(anchor)
        if anchor_norm < 1e-10:
            anchor_norm = 1.0

        # Cosine distance from anchor for each message
        drift_curve = np.zeros(len(embeddings))
        for i, emb in enumerate(embeddings):
            emb_norm = np.linalg.norm(emb)
            if emb_norm < 1e-10:
                drift_curve[i] = 1.0
            else:
                cos_sim = np.dot(anchor, emb) / (anchor_norm * emb_norm)
                drift_curve[i] = 1.0 - float(np.clip(cos_sim, -1.0, 1.0))

        # Compute metrics
        max_drift = float(drift_curve.max())
        mean_drift = float(drift_curve.mean())
        final_drift = float(drift_curve[-1])

        # Drift velocity: average absolute change between consecutive messages
        if len(drift_curve) > 1:
            velocity = float(np.abs(np.diff(drift_curve)).mean())
        else:
            velocity = 0.0

        # Return count: how many times drift drops back below threshold after exceeding
        return_count = 0
        above = False
        for d in drift_curve:
            if d >= self.drift_threshold:
                above = True
            elif above:
                return_count += 1
                above = False

        metrics = {
            "max_drift": min(max_drift, 1.0),
            "mean_drift": min(mean_drift, 1.0),
            "drift_velocity": min(velocity, 1.0),
            "final_drift": min(final_drift, 1.0),
            "return_count": return_count,
        }

        return embeddings, drift_curve, metrics

    def detect_changepoints(self, drift_curve: np.ndarray) -> List[int]:
        """
        Detect indices where drift persistently exceeds threshold.

        Parameters
        ----------
        drift_curve : np.ndarray
            Per-message cosine distances.

        Returns
        -------
        list of int
            Message indices identified as changepoints.
        """
        changepoints = []
        consecutive = 0

        for i, d in enumerate(drift_curve):
            if d >= self.drift_threshold:
                consecutive += 1
                if consecutive >= self.persistence:
                    # Mark the first message of the persistent run
                    cp = i - self.persistence + 1
                    if not changepoints or cp > changepoints[-1]:
                        changepoints.append(cp)
            else:
                consecutive = 0

        return changepoints


# ---------------------------------------------------------------------------
# Signal 2: Topic Divergence Analyzer
# ---------------------------------------------------------------------------

class TopicDivergenceAnalyzer:
    """
    Assigns topics to messages and computes entropy/transition metrics.

    Supports BERTopic (primary) and TF-IDF cosine-threshold (fallback).
    """

    def __init__(self, backend: str = "auto"):
        """
        Parameters
        ----------
        backend : str
            "bertopic", "tfidf", or "auto" (try bertopic first).
        """
        self.backend = backend

    def analyze(
        self, texts: List[str]
    ) -> Tuple[List[int], Dict[str, float], List[int]]:
        """
        Assign topics and compute divergence metrics.

        Parameters
        ----------
        texts : list of str
            Message texts.

        Returns
        -------
        tuple of (topic_assignments, metrics, changepoints)
            - topic_assignments: per-message topic IDs
            - metrics: num_topics, topic_entropy, transition_rate, dominant_topic_ratio
            - changepoints: indices where topic changes
        """
        if len(texts) < 2:
            return (
                [0] * len(texts),
                {"num_topics": 1, "topic_entropy": 0.0, "transition_rate": 0.0, "dominant_topic_ratio": 1.0},
                [],
            )

        if self.backend == "bertopic" or (self.backend == "auto" and self._bertopic_available()):
            return self._analyze_bertopic(texts)
        else:
            return self._analyze_tfidf(texts)

    def _bertopic_available(self) -> bool:
        try:
            import bertopic  # noqa: F401
            return True
        except ImportError:
            return False

    def _analyze_bertopic(self, texts: List[str]) -> Tuple[List[int], Dict[str, float], List[int]]:
        from bertopic import BERTopic

        model = BERTopic(min_topic_size=2, verbose=False)
        topics, _ = model.fit_transform(texts)
        return self._compute_topic_metrics(topics)

    def _analyze_tfidf(self, texts: List[str]) -> Tuple[List[int], Dict[str, float], List[int]]:
        """TF-IDF fallback: assign topics via cosine similarity clustering."""
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.metrics.pairwise import cosine_similarity

        vectorizer = TfidfVectorizer(
            max_features=256, stop_words="english", sublinear_tf=True
        )
        tfidf_matrix = vectorizer.fit_transform(texts)

        # Simple sequential topic assignment: start a new topic when
        # cosine similarity to the current topic's centroid drops below threshold
        threshold = 0.15
        topics = [0]
        current_topic = 0
        # Centroid is the mean of vectors assigned to current topic
        centroids = {0: tfidf_matrix[0].toarray().flatten()}
        centroid_counts = {0: 1}

        for i in range(1, len(texts)):
            vec = tfidf_matrix[i].toarray().flatten()
            centroid = centroids[current_topic]
            sim = float(cosine_similarity([vec], [centroid])[0][0])

            if sim < threshold:
                current_topic += 1
                centroids[current_topic] = vec
                centroid_counts[current_topic] = 1
            else:
                # Update running centroid
                n = centroid_counts[current_topic]
                centroids[current_topic] = (centroid * n + vec) / (n + 1)
                centroid_counts[current_topic] = n + 1

            topics.append(current_topic)

        return self._compute_topic_metrics(topics)

    def _compute_topic_metrics(
        self, topics: List[int]
    ) -> Tuple[List[int], Dict[str, float], List[int]]:
        """Compute entropy, transition rate, dominant ratio from topic assignments."""
        unique_topics = set(t for t in topics if t >= 0)  # BERTopic uses -1 for outliers
        num_topics = max(len(unique_topics), 1)

        # Shannon entropy of topic distribution
        from collections import Counter

        counts = Counter(t for t in topics if t >= 0)
        total = sum(counts.values()) or 1
        probs = [c / total for c in counts.values()]
        entropy = -sum(p * math.log2(p) for p in probs if p > 0)

        # Transition rate: fraction of consecutive messages with different topics
        transitions = sum(1 for i in range(1, len(topics)) if topics[i] != topics[i - 1])
        transition_rate = transitions / max(len(topics) - 1, 1)

        # Dominant topic ratio
        dominant_count = max(counts.values()) if counts else len(topics)
        dominant_ratio = dominant_count / max(total, 1)

        # Changepoints: where topic changes
        changepoints = [i for i in range(1, len(topics)) if topics[i] != topics[i - 1]]

        metrics = {
            "num_topics": num_topics,
            "topic_entropy": min(entropy, 10.0),  # reasonable cap
            "transition_rate": min(transition_rate, 1.0),
            "dominant_topic_ratio": min(dominant_ratio, 1.0),
        }

        return topics, metrics, changepoints


# ---------------------------------------------------------------------------
# Signal 3: LLM-as-Judge (optional)
# ---------------------------------------------------------------------------

RELATION_TAXONOMY = [
    "CONTINUING", "CLARIFYING", "DRILLING", "BRANCHING",
    "TANGENT", "CONCLUDING", "RETURNING",
]


class LLMDivergenceAnalyzer:
    """
    Uses Claude to classify each message's relationship to the conversation topic.

    Requires ANTHROPIC_API_KEY environment variable.
    """

    def __init__(self, api_key: Optional[str] = None):
        import os
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        if not self.api_key:
            raise ValueError("ANTHROPIC_API_KEY not set")

    def classify_messages(
        self,
        texts: List[str],
        chat_title: Optional[str] = None,
    ) -> List[LLMMessageJudgement]:
        """
        Classify each message using Claude.

        Parameters
        ----------
        texts : list of str
            Message texts.
        chat_title : str, optional
            Chat title for context.

        Returns
        -------
        list of LLMMessageJudgement
        """
        import anthropic

        client = anthropic.Anthropic(api_key=self.api_key)

        # Build conversation context (truncate long messages)
        truncated = [t[:500] if len(t) > 500 else t for t in texts]
        messages_block = "\n".join(
            f"[MSG {i}] {text}" for i, text in enumerate(truncated)
        )

        prompt = f"""Analyze this conversation and classify each message's relationship to the original topic.

Title: {chat_title or 'Untitled'}

Messages:
{messages_block}

For each message, provide:
- relation: one of {RELATION_TAXONOMY}
- relevance_score: 0-10 (10 = highly relevant to original topic)
- suggested_segment_break: true/false
- reasoning: brief explanation

Respond in JSON array format:
[{{"message_idx": 0, "relation": "CONTINUING", "relevance_score": 8, "suggested_segment_break": false, "reasoning": "..."}}]"""

        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}],
        )

        try:
            text = response.content[0].text
            # Extract JSON from response (handle markdown code blocks)
            if "```" in text:
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
            data = json.loads(text.strip())
        except (json.JSONDecodeError, IndexError, KeyError) as e:
            logger.warning("Failed to parse LLM response: %s", e)
            return []

        judgements = []
        for item in data:
            try:
                judgements.append(
                    LLMMessageJudgement(
                        message_idx=item["message_idx"],
                        relation=item.get("relation", "CONTINUING"),
                        relevance_score=float(item.get("relevance_score", 5.0)),
                        suggested_segment_break=bool(item.get("suggested_segment_break", False)),
                        reasoning=item.get("reasoning"),
                    )
                )
            except (KeyError, ValueError) as e:
                logger.debug("Skipping invalid LLM judgement item: %s", e)

        return judgements


# ---------------------------------------------------------------------------
# Conversation Segmenter (Ensemble)
# ---------------------------------------------------------------------------

class ConversationSegmenter:
    """
    Combines signals from drift, topic, and LLM analyzers to detect
    segment boundaries and compute a composite divergence score.
    """

    def __init__(self, min_segment_messages: int = 3):
        self.min_segment_messages = min_segment_messages

    def detect_boundaries(
        self,
        drift_changepoints: List[int],
        topic_changepoints: List[int],
        llm_judgements: Optional[List[LLMMessageJudgement]] = None,
        num_messages: int = 0,
    ) -> List[int]:
        """
        Ensemble boundary detection via voting.

        A boundary is confirmed if >= 2 signals agree.
        LLM gets an override vote if relevance_score <= 3.0.

        Parameters
        ----------
        drift_changepoints : list of int
            Changepoints from embedding drift.
        topic_changepoints : list of int
            Changepoints from topic modeling.
        llm_judgements : list of LLMMessageJudgement, optional
            LLM per-message judgements.
        num_messages : int
            Total message count.

        Returns
        -------
        list of int
            Confirmed boundary indices.
        """
        # Collect all candidate indices
        candidates = set(drift_changepoints) | set(topic_changepoints)

        if llm_judgements:
            for j in llm_judgements:
                if j.suggested_segment_break:
                    candidates.add(j.message_idx)

        # Vote on each candidate
        confirmed = []
        for idx in sorted(candidates):
            votes = 0
            if idx in drift_changepoints:
                votes += 1
            if idx in topic_changepoints:
                votes += 1
            if llm_judgements:
                for j in llm_judgements:
                    if j.message_idx == idx:
                        if j.suggested_segment_break:
                            votes += 1
                        # LLM override: low relevance forces a boundary
                        if j.relevance_score <= 3.0:
                            votes += 1
                        break

            if votes >= 2:
                confirmed.append(idx)

        # If no LLM data, lower threshold to >= 1 (any single signal)
        # but only if both drift and topic produced candidates
        if not llm_judgements and not confirmed:
            if drift_changepoints or topic_changepoints:
                confirmed = sorted(candidates)

        # Enforce minimum segment length
        filtered = []
        prev = 0
        for boundary in confirmed:
            if boundary - prev >= self.min_segment_messages:
                filtered.append(boundary)
                prev = boundary
        # Also ensure last segment is long enough
        if filtered and num_messages - filtered[-1] < self.min_segment_messages:
            filtered.pop()

        return filtered

    def build_segments(
        self,
        boundaries: List[int],
        num_messages: int,
        topic_assignments: Optional[List[int]] = None,
        embeddings: Optional[np.ndarray] = None,
    ) -> List[SegmentRecord]:
        """
        Convert boundary indices into SegmentRecord objects.

        Parameters
        ----------
        boundaries : list of int
            Confirmed boundary indices.
        num_messages : int
            Total messages.
        topic_assignments : list of int, optional
            Per-message topic IDs for labeling.
        embeddings : np.ndarray, optional
            Message embeddings for anchor computation.

        Returns
        -------
        list of SegmentRecord
        """
        if num_messages == 0:
            return []

        # Build segment ranges
        starts = [0] + boundaries
        ends = boundaries + [num_messages]
        segments = []

        for start, end in zip(starts, ends):
            # Determine topic label from most common topic in range
            label = None
            if topic_assignments:
                from collections import Counter

                segment_topics = topic_assignments[start:end]
                if segment_topics:
                    most_common = Counter(segment_topics).most_common(1)[0][0]
                    label = f"Topic {most_common}"

            # Compute anchor embedding for this segment
            anchor = None
            if embeddings is not None and len(embeddings) > start:
                seg_embeddings = embeddings[start:min(end, len(embeddings))]
                if len(seg_embeddings) > 0:
                    anchor = seg_embeddings.mean(axis=0).tolist()

            segments.append(
                SegmentRecord(
                    start_message_idx=start,
                    end_message_idx=end - 1,  # inclusive
                    topic_label=label,
                    anchor_embedding=anchor,
                )
            )

        return segments

    def compute_divergence_score(
        self,
        drift_metrics: Dict[str, float],
        topic_metrics: Dict[str, float],
    ) -> float:
        """
        Compute composite divergence score from signal metrics.

        Formula:
            composite = (
                0.4 * mean_drift +
                0.2 * normalized_entropy +
                0.2 * transition_rate +
                0.2 * (1 - dominant_topic_ratio)
            )

        Parameters
        ----------
        drift_metrics : dict
            From EmbeddingDriftAnalyzer.
        topic_metrics : dict
            From TopicDivergenceAnalyzer.

        Returns
        -------
        float
            Score in [0.0, 1.0].
        """
        mean_drift = drift_metrics.get("mean_drift", 0.0)
        entropy = topic_metrics.get("topic_entropy", 0.0)
        normalized_entropy = min(entropy / 3.0, 1.0)
        transition_rate = topic_metrics.get("transition_rate", 0.0)
        dominant_ratio = topic_metrics.get("dominant_topic_ratio", 1.0)

        composite = (
            0.4 * mean_drift
            + 0.2 * normalized_entropy
            + 0.2 * transition_rate
            + 0.2 * (1.0 - dominant_ratio)
        )

        return float(np.clip(composite, 0.0, 1.0))


# ---------------------------------------------------------------------------
# Top-Level Service
# ---------------------------------------------------------------------------

class TopicAnalysisService:
    """
    Orchestrates the full topic analysis pipeline.

    Coordinates embedder, drift analyzer, topic analyzer, LLM judge,
    and segmenter. Stores results via the database repository.
    """

    def __init__(
        self,
        db,
        embedder_backend: str = "auto",
        topic_backend: str = "auto",
        use_llm: bool = True,
        drift_threshold: float = 0.35,
        min_segment_messages: int = 3,
    ):
        """
        Parameters
        ----------
        db : Database
            Database instance with .segments repository.
        embedder_backend : str
            "auto", "sentence-transformers", or "tfidf".
        topic_backend : str
            "auto", "bertopic", or "tfidf".
        use_llm : bool
            Whether to use LLM-as-judge signal.
        drift_threshold : float
            Cosine distance threshold for drift changepoints.
        min_segment_messages : int
            Minimum messages per segment.
        """
        self.db = db
        self.use_llm = use_llm

        self.embedder = get_embedder(embedder_backend)
        self.drift_analyzer = EmbeddingDriftAnalyzer(
            self.embedder, drift_threshold=drift_threshold
        )
        self.topic_analyzer = TopicDivergenceAnalyzer(backend=topic_backend)
        self.segmenter = ConversationSegmenter(
            min_segment_messages=min_segment_messages
        )

        # LLM analyzer is lazily created
        self._llm_analyzer = None

    def _get_llm_analyzer(self) -> Optional[LLMDivergenceAnalyzer]:
        """Get or create LLM analyzer (returns None if unavailable)."""
        if not self.use_llm:
            return None
        if self._llm_analyzer is None:
            try:
                self._llm_analyzer = LLMDivergenceAnalyzer()
            except (ValueError, ImportError) as e:
                logger.info("LLM analyzer not available: %s", e)
                return None
        return self._llm_analyzer

    def analyze_chat(self, chat_id: int) -> Optional[DivergenceReport]:
        """
        Run full analysis pipeline on a single chat.

        Parameters
        ----------
        chat_id : int
            Chat ID to analyze.

        Returns
        -------
        DivergenceReport or None
            Analysis results, or None if chat has no messages.
        """
        # Fetch chat data
        chat = self.db.get_chat(chat_id)
        if not chat:
            logger.warning("Chat %d not found", chat_id)
            return None

        messages = chat.get("messages", [])
        if not messages:
            logger.debug("Chat %d has no messages, skipping", chat_id)
            return None

        # Extract text content from messages
        texts = []
        for msg in messages:
            text = msg.get("text") or msg.get("rich_text") or ""
            if isinstance(text, str) and text.strip():
                texts.append(text.strip())
            else:
                texts.append("")  # placeholder to keep indices aligned

        # Filter out empty messages for analysis but keep index mapping
        non_empty_indices = [i for i, t in enumerate(texts) if t]
        non_empty_texts = [texts[i] for i in non_empty_indices]

        if len(non_empty_texts) < 2:
            # Not enough content to analyze meaningfully
            report = DivergenceReport(
                overall_score=0.0,
                source_last_updated_at=chat.get("last_updated_at"),
            )
            self._store_results(chat_id, report, [
                SegmentRecord(start_message_idx=0, end_message_idx=max(len(messages) - 1, 0))
            ], None)
            return report

        # Signal 1: Embedding drift
        embeddings, drift_curve, drift_metrics = self.drift_analyzer.compute_drift_curve(
            non_empty_texts
        )
        drift_changepoints = self.drift_analyzer.detect_changepoints(drift_curve)
        # Map changepoints back to original indices
        drift_cp_original = [non_empty_indices[cp] for cp in drift_changepoints if cp < len(non_empty_indices)]

        # Signal 2: Topic modeling
        topic_assignments_sparse, topic_metrics, topic_changepoints = self.topic_analyzer.analyze(
            non_empty_texts
        )
        topic_cp_original = [non_empty_indices[cp] for cp in topic_changepoints if cp < len(non_empty_indices)]

        # Expand topic assignments back to full message list
        full_topic_assignments = [-1] * len(texts)
        for sparse_idx, orig_idx in enumerate(non_empty_indices):
            if sparse_idx < len(topic_assignments_sparse):
                full_topic_assignments[orig_idx] = topic_assignments_sparse[sparse_idx]

        # Signal 3: LLM (optional)
        llm_judgements = None
        llm_analyzer = self._get_llm_analyzer()
        if llm_analyzer and len(non_empty_texts) >= 3:
            try:
                llm_judgements = llm_analyzer.classify_messages(
                    non_empty_texts, chat_title=chat.get("title")
                )
                # Remap indices
                for j in llm_judgements:
                    if j.message_idx < len(non_empty_indices):
                        j.message_idx = non_empty_indices[j.message_idx]
            except Exception as e:
                logger.warning("LLM analysis failed for chat %d: %s", chat_id, e)
                llm_judgements = None

        # Ensemble boundary detection
        boundaries = self.segmenter.detect_boundaries(
            drift_cp_original,
            topic_cp_original,
            llm_judgements,
            num_messages=len(messages),
        )

        # Build segments
        # Expand embeddings back to full size for anchor computation
        full_embeddings = None
        if embeddings is not None and len(embeddings) > 0:
            dim = embeddings.shape[1] if embeddings.ndim > 1 else embeddings.shape[0]
            full_embeddings = np.zeros((len(texts), dim))
            for sparse_idx, orig_idx in enumerate(non_empty_indices):
                if sparse_idx < len(embeddings):
                    full_embeddings[orig_idx] = embeddings[sparse_idx]

        segments = self.segmenter.build_segments(
            boundaries,
            num_messages=len(messages),
            topic_assignments=full_topic_assignments,
            embeddings=full_embeddings,
        )

        # Compute composite score
        overall_score = self.segmenter.compute_divergence_score(drift_metrics, topic_metrics)

        # Determine should_split
        should_split = overall_score >= 0.6 and len(segments) > 1

        # Build report
        report = DivergenceReport(
            overall_score=overall_score,
            embedding_drift_score=drift_metrics.get("mean_drift", 0.0),
            topic_entropy_score=min(topic_metrics.get("topic_entropy", 0.0) / 3.0, 1.0),
            topic_transition_score=topic_metrics.get("transition_rate", 0.0),
            llm_relevance_score=self._compute_avg_llm_relevance(llm_judgements),
            should_split=should_split,
            suggested_split_points=boundaries,
            source_last_updated_at=chat.get("last_updated_at"),
            raw_json={
                "drift_metrics": drift_metrics,
                "topic_metrics": topic_metrics,
                "boundaries": boundaries,
                "num_non_empty": len(non_empty_texts),
            },
        )

        # Store results
        self._store_results(chat_id, report, segments, llm_judgements)

        return report

    def _compute_avg_llm_relevance(
        self, judgements: Optional[List[LLMMessageJudgement]]
    ) -> Optional[float]:
        """Compute average LLM relevance score, normalized to 0-1."""
        if not judgements:
            return None
        scores = [j.relevance_score for j in judgements]
        if not scores:
            return None
        return 1.0 - (sum(scores) / len(scores) / 10.0)  # invert: low relevance = high divergence

    def _store_results(
        self,
        chat_id: int,
        report: DivergenceReport,
        segments: List[SegmentRecord],
        judgements: Optional[List[LLMMessageJudgement]],
    ) -> None:
        """Persist analysis results to database."""
        report_dict = asdict(report)
        segment_dicts = [asdict(s) for s in segments]
        judgement_dicts = [asdict(j) for j in judgements] if judgements else None

        self.db.segments.upsert_topic_analysis(
            chat_id, report_dict, segment_dicts, judgement_dicts
        )

    def backfill(
        self,
        incremental: bool = True,
        limit: int = 100,
        progress_callback=None,
    ) -> Dict[str, int]:
        """
        Batch-analyze chats that need topic analysis.

        Parameters
        ----------
        incremental : bool
            Only analyze new/updated chats.
        limit : int
            Maximum chats to process.
        progress_callback : callable, optional
            Called with (chat_id, total, current) for progress.

        Returns
        -------
        dict
            Stats: analyzed, skipped, errors.
        """
        chats = self.db.segments.list_chats_needing_topic_analysis(
            incremental=incremental, limit=limit
        )

        stats = {"analyzed": 0, "skipped": 0, "errors": 0}
        total = len(chats)

        for i, chat_info in enumerate(chats):
            chat_id = chat_info["id"]
            try:
                result = self.analyze_chat(chat_id)
                if result:
                    stats["analyzed"] += 1
                else:
                    stats["skipped"] += 1
            except Exception as e:
                logger.error("Error analyzing chat %d: %s", chat_id, e)
                stats["errors"] += 1

            if progress_callback:
                progress_callback(chat_id, total, i + 1)

        logger.info(
            "Backfill complete: %d analyzed, %d skipped, %d errors",
            stats["analyzed"],
            stats["skipped"],
            stats["errors"],
        )
        return stats
