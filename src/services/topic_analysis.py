"""
Topic divergence detection & conversation segmentation.

Implements three analyzers:
- Embedding drift (semantic drift over time)
- Topic modeling (BERTopic, with a lightweight fallback backend)
- LLM-as-judge (Anthropic/Claude)

Stores results in the local SQLite database via ChatDatabase.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

from src.core.db import ChatDatabase

logger = logging.getLogger(__name__)


# ============================================================
# Utilities
# ============================================================


def _now_iso() -> str:
    return datetime.now().isoformat()


def _cosine_distance(a: np.ndarray, b: np.ndarray) -> float:
    # embeddings expected to be normalized; still handle numerical drift
    denom = (np.linalg.norm(a) * np.linalg.norm(b))
    if denom == 0:
        return 1.0
    sim = float(np.dot(a, b) / denom)
    sim = max(-1.0, min(1.0, sim))
    return 1.0 - sim


def _json_dumps(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True)


def _safe_mean(values: Sequence[float]) -> float:
    vals = [v for v in values if v is not None]
    return float(np.mean(vals)) if vals else 0.0


# ============================================================
# Embedding drift (Approach 1)
# ============================================================


class TextEmbedder:
    """Minimal embedder interface."""

    def encode(self, texts: List[str], normalize: bool = True) -> np.ndarray:  # (n, d)
        raise NotImplementedError


class SentenceTransformerEmbedder(TextEmbedder):
    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        from sentence_transformers import SentenceTransformer  # lazy import

        self._model = SentenceTransformer(model_name)

    def encode(self, texts: List[str], normalize: bool = True) -> np.ndarray:
        return np.asarray(self._model.encode(texts, normalize_embeddings=normalize))


class SklearnTfidfEmbedder(TextEmbedder):
    """
    Lightweight deterministic embedder for tests/offline.

    Fits TF-IDF on the provided texts each call.
    """

    def encode(self, texts: List[str], normalize: bool = True) -> np.ndarray:
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.preprocessing import normalize as sk_normalize

        vec = TfidfVectorizer(min_df=1, max_features=4096)
        mat = vec.fit_transform(texts)
        arr = mat.toarray().astype(np.float32)
        if normalize:
            arr = sk_normalize(arr, norm="l2")
        return arr


class EmbeddingDriftAnalyzer:
    def __init__(self, embedder: Optional[TextEmbedder] = None, model_name: str = "all-MiniLM-L6-v2"):
        self.embedder = embedder or SentenceTransformerEmbedder(model_name=model_name)

    def embed(self, text: str) -> np.ndarray:
        return self.embedder.encode([text], normalize=True)[0]

    def embed_messages(self, messages: List[str]) -> np.ndarray:
        embeddings = self.embedder.encode(messages, normalize=True)
        if len(embeddings) == 0:
            return np.zeros((1,), dtype=np.float32)
        return np.mean(embeddings, axis=0)

    def embed_message_texts(self, message_texts: List[Optional[str]]) -> Tuple[List[Optional[np.ndarray]], List[int]]:
        """
        Embed all non-empty message texts in one pass.

        Returns:
          (embeddings_by_index, valid_indices)
        """
        valid_indices = [i for i, t in enumerate(message_texts) if t and t.strip()]
        if not valid_indices:
            return ([None for _ in message_texts], [])
        texts = [message_texts[i].strip() for i in valid_indices]  # type: ignore[union-attr]
        embs = self.embedder.encode(texts, normalize=True)
        by_idx: List[Optional[np.ndarray]] = [None for _ in message_texts]
        for i, emb in zip(valid_indices, embs):
            by_idx[i] = np.asarray(emb)
        return by_idx, valid_indices

    def compute_drift_curve(
        self,
        message_texts: List[Optional[str]],
        anchor_window: int = 3,
        rolling_window: int = 1,
    ) -> Dict[str, Any]:
        embs_by_idx, valid_indices = self.embed_message_texts(message_texts)
        if not valid_indices:
            return {
                "anchor_embedding": None,
                "drift_scores": [None for _ in message_texts],
                "metrics": {
                    "max_drift": 0.0,
                    "mean_drift": 0.0,
                    "drift_velocity": 0.0,
                    "final_drift": 0.0,
                    "return_count": 0,
                },
            }

        anchor_count = max(1, anchor_window)
        anchor_indices = valid_indices[:anchor_count]
        anchor_vecs = [embs_by_idx[i] for i in anchor_indices if embs_by_idx[i] is not None]
        anchor_embedding = np.mean(np.stack(anchor_vecs, axis=0), axis=0) if anchor_vecs else np.zeros((1,), dtype=np.float32)

        drift_scores: List[Optional[float]] = [None for _ in message_texts]
        for idx in valid_indices:
            start = max(0, idx - rolling_window + 1)
            window_vecs = [embs_by_idx[j] for j in range(start, idx + 1) if embs_by_idx[j] is not None]
            if not window_vecs:
                continue
            cur = np.mean(np.stack(window_vecs, axis=0), axis=0)
            drift_scores[idx] = _cosine_distance(anchor_embedding, cur)

        valid_scores = [s for s in drift_scores if s is not None]
        if len(valid_scores) >= 2:
            deltas = [abs(valid_scores[i] - valid_scores[i - 1]) for i in range(1, len(valid_scores))]
            drift_velocity = float(np.mean(deltas)) if deltas else 0.0
        else:
            drift_velocity = 0.0

        # "return_count": count significant drops after a rise
        return_count = 0
        last = None
        last_trend = None  # "up" / "down"
        peak = None
        for s in valid_scores:
            if last is None:
                last = s
                peak = s
                continue
            if s > last + 0.05:
                last_trend = "up"
                peak = max(peak or s, s)
            elif s < last - 0.05:
                if last_trend == "up" and peak is not None and (peak - s) >= 0.10:
                    return_count += 1
                last_trend = "down"
            last = s

        return {
            "anchor_embedding": anchor_embedding,
            "drift_scores": drift_scores,
            "metrics": {
                "max_drift": float(max(valid_scores)) if valid_scores else 0.0,
                "mean_drift": float(np.mean(valid_scores)) if valid_scores else 0.0,
                "drift_velocity": drift_velocity,
                "final_drift": float(valid_scores[-1]) if valid_scores else 0.0,
                "return_count": int(return_count),
            },
        }

    def detect_changepoints(
        self,
        drift_scores: List[Optional[float]],
        threshold: float = 0.3,
        min_persistence: int = 2,
        min_segment_length: int = 3,
    ) -> List[int]:
        """
        Simple threshold + persistence:
        - mark a changepoint at the start of a run where drift >= threshold
          for min_persistence messages.
        """
        points: List[int] = []
        i = 0
        last_cp = 0
        while i < len(drift_scores):
            s = drift_scores[i]
            if s is None or s < threshold:
                i += 1
                continue

            run_start = i
            run_len = 0
            while i < len(drift_scores) and drift_scores[i] is not None and drift_scores[i] >= threshold:
                run_len += 1
                i += 1

            if run_len >= min_persistence:
                # If the run starts too early, pick the earliest point in the run
                # that satisfies min segment length from the last changepoint.
                candidate = max(run_start, last_cp + min_segment_length)
                # candidate must still be within the run and leave enough persistence
                if candidate < (run_start + run_len) and (run_start + run_len - candidate) >= min_persistence:
                    points.append(candidate)
                    last_cp = candidate
        return points


# ============================================================
# Topic modeling (Approach 2)
# ============================================================


class TopicDivergenceAnalyzer:
    def __init__(self, backend: str = "bertopic"):
        self.backend = backend
        self._topic_model = None

        if backend == "bertopic":
            from bertopic import BERTopic  # lazy import

            self._topic_model = BERTopic(
                embedding_model="all-MiniLM-L6-v2",
                min_topic_size=2,
                nr_topics="auto",
            )

    def analyze_chat(self, message_texts: List[Optional[str]]) -> Dict[str, Any]:
        valid = [(i, t.strip()) for i, t in enumerate(message_texts) if t and t.strip()]
        topics_full: List[Optional[int]] = [None for _ in message_texts]

        if len(valid) < 2:
            return {
                "topics": topics_full,
                "topic_labels": {},
                "metrics": {
                    "num_topics": 0,
                    "topic_entropy": 0.0,
                    "transition_rate": 0.0,
                    "dominant_topic_ratio": 1.0 if valid else 0.0,
                },
                "segments": [],
            }

        texts = [t for _, t in valid]

        if self.backend == "bertopic":
            topics, _ = self._topic_model.fit_transform(texts)
            topics = list(map(int, topics))
            labels = self._labels_from_bertopic(set(topics))
        else:
            # lightweight fallback: TF-IDF + cosine-threshold topic runs
            from sklearn.feature_extraction.text import TfidfVectorizer
            from sklearn.preprocessing import normalize as sk_normalize

            vec = TfidfVectorizer(min_df=1, max_features=4096)
            X = vec.fit_transform(texts).toarray().astype(np.float32)
            X = sk_normalize(X, norm="l2")

            topics = []
            cur_topic = 0
            topics.append(cur_topic)
            for i in range(1, len(texts)):
                prev = X[i - 1]
                cur = X[i]
                sim = float(np.dot(prev, cur))
                # Heuristic: low similarity => new topic
                if sim < 0.25:
                    cur_topic += 1
                topics.append(cur_topic)

            labels = {tid: f"topic-{tid}" for tid in set(topics)}

        for (orig_idx, _), topic_id in zip(valid, topics):
            topics_full[orig_idx] = topic_id

        # metrics (ignore None)
        topic_ids = [t for t in topics_full if t is not None]
        counts: Dict[int, int] = {}
        for t in topic_ids:
            counts[int(t)] = counts.get(int(t), 0) + 1
        total = len(topic_ids)
        probs = [c / total for c in counts.values()] if total else []
        topic_entropy = float(-sum(p * np.log2(p) for p in probs if p > 0)) if probs else 0.0
        dominant_topic_ratio = float(max(probs)) if probs else 0.0

        transitions = 0
        prev = None
        for t in topics_full:
            if t is None:
                continue
            if prev is not None and t != prev:
                transitions += 1
            prev = t
        transition_rate = float(transitions / max(1, (len(topic_ids) - 1))) if topic_ids else 0.0

        segments = self.extract_segments(topics_full)
        return {
            "topics": topics_full,
            "topic_labels": labels,
            "metrics": {
                "num_topics": len(set(topic_ids)),
                "topic_entropy": topic_entropy,
                "transition_rate": transition_rate,
                "dominant_topic_ratio": dominant_topic_ratio,
            },
            "segments": segments,
        }

    def _labels_from_bertopic(self, topic_ids: set[int]) -> Dict[int, str]:
        labels: Dict[int, str] = {}
        for tid in topic_ids:
            if tid == -1:
                labels[tid] = "outlier"
                continue
            words = self._topic_model.get_topic(tid) or []
            top = [w for w, _ in words[:3]]
            labels[tid] = ", ".join(top) if top else f"topic-{tid}"
        return labels

    def extract_segments(self, topics_full: List[Optional[int]]) -> List[Dict[str, Any]]:
        segments: List[Dict[str, Any]] = []
        start = None
        cur = None
        for i, t in enumerate(topics_full):
            if t is None:
                continue
            if cur is None:
                cur = t
                start = i
                continue
            if t != cur:
                segments.append({"start_idx": start, "end_idx": i - 1, "topic_id": cur})
                cur = t
                start = i
        if cur is not None and start is not None:
            segments.append({"start_idx": start, "end_idx": len(topics_full) - 1, "topic_id": cur})
        return segments


# ============================================================
# LLM judge (Approach 3)
# ============================================================


@dataclass(frozen=True)
class LLMMessageJudgement:
    relation: str
    relevance_score: float  # 0-10
    suggested_segment_break: bool
    reasoning: str


class LLMDivergenceAnalyzer:
    def __init__(self, model: str = "claude-sonnet-4-20250514"):
        import anthropic  # lazy import

        self.client = anthropic.Anthropic()
        self.model = model

    def _format_conversation(self, messages: List[Dict[str, Any]]) -> str:
        parts = []
        for m in messages:
            role = m.get("role", "")
            text = (m.get("text") or m.get("rich_text") or "").strip()
            if not text:
                continue
            parts.append(f"{role}: {text}")
        return "\n".join(parts)

    def classify_message(
        self,
        conversation_so_far: List[Dict[str, Any]],
        current_message: Dict[str, Any],
        original_anchor: str,
    ) -> LLMMessageJudgement:
        import json as _json

        prompt = f"""Analyze how this message relates to the conversation's original topic.

