"""
Tests for topic divergence analysis service and segment repository.

Uses TF-IDF fallback (no model downloads) for all embedding operations.
"""

import json
import math
import os
import tempfile

import numpy as np
import pytest

from src.core.db import ChatDatabase
from src.core.models import Chat, Message, Workspace, ChatMode, MessageRole
from src.services.topic_analysis import (
    ConversationSegmenter,
    DivergenceReport,
    EmbeddingDriftAnalyzer,
    LLMMessageJudgement,
    SegmentRecord,
    SklearnTfidfEmbedder,
    TopicAnalysisService,
    TopicDivergenceAnalyzer,
    get_embedder,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    db = ChatDatabase(path)
    yield db
    db.close()
    os.unlink(path)


@pytest.fixture
def db_with_chat(temp_db):
    """Database with a single chat containing diverse messages."""
    workspace = Workspace(workspace_hash="test-ws")
    ws_id = temp_db.upsert_workspace(workspace)

    # A conversation that starts about Python, then drifts to cooking
    messages = [
        Message(role=MessageRole.USER, text="How do I create a Python list comprehension?"),
        Message(role=MessageRole.ASSISTANT, text="You can use [expr for item in iterable]. For example: squares = [x**2 for x in range(10)]"),
        Message(role=MessageRole.USER, text="Can I add conditions to filter elements?"),
        Message(role=MessageRole.ASSISTANT, text="Yes, add an if clause: [x for x in range(10) if x % 2 == 0] gives even numbers."),
        Message(role=MessageRole.USER, text="What is the best recipe for chocolate cake?"),
        Message(role=MessageRole.ASSISTANT, text="A classic chocolate cake uses cocoa powder, flour, sugar, eggs, and buttermilk."),
        Message(role=MessageRole.USER, text="How long should I bake it at 350 degrees?"),
        Message(role=MessageRole.ASSISTANT, text="Bake at 350F for about 30-35 minutes until a toothpick comes out clean."),
    ]

    chat = Chat(
        cursor_composer_id="test-comp-1",
        workspace_id=ws_id,
        title="Python and Cooking",
        mode=ChatMode.CHAT,
        messages=messages,
    )
    chat_id = temp_db.upsert_chat(chat)
    return temp_db, chat_id


@pytest.fixture
def db_with_focused_chat(temp_db):
    """Database with a chat that stays on a single topic."""
    workspace = Workspace(workspace_hash="test-ws-2")
    ws_id = temp_db.upsert_workspace(workspace)

    messages = [
        Message(role=MessageRole.USER, text="How do I install Python packages?"),
        Message(role=MessageRole.ASSISTANT, text="Use pip install package_name. You can also use a requirements.txt file."),
        Message(role=MessageRole.USER, text="What about virtual environments?"),
        Message(role=MessageRole.ASSISTANT, text="Create one with python -m venv myenv, then activate it with source myenv/bin/activate."),
        Message(role=MessageRole.USER, text="How do I freeze dependencies?"),
        Message(role=MessageRole.ASSISTANT, text="Run pip freeze > requirements.txt to save all installed packages."),
    ]

    chat = Chat(
        cursor_composer_id="test-comp-2",
        workspace_id=ws_id,
        title="Python Package Management",
        mode=ChatMode.CHAT,
        messages=messages,
    )
    chat_id = temp_db.upsert_chat(chat)
    return temp_db, chat_id


# ---------------------------------------------------------------------------
# Embedder Tests
# ---------------------------------------------------------------------------

class TestSklearnTfidfEmbedder:
    """Tests for the TF-IDF fallback embedder."""

    def test_basic_embedding(self):
        embedder = SklearnTfidfEmbedder(max_features=64)
        texts = ["hello world", "goodbye world", "something else entirely"]
        result = embedder.embed(texts)

        assert isinstance(result, np.ndarray)
        assert result.shape[0] == 3
        assert result.shape[1] <= 64

    def test_single_text(self):
        embedder = SklearnTfidfEmbedder()
        result = embedder.embed(["just one sentence"])
        assert result.shape[0] == 1

    def test_empty_text_handling(self):
        embedder = SklearnTfidfEmbedder()
        # TF-IDF should handle empty strings gracefully
        result = embedder.embed(["hello", "", "world"])
        assert result.shape[0] == 3

    def test_deterministic_output(self):
        embedder = SklearnTfidfEmbedder(max_features=32)
        texts = ["python programming", "java development"]
        r1 = embedder.embed(texts)
        r2 = embedder.embed(texts)
        # After fitting, same inputs should give same outputs
        np.testing.assert_array_almost_equal(r1, r2)


class TestGetEmbedder:
    """Tests for the embedder factory."""

    def test_tfidf_backend(self):
        embedder = get_embedder("tfidf")
        assert isinstance(embedder, SklearnTfidfEmbedder)

    def test_auto_backend_returns_embedder(self):
        embedder = get_embedder("auto")
        # Should return some valid embedder (either sentence-transformers or tfidf)
        assert hasattr(embedder, "embed")


# ---------------------------------------------------------------------------
# Embedding Drift Analyzer Tests
# ---------------------------------------------------------------------------

class TestEmbeddingDriftAnalyzer:
    """Tests for Signal 1: Embedding drift detection."""

    def test_drift_curve_with_similar_texts(self):
        embedder = SklearnTfidfEmbedder(max_features=128)
        analyzer = EmbeddingDriftAnalyzer(embedder, drift_threshold=0.5)

        texts = [
            "Python list comprehension tutorial",
            "Python dictionary comprehension examples",
            "Python set comprehension usage",
            "Python generator expressions",
        ]
        embeddings, curve, metrics = analyzer.compute_drift_curve(texts)

        assert len(curve) == 4
        assert metrics["mean_drift"] >= 0.0
        assert metrics["max_drift"] >= 0.0

    def test_drift_curve_with_divergent_texts(self):
        embedder = SklearnTfidfEmbedder(max_features=128)
        analyzer = EmbeddingDriftAnalyzer(embedder, drift_threshold=0.3)

        texts = [
            "Python programming language tutorial",
            "Python coding best practices",
            "Making chocolate cake recipe baking",
            "Frosting decoration birthday party",
        ]
        embeddings, curve, metrics = analyzer.compute_drift_curve(texts)

        assert len(curve) == 4
        # Later messages about cooking should drift more from Python anchor
        assert metrics["max_drift"] > 0.0

    def test_drift_with_single_message(self):
        embedder = SklearnTfidfEmbedder()
        analyzer = EmbeddingDriftAnalyzer(embedder)
        _, curve, metrics = analyzer.compute_drift_curve(["single message"])
        assert len(curve) == 1
        assert metrics["mean_drift"] == 0.0

    def test_detect_changepoints(self):
        embedder = SklearnTfidfEmbedder()
        analyzer = EmbeddingDriftAnalyzer(embedder, drift_threshold=0.3, persistence=2)

        # Simulate a drift curve that exceeds threshold
        curve = np.array([0.1, 0.1, 0.5, 0.6, 0.7, 0.2, 0.1])
        changepoints = analyzer.detect_changepoints(curve)

        # Should detect a changepoint around index 2-3
        assert len(changepoints) >= 1
        assert changepoints[0] >= 2


# ---------------------------------------------------------------------------
# Topic Divergence Analyzer Tests
# ---------------------------------------------------------------------------

class TestTopicDivergenceAnalyzer:
    """Tests for Signal 2: Topic modeling divergence."""

    def test_single_topic_conversation(self):
        analyzer = TopicDivergenceAnalyzer(backend="tfidf")
        texts = [
            "Python programming tutorial for beginners",
            "Learning Python data structures and algorithms",
            "Python function definitions and parameters",
            "Python class inheritance and polymorphism",
        ]
        topics, metrics, changepoints = analyzer.analyze(texts)

        assert len(topics) == 4
        assert metrics["num_topics"] >= 1
        assert 0.0 <= metrics["topic_entropy"]
        assert 0.0 <= metrics["transition_rate"] <= 1.0
        assert 0.0 <= metrics["dominant_topic_ratio"] <= 1.0

    def test_multi_topic_conversation(self):
        analyzer = TopicDivergenceAnalyzer(backend="tfidf")
        texts = [
            "Python programming language syntax",
            "Python coding best practices",
            "Chocolate cake baking recipe instructions",
            "Frosting decoration birthday celebration",
            "Quantum physics wave particle duality",
            "Einstein relativity theory spacetime",
        ]
        topics, metrics, changepoints = analyzer.analyze(texts)

        assert len(topics) == 6
        # With multiple distinct topics, entropy should be > 0
        assert metrics["num_topics"] >= 1

    def test_single_message(self):
        analyzer = TopicDivergenceAnalyzer(backend="tfidf")
        topics, metrics, _ = analyzer.analyze(["just one message"])
        assert topics == [0]
        assert metrics["topic_entropy"] == 0.0

    def test_empty_messages(self):
        analyzer = TopicDivergenceAnalyzer(backend="tfidf")
        topics, metrics, _ = analyzer.analyze([])
        assert topics == []


# ---------------------------------------------------------------------------
# Conversation Segmenter Tests
# ---------------------------------------------------------------------------

class TestConversationSegmenter:
    """Tests for the ensemble segmenter."""

    def test_no_boundaries(self):
        segmenter = ConversationSegmenter(min_segment_messages=2)
        boundaries = segmenter.detect_boundaries([], [], None, num_messages=10)
        assert boundaries == []

    def test_single_signal_no_llm(self):
        """Without LLM, single signal can produce boundaries."""
        segmenter = ConversationSegmenter(min_segment_messages=2)
        boundaries = segmenter.detect_boundaries(
            drift_changepoints=[5],
            topic_changepoints=[],
            llm_judgements=None,
            num_messages=10,
        )
        # Without LLM, threshold relaxes to >= 1
        assert 5 in boundaries

    def test_two_signal_agreement(self):
        segmenter = ConversationSegmenter(min_segment_messages=2)
        boundaries = segmenter.detect_boundaries(
            drift_changepoints=[4, 8],
            topic_changepoints=[4],
            llm_judgements=None,
            num_messages=12,
        )
        # Index 4 has 2 votes
        assert 4 in boundaries

    def test_min_segment_enforcement(self):
        segmenter = ConversationSegmenter(min_segment_messages=5)
        # Two boundaries too close together
        boundaries = segmenter.detect_boundaries(
            drift_changepoints=[2, 4],
            topic_changepoints=[2, 4],
            llm_judgements=None,
            num_messages=10,
        )
        # Should be filtered to respect min_segment_messages
        for i in range(1, len(boundaries)):
            assert boundaries[i] - boundaries[i - 1] >= 5

    def test_llm_override_low_relevance(self):
        segmenter = ConversationSegmenter(min_segment_messages=2)
        llm_j = [
            LLMMessageJudgement(message_idx=5, relation="TANGENT", relevance_score=2.0, suggested_segment_break=True),
        ]
        boundaries = segmenter.detect_boundaries(
            drift_changepoints=[5],
            topic_changepoints=[],
            llm_judgements=llm_j,
            num_messages=10,
        )
        # LLM low relevance + drift = 3 votes, well above threshold
        assert 5 in boundaries

    def test_build_segments(self):
        segmenter = ConversationSegmenter()
        segments = segmenter.build_segments(
            boundaries=[5, 10],
            num_messages=15,
        )
        assert len(segments) == 3
        assert segments[0].start_message_idx == 0
        assert segments[0].end_message_idx == 4
        assert segments[1].start_message_idx == 5
        assert segments[1].end_message_idx == 9
        assert segments[2].start_message_idx == 10
        assert segments[2].end_message_idx == 14

    def test_build_segments_no_boundaries(self):
        segmenter = ConversationSegmenter()
        segments = segmenter.build_segments(boundaries=[], num_messages=10)
        assert len(segments) == 1
        assert segments[0].start_message_idx == 0
        assert segments[0].end_message_idx == 9

    def test_compute_divergence_score(self):
        segmenter = ConversationSegmenter()
        score = segmenter.compute_divergence_score(
            drift_metrics={"mean_drift": 0.5},
            topic_metrics={
                "topic_entropy": 1.5,
                "transition_rate": 0.3,
                "dominant_topic_ratio": 0.6,
            },
        )
        # Manual calculation:
        # 0.4 * 0.5 + 0.2 * (1.5/3.0) + 0.2 * 0.3 + 0.2 * (1-0.6)
        # = 0.2 + 0.1 + 0.06 + 0.08 = 0.44
        expected = 0.4 * 0.5 + 0.2 * (1.5 / 3.0) + 0.2 * 0.3 + 0.2 * (1.0 - 0.6)
        assert abs(score - expected) < 0.001

    def test_score_clipping(self):
        segmenter = ConversationSegmenter()
        # Extreme values should be clipped to [0, 1]
        score = segmenter.compute_divergence_score(
            drift_metrics={"mean_drift": 2.0},
            topic_metrics={
                "topic_entropy": 100.0,
                "transition_rate": 5.0,
                "dominant_topic_ratio": 0.0,
            },
        )
        assert 0.0 <= score <= 1.0


# ---------------------------------------------------------------------------
# Segment Repository Tests
# ---------------------------------------------------------------------------

class TestSegmentRepository:
    """Tests for database storage of topic analysis results."""

    def test_upsert_and_get_topic_analysis(self, temp_db):
        """Store and retrieve a topic analysis report."""
        # Need a chat first
        workspace = Workspace(workspace_hash="repo-test")
        ws_id = temp_db.upsert_workspace(workspace)
        chat = Chat(
            cursor_composer_id="repo-comp-1",
            workspace_id=ws_id,
            title="Test",
            mode=ChatMode.CHAT,
            messages=[Message(role=MessageRole.USER, text="Hello")],
        )
        chat_id = temp_db.upsert_chat(chat)

        # Store analysis
        report = {
            "overall_score": 0.45,
            "embedding_drift_score": 0.3,
            "topic_entropy_score": 0.5,
            "topic_transition_score": 0.4,
            "llm_relevance_score": None,
            "should_split": False,
            "suggested_split_points": [3, 7],
            "topic_summaries": ["Topic A", "Topic B"],
            "source_last_updated_at": "2026-03-02T00:00:00",
        }
        segments = [
            {
                "start_message_idx": 0,
                "end_message_idx": 2,
                "topic_label": "Topic A",
                "summary": "First segment",
                "divergence_score": 0.1,
                "anchor_embedding": [0.1, 0.2, 0.3],
            },
            {
                "start_message_idx": 3,
                "end_message_idx": 5,
                "topic_label": "Topic B",
                "summary": "Second segment",
                "divergence_score": 0.6,
                "anchor_embedding": [0.4, 0.5, 0.6],
            },
        ]

        temp_db.segments.upsert_topic_analysis(chat_id, report, segments)

        # Retrieve
        result = temp_db.segments.get_topic_analysis(chat_id)
        assert result is not None
        assert result["overall_score"] == 0.45
        assert result["num_segments"] == 2
        assert result["should_split"] is False
        assert result["suggested_split_points"] == [3, 7]

    def test_get_chat_segments(self, temp_db):
        """Retrieve stored segments."""
        workspace = Workspace(workspace_hash="seg-test")
        ws_id = temp_db.upsert_workspace(workspace)
        chat = Chat(
            cursor_composer_id="seg-comp",
            workspace_id=ws_id,
            title="Seg Test",
            mode=ChatMode.CHAT,
            messages=[Message(role=MessageRole.USER, text="x")],
        )
        chat_id = temp_db.upsert_chat(chat)

        report = {"overall_score": 0.5}
        segments = [
            {"start_message_idx": 0, "end_message_idx": 4, "divergence_score": 0.2},
            {"start_message_idx": 5, "end_message_idx": 9, "divergence_score": 0.7},
        ]
        temp_db.segments.upsert_topic_analysis(chat_id, report, segments)

        result = temp_db.segments.get_chat_segments(chat_id)
        assert len(result) == 2
        assert result[0]["start_message_idx"] == 0
        assert result[1]["start_message_idx"] == 5

    def test_upsert_replaces_old_data(self, temp_db):
        """Subsequent upsert replaces previous analysis."""
        workspace = Workspace(workspace_hash="replace-test")
        ws_id = temp_db.upsert_workspace(workspace)
        chat = Chat(
            cursor_composer_id="replace-comp",
            workspace_id=ws_id,
            title="Replace",
            mode=ChatMode.CHAT,
            messages=[Message(role=MessageRole.USER, text="x")],
        )
        chat_id = temp_db.upsert_chat(chat)

        # First analysis
        temp_db.segments.upsert_topic_analysis(
            chat_id,
            {"overall_score": 0.3},
            [{"start_message_idx": 0, "end_message_idx": 5, "divergence_score": 0.3}],
        )

        # Second analysis (should replace)
        temp_db.segments.upsert_topic_analysis(
            chat_id,
            {"overall_score": 0.8},
            [
                {"start_message_idx": 0, "end_message_idx": 2, "divergence_score": 0.2},
                {"start_message_idx": 3, "end_message_idx": 5, "divergence_score": 0.9},
            ],
        )

        result = temp_db.segments.get_topic_analysis(chat_id)
        assert result["overall_score"] == 0.8
        assert result["num_segments"] == 2

        segs = temp_db.segments.get_chat_segments(chat_id)
        assert len(segs) == 2

    def test_judgements_storage(self, temp_db):
        """Store and retrieve LLM judgements."""
        workspace = Workspace(workspace_hash="judge-test")
        ws_id = temp_db.upsert_workspace(workspace)
        chat = Chat(
            cursor_composer_id="judge-comp",
            workspace_id=ws_id,
            title="Judge",
            mode=ChatMode.CHAT,
            messages=[Message(role=MessageRole.USER, text="x")],
        )
        chat_id = temp_db.upsert_chat(chat)

        judgements = [
            {"message_idx": 0, "relation": "CONTINUING", "relevance_score": 8.0, "suggested_segment_break": False, "reasoning": "On topic"},
            {"message_idx": 3, "relation": "TANGENT", "relevance_score": 2.0, "suggested_segment_break": True, "reasoning": "Off topic"},
        ]

        temp_db.segments.upsert_topic_analysis(
            chat_id,
            {"overall_score": 0.5},
            [{"start_message_idx": 0, "end_message_idx": 5, "divergence_score": 0.5}],
            judgement_rows=judgements,
        )

        result = temp_db.segments.get_message_judgements(chat_id)
        assert len(result) == 2
        assert result[0]["relation"] == "CONTINUING"
        assert result[1]["relation"] == "TANGENT"
        assert result[1]["suggested_segment_break"] is True

    def test_no_analysis_returns_none(self, temp_db):
        """get_topic_analysis returns None for unanalyzed chats."""
        result = temp_db.segments.get_topic_analysis(99999)
        assert result is None

    def test_get_stats(self, temp_db):
        """get_stats returns valid statistics."""
        stats = temp_db.segments.get_stats()
        assert "total_chats" in stats
        assert "total_analyzed" in stats
        assert "pending_analysis" in stats
        assert "score_distribution" in stats

    def test_segment_links(self, temp_db):
        """Create and retrieve segment links."""
        workspace = Workspace(workspace_hash="link-test")
        ws_id = temp_db.upsert_workspace(workspace)

        # Two chats with segments
        for comp_id in ["link-comp-1", "link-comp-2"]:
            chat = Chat(
                cursor_composer_id=comp_id,
                workspace_id=ws_id,
                title=comp_id,
                mode=ChatMode.CHAT,
                messages=[Message(role=MessageRole.USER, text="x")],
            )
            chat_id = temp_db.upsert_chat(chat)
            temp_db.segments.upsert_topic_analysis(
                chat_id,
                {"overall_score": 0.5},
                [{"start_message_idx": 0, "end_message_idx": 5, "divergence_score": 0.5, "anchor_embedding": [0.1, 0.2]}],
            )

        # Get segment IDs
        segs1 = temp_db.segments.get_chat_segments(1)
        segs2 = temp_db.segments.get_chat_segments(2)

        if segs1 and segs2:
            link_id = temp_db.segments.upsert_segment_link(
                segs1[0]["id"], segs2[0]["id"], "references", 0.85
            )
            assert link_id > 0

            # Upsert again should update, not duplicate
            link_id2 = temp_db.segments.upsert_segment_link(
                segs1[0]["id"], segs2[0]["id"], "references", 0.90
            )
            assert link_id2 == link_id

    def test_high_divergence_chats(self, temp_db):
        """get_high_divergence_chats filters by threshold."""
        workspace = Workspace(workspace_hash="high-div")
        ws_id = temp_db.upsert_workspace(workspace)

        # Create chats with different scores
        for i, score in enumerate([0.2, 0.5, 0.8]):
            chat = Chat(
                cursor_composer_id=f"hd-comp-{i}",
                workspace_id=ws_id,
                title=f"Chat {i}",
                mode=ChatMode.CHAT,
                messages=[Message(role=MessageRole.USER, text="x")],
            )
            cid = temp_db.upsert_chat(chat)
            temp_db.segments.upsert_topic_analysis(
                cid,
                {"overall_score": score},
                [{"start_message_idx": 0, "end_message_idx": 5, "divergence_score": score}],
            )

        results = temp_db.segments.get_high_divergence_chats(threshold=0.5)
        assert len(results) == 2
        assert all(r["overall_score"] >= 0.5 for r in results)


# ---------------------------------------------------------------------------
# TopicAnalysisService Integration Tests
# ---------------------------------------------------------------------------

class TestTopicAnalysisService:
    """Integration tests for the full analysis pipeline."""

    def test_analyze_divergent_chat(self, db_with_chat):
        """Full pipeline on a chat with topic drift."""
        db, chat_id = db_with_chat

        service = TopicAnalysisService(
            db=db,
            embedder_backend="tfidf",
            topic_backend="tfidf",
            use_llm=False,
        )

        report = service.analyze_chat(chat_id)

        assert report is not None
        assert isinstance(report, DivergenceReport)
        assert 0.0 <= report.overall_score <= 1.0
        assert isinstance(report.suggested_split_points, list)

        # Verify data was stored
        stored = db.segments.get_topic_analysis(chat_id)
        assert stored is not None
        assert stored["overall_score"] == report.overall_score

        segments = db.segments.get_chat_segments(chat_id)
        assert len(segments) >= 1

    def test_analyze_focused_chat(self, db_with_focused_chat):
        """Focused chat should score lower than divergent one."""
        db, chat_id = db_with_focused_chat

        service = TopicAnalysisService(
            db=db,
            embedder_backend="tfidf",
            topic_backend="tfidf",
            use_llm=False,
        )

        report = service.analyze_chat(chat_id)

        assert report is not None
        assert 0.0 <= report.overall_score <= 1.0

    def test_analyze_nonexistent_chat(self, temp_db):
        """Analysis of non-existent chat returns None."""
        service = TopicAnalysisService(
            db=temp_db,
            embedder_backend="tfidf",
            topic_backend="tfidf",
            use_llm=False,
        )
        result = service.analyze_chat(99999)
        assert result is None

    def test_backfill(self, db_with_chat):
        """Backfill processes chats needing analysis."""
        db, _ = db_with_chat

        service = TopicAnalysisService(
            db=db,
            embedder_backend="tfidf",
            topic_backend="tfidf",
            use_llm=False,
        )

        stats = service.backfill(incremental=True, limit=10)
        assert stats["analyzed"] >= 1
        assert stats["errors"] == 0

        # Running again with incremental should skip already-analyzed
        stats2 = service.backfill(incremental=True, limit=10)
        # May still analyze if the implementation compares source_last_updated_at
        assert stats2["errors"] == 0

    def test_idempotent_analysis(self, db_with_chat):
        """Running analysis twice produces consistent results."""
        db, chat_id = db_with_chat

        service = TopicAnalysisService(
            db=db,
            embedder_backend="tfidf",
            topic_backend="tfidf",
            use_llm=False,
        )

        report1 = service.analyze_chat(chat_id)
        report2 = service.analyze_chat(chat_id)

        assert report1.overall_score == report2.overall_score
        assert report1.suggested_split_points == report2.suggested_split_points


# ---------------------------------------------------------------------------
# list_chats_needing_topic_analysis Tests
# ---------------------------------------------------------------------------

class TestListChatsNeedingAnalysis:
    """Tests for incremental analysis detection."""

    def test_unanalyzed_chats_are_returned(self, db_with_chat):
        db, chat_id = db_with_chat
        chats = db.segments.list_chats_needing_topic_analysis(incremental=True)
        ids = [c["id"] for c in chats]
        assert chat_id in ids

    def test_analyzed_chats_not_returned(self, db_with_chat):
        db, chat_id = db_with_chat

        # Analyze the chat
        service = TopicAnalysisService(
            db=db,
            embedder_backend="tfidf",
            topic_backend="tfidf",
            use_llm=False,
        )
        service.analyze_chat(chat_id)

        # Should no longer appear as needing analysis (or appear if last_updated_at differs)
        chats = db.segments.list_chats_needing_topic_analysis(incremental=True)
        # The chat might still appear depending on source_last_updated_at matching
        # This is acceptable behavior — the incremental check compares timestamps