Original topic/question:
{original_anchor}

Conversation so far (most recent first is NOT required; this is chronological):
{self._format_conversation(conversation_so_far[-10:])}

Current message to classify:
{(current_message.get("text") or current_message.get("rich_text") or "").strip()}

Classify this message as one of:
- CONTINUING: Directly addressing the original topic
- CLARIFYING: Asking for clarification to better address the topic
- DRILLING: Going deeper into a subtopic (still related, but narrower)
- BRANCHING: Starting a new, different topic
- TANGENT: Brief aside, likely to return
- CONCLUDING: Wrapping up the current topic
- RETURNING: Coming back to a previous topic after a departure

Respond in JSON with these keys:
{{
  "relation": "...",
  "relevance_score": 0-10,
  "suggested_segment_break": true/false,
  "reasoning": "..."
}}
"""

        msg = self.client.messages.create(
            model=self.model,
            max_tokens=400,
            temperature=0.2,
            messages=[{"role": "user", "content": prompt}],
        )

        text = ""
        for block in msg.content:
            if getattr(block, "type", None) == "text":
                text += block.text
        # best-effort JSON extraction
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise ValueError(f"LLM did not return JSON: {text[:200]}")

        data = _json.loads(text[start : end + 1])
        return LLMMessageJudgement(
            relation=str(data.get("relation", "CONTINUING")),
            relevance_score=float(data.get("relevance_score", 5)),
            suggested_segment_break=bool(data.get("suggested_segment_break", False)),
            reasoning=str(data.get("reasoning", "")),
        )

    def summarize_segment(self, segment_text: str) -> Tuple[str, Optional[str]]:
        """
        Returns (summary, topic_label).
        """
        import json as _json

        prompt = f"""Summarize this conversation segment in 1-3 sentences and provide a short topic label (2-6 words).

Segment:
{segment_text}

Respond in JSON:
{{
  "summary": "...",
  "topic_label": "..."
}}
"""
        msg = self.client.messages.create(
            model=self.model,
            max_tokens=250,
            temperature=0.2,
            messages=[{"role": "user", "content": prompt}],
        )
        text = ""
        for block in msg.content:
            if getattr(block, "type", None) == "text":
                text += block.text
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            return (segment_text[:200].strip(), None)
        data = _json.loads(text[start : end + 1])
        return (str(data.get("summary", "")).strip(), str(data.get("topic_label", "")).strip() or None)


# ============================================================
# Segmentation (Ensemble)
# ============================================================


@dataclass
class SegmentRecord:
    start_message_idx: int
    end_message_idx: int
    anchor_embedding: List[float]
    summary: str
    topic_label: Optional[str]
    parent_segment_idx: Optional[int]
    divergence_score: float


@dataclass
class DivergenceReport:
    chat_id: int
    overall_score: float  # 0-1
    embedding_drift_score: float
    topic_entropy_score: float
    topic_transition_score: float
    llm_relevance_score: Optional[float]
    num_segments: int
    should_split: bool
    suggested_split_points: List[int]
    topic_summaries: List[str]
    raw: Dict[str, Any]


class ConversationSegmenter:
    def __init__(
        self,
        embedding_analyzer: Optional[EmbeddingDriftAnalyzer] = None,
        topic_analyzer: Optional[TopicDivergenceAnalyzer] = None,
        llm_analyzer: Optional[LLMDivergenceAnalyzer] = None,
    ):
        self.embedding_analyzer = embedding_analyzer or EmbeddingDriftAnalyzer()
        self.topic_analyzer = topic_analyzer or TopicDivergenceAnalyzer()
        self.llm_analyzer = llm_analyzer

    def compute_divergence_score(
        self,
        message_texts: List[Optional[str]],
        include_llm: bool = False,
        llm_judgements: Optional[List[Optional[LLMMessageJudgement]]] = None,
    ) -> Dict[str, Any]:
        embedding_metrics = self.embedding_analyzer.compute_drift_curve(message_texts)
        topic_metrics = self.topic_analyzer.analyze_chat(message_texts)

        mean_drift = float(embedding_metrics["metrics"]["mean_drift"])
        topic_entropy = float(topic_metrics["metrics"]["topic_entropy"])
        transition_rate = float(topic_metrics["metrics"]["transition_rate"])
        dominant = float(topic_metrics["metrics"]["dominant_topic_ratio"])

        llm_mean_relevance = None
        if include_llm and llm_judgements:
            rels = [j.relevance_score for j in llm_judgements if j is not None]
            llm_mean_relevance = float(np.mean(rels)) if rels else None

        # Normalize: topic entropy is ~0..log2(k); cap around 3 for typical chat sizes
        composite = (
            0.4 * mean_drift
            + 0.2 * min(1.0, topic_entropy / 3.0)
            + 0.2 * min(1.0, transition_rate)
            + 0.2 * (1.0 - dominant)
        )
        composite = float(max(0.0, min(1.0, composite)))

        return {
            "composite_score": composite,
            "embedding_metrics": embedding_metrics,
            "topic_metrics": topic_metrics,
            "llm_mean_relevance": llm_mean_relevance,
            "interpretation": self._interpret_score(composite),
        }

    def _interpret_score(self, score: float) -> str:
        if score < 0.2:
            return "Highly focused - single topic throughout"
        if score < 0.4:
            return "Mostly focused with minor tangents"
        if score < 0.6:
            return "Moderate divergence - multiple related topics"
        if score < 0.8:
            return "Significant divergence - distinct topic branches"
        return "Highly divergent - consider splitting into child chats"

    def segment_chat(
        self,
        messages: List[Dict[str, Any]],
        drift_threshold: float = 0.35,
        min_segment_messages: int = 3,
        include_llm: bool = True,
    ) -> Tuple[List[SegmentRecord], DivergenceReport, List[Optional[LLMMessageJudgement]]]:
        message_texts = [
            (m.get("text") or m.get("rich_text") or "").strip() or None for m in messages
        ]

        embs_by_idx, _valid_indices = self.embedding_analyzer.embed_message_texts(message_texts)

        drift = self.embedding_analyzer.compute_drift_curve(message_texts)
        drift_scores = drift["drift_scores"]
        drift_cps = self.embedding_analyzer.detect_changepoints(
            drift_scores,
            threshold=drift_threshold,
            min_persistence=2,
            min_segment_length=min_segment_messages,
        )

        topic = self.topic_analyzer.analyze_chat(message_texts)
        topics_full = topic["topics"]
        topic_cps = []
        prev = None
        for i, t in enumerate(topics_full):
            if t is None:
                continue
            if prev is not None and t != prev:
                topic_cps.append(i)
            prev = t

        llm_judgements: List[Optional[LLMMessageJudgement]] = [None for _ in messages]
        llm_cps: List[int] = []
        if include_llm and self.llm_analyzer is not None and len(messages) >= 2:
            anchor = (messages[0].get("text") or messages[0].get("rich_text") or "").strip()
            if not anchor:
                anchor = (messages[1].get("text") or messages[1].get("rich_text") or "").strip()
            anchor = anchor or "Conversation start"

            so_far: List[Dict[str, Any]] = []
            for i, m in enumerate(messages):
                text = (m.get("text") or m.get("rich_text") or "").strip()
                if not text:
                    so_far.append(m)
                    continue
                try:
                    j = self.llm_analyzer.classify_message(so_far, m, anchor)
                    llm_judgements[i] = j
                    if j.suggested_segment_break:
                        llm_cps.append(i)
                except Exception as e:
                    logger.debug("LLM judge failed at message %d: %s", i, e)
                so_far.append(m)

        # Ensemble boundary decision
        candidate_points = sorted(set(drift_cps + topic_cps + llm_cps))
        confirmed: List[int] = []
        def _has_near(x: int, pts: List[int], radius: int = 1) -> bool:
            return any(abs(p - x) <= radius for p in pts)

        for idx in candidate_points:
            signals = 0
            if _has_near(idx, drift_cps, radius=1):
                signals += 1
            if _has_near(idx, topic_cps, radius=1):
                signals += 1
            if _has_near(idx, llm_cps, radius=0):
                signals += 1

            llm = llm_judgements[idx] if 0 <= idx < len(llm_judgements) else None
            llm_override = bool(llm and llm.suggested_segment_break and llm.relevance_score <= 3.0)

            # If LLM is disabled, allow topic transitions supported by high drift at the same index.
            if self.llm_analyzer is None and signals == 1 and _has_near(idx, topic_cps, radius=0):
                ds = drift_scores[idx]
                if ds is not None and ds >= drift_threshold:
                    signals = 2

            if signals >= 2 or llm_override:
                confirmed.append(idx)

        # Enforce min segment length
        boundaries = [0] + [b for b in confirmed if b >= min_segment_messages]
        boundaries = sorted(set(boundaries))
        filtered = [boundaries[0]]
        for b in boundaries[1:]:
            if (b - filtered[-1]) >= min_segment_messages:
                filtered.append(b)
        boundaries = filtered

        segments: List[SegmentRecord] = []
        for seg_i, start in enumerate(boundaries):
            end = (boundaries[seg_i + 1] - 1) if seg_i + 1 < len(boundaries) else (len(messages) - 1)
            if end < start:
                continue

            seg_texts = [t for t in message_texts[start : end + 1] if t]
            seg_text_joined = "\n\n".join(seg_texts)
            seg_vecs = [embs_by_idx[i] for i in range(start, end + 1) if embs_by_idx[i] is not None]
            if seg_vecs:
                anchor_emb = np.mean(np.stack(seg_vecs, axis=0), axis=0).astype(np.float32)
            else:
                # Unknown dim; store empty list
                anchor_emb = np.zeros((1,), dtype=np.float32)

            summary = seg_text_joined[:240].strip() if seg_text_joined else ""
            topic_label = None
            if include_llm and self.llm_analyzer is not None and seg_text_joined.strip():
                try:
                    summary, topic_label = self.llm_analyzer.summarize_segment(seg_text_joined[:8000])
                except Exception as e:
                    logger.debug("LLM summary failed for segment %d: %s", seg_i, e)

            divergence_score = float(drift_scores[start]) if drift_scores[start] is not None else 0.0
            segments.append(
                SegmentRecord(
                    start_message_idx=int(start),
                    end_message_idx=int(end),
                    anchor_embedding=[float(x) for x in anchor_emb.tolist()] if anchor_emb.size > 1 else [],
                    summary=summary,
                    topic_label=topic_label,
                    parent_segment_idx=(seg_i - 1) if seg_i > 0 else None,
                    divergence_score=divergence_score,
                )
            )

        div = self.compute_divergence_score(
            message_texts,
            include_llm=include_llm and self.llm_analyzer is not None,
            llm_judgements=llm_judgements,
        )

        overall = float(div["composite_score"])
        should_split = overall >= 0.6 or (len(segments) >= 3 and overall >= 0.5)
        suggested_split_points = [s.start_message_idx for s in segments[1:]]

        report = DivergenceReport(
            chat_id=-1,
            overall_score=overall,
            embedding_drift_score=float(div["embedding_metrics"]["metrics"]["mean_drift"]),
            topic_entropy_score=float(div["topic_metrics"]["metrics"]["topic_entropy"]),
            topic_transition_score=float(div["topic_metrics"]["metrics"]["transition_rate"]),
            llm_relevance_score=div.get("llm_mean_relevance"),
            num_segments=len(segments),
            should_split=should_split,
            suggested_split_points=suggested_split_points,
            topic_summaries=[s.summary for s in segments],
            raw={
                "embedding": {
                    "metrics": div["embedding_metrics"]["metrics"],
                    "drift_scores": div["embedding_metrics"]["drift_scores"],
                },
                "topic": {
                    "metrics": div["topic_metrics"]["metrics"],
                    "topics": div["topic_metrics"]["topics"],
                    "topic_labels": div["topic_metrics"]["topic_labels"],
                },
                "llm": [
                    None
                    if j is None
                    else {
                        "relation": j.relation,
                        "relevance_score": j.relevance_score,
                        "suggested_segment_break": j.suggested_segment_break,
                        "reasoning": j.reasoning,
                    }
                    for j in llm_judgements
                ],
                "interpretation": div["interpretation"],
                "boundaries": {
                    "drift": drift_cps,
                    "topic": topic_cps,
                    "llm": llm_cps,
                    "confirmed": confirmed,
                    "final": suggested_split_points,
                },
            },
        )
        return segments, report, llm_judgements


# ============================================================
# Persistence + orchestration
# ============================================================


class TopicAnalysisService:
    def __init__(
        self,
        db: ChatDatabase,
        segmenter: Optional[ConversationSegmenter] = None,
    ):
        self.db = db
        self.segmenter = segmenter or ConversationSegmenter()

    def analyze_chat(
        self,
        chat_id: int,
        drift_threshold: float = 0.35,
        min_segment_messages: int = 3,
        include_llm: bool = True,
    ) -> DivergenceReport:
        chat = self.db.get_chat(chat_id)
        if not chat:
            raise ValueError(f"Chat {chat_id} not found")

        messages = chat.get("messages", [])
        if not messages:
            report = DivergenceReport(
                chat_id=chat_id,
                overall_score=0.0,
                embedding_drift_score=0.0,
                topic_entropy_score=0.0,
                topic_transition_score=0.0,
                llm_relevance_score=None,
                num_segments=0,
                should_split=False,
                suggested_split_points=[],
                topic_summaries=[],
                raw={"error": "empty chat"},
            )
            self.db.upsert_topic_analysis(chat_id, report, [], llm_rows=[])
            return report

        segments, report, llm_judgements = self.segmenter.segment_chat(
            messages,
            drift_threshold=drift_threshold,
            min_segment_messages=min_segment_messages,
            include_llm=include_llm,
        )
        report.chat_id = chat_id  # type: ignore[misc]

        # Persist
        llm_rows = []
        for idx, j in enumerate(llm_judgements):
            if j is None:
                continue
            llm_rows.append(
                {
                    "message_idx": idx,
                    "relation": j.relation,
                    "relevance_score": j.relevance_score,
                    "suggested_segment_break": 1 if j.suggested_segment_break else 0,
                    "reasoning": j.reasoning,
                }
            )
        self.db.upsert_topic_analysis(chat_id, report, segments, llm_rows=llm_rows)
        return report

    def backfill(
        self,
        incremental: bool = True,
        include_llm: bool = True,
        limit: int = 100000,
    ) -> Dict[str, int]:
        stats = {"processed": 0, "skipped": 0, "errors": 0}
        chat_ids = self.db.list_chats_needing_topic_analysis(incremental=incremental, limit=limit)

        for cid in chat_ids:
            try:
                self.analyze_chat(cid, include_llm=include_llm)
                stats["processed"] += 1
            except Exception as e:
                logger.error("Topic analysis failed for chat %d: %s", cid, e)
                stats["errors"] += 1
        return stats


def find_best_link_target(source_segment_embedding: List[float], candidate_segments: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Best-match linking across segments using cosine similarity.
    """
    src = np.asarray(source_segment_embedding, dtype=np.float32)
    best = None
    best_score = -1.0
    for seg in candidate_segments:
        emb = seg.get("anchor_embedding")
        if not emb:
            continue
        tgt = np.asarray(emb, dtype=np.float32)
        sim = 1.0 - _cosine_distance(src, tgt)
        if sim > best_score:
            best_score = sim
            best = seg
    if not best:
        return {"target_segment_id": None, "similarity_score": 0.0, "link_type": "references"}
    return {"target_segment_id": best["id"], "similarity_score": float(best_score), "link_type": "references"}

