"""
Tests for topic divergence detection and conversation segmentation.
"""
import pytest
import numpy as np
from datetime import datetime
from unittest.mock import MagicMock, patch


# ==================== Test Fixtures ====================

@pytest.fixture
def single_topic_messages():
    """A focused conversation staying on one topic."""
    return [
        {"role": "user", "text": "How do I create a Python virtual environment?"},
        {"role": "assistant", "text": "You can create a virtual environment using python -m venv myenv"},
        {"role": "user", "text": "How do I activate it?"},
        {"role": "assistant", "text": "On Linux/Mac use source myenv/bin/activate, on Windows use myenv\\Scripts\\activate"},
        {"role": "user", "text": "And how do I install packages into it?"},
        {"role": "assistant", "text": "Use pip install package_name while the environment is activated"},
    ]


@pytest.fixture
def tangent_return_messages():
    """Conversation with one tangent that returns to main topic."""
    return [
        {"role": "user", "text": "Help me write a REST API in Python"},
        {"role": "assistant", "text": "I'll help you create a REST API using Flask or FastAPI"},
        {"role": "user", "text": "Let's use Flask. How do I start?"},
        {"role": "assistant", "text": "First install Flask with pip install flask, then create app.py"},
        {"role": "user", "text": "By the way, what's your opinion on tabs vs spaces?"},
        {"role": "assistant", "text": "Most Python developers prefer 4 spaces, as recommended by PEP 8"},
        {"role": "user", "text": "Got it. Back to Flask - how do I add a route?"},
        {"role": "assistant", "text": "Use the @app.route decorator to define routes"},
    ]


@pytest.fixture
def clear_branch_messages():
    """Conversation with a clear topic branch."""
    return [
        {"role": "user", "text": "I need help debugging my Python code"},
        {"role": "assistant", "text": "I'd be happy to help. What error are you seeing?"},
        {"role": "user", "text": "I'm getting a TypeError when calling my function"},
        {"role": "assistant", "text": "Can you share the function code and the full error traceback?"},
        {"role": "user", "text": "Actually, let me ask about something else. Can you help me set up CI/CD?"},
        {"role": "assistant", "text": "Sure! For CI/CD, you could use GitHub Actions, Jenkins, or GitLab CI"},
        {"role": "user", "text": "How do I create a GitHub Actions workflow?"},
        {"role": "assistant", "text": "Create a .github/workflows/main.yml file in your repo"},
    ]


@pytest.fixture
def highly_divergent_messages():
    """Conversation that jumps between multiple unrelated topics."""
    return [
        {"role": "user", "text": "What's the weather like today?"},
        {"role": "assistant", "text": "I don't have access to real-time weather data."},
        {"role": "user", "text": "Can you explain quantum computing?"},
        {"role": "assistant", "text": "Quantum computing uses quantum bits or qubits..."},
        {"role": "user", "text": "How do I make pasta carbonara?"},
        {"role": "assistant", "text": "For authentic carbonara, use guanciale, eggs, and pecorino..."},
        {"role": "user", "text": "What's the capital of Mongolia?"},
        {"role": "assistant", "text": "The capital of Mongolia is Ulaanbaatar."},
    ]


# ==================== Model Tests ====================

class TestModels:
    """Test data models."""
    
    def test_segment_creation(self):
        """Test Segment dataclass."""
        from src.divergence.models import Segment
        
        segment = Segment(
            id="seg-123",
            chat_id=1,
            start_message_idx=0,
            end_message_idx=5,
            summary="Test segment",
        )
        
        assert segment.id == "seg-123"
        assert segment.chat_id == 1
        assert segment.message_count == 6  # 0 to 5 inclusive
        assert segment.divergence_score == 0.0
        assert segment.created_at is not None
    
    def test_segment_to_dict(self):
        """Test Segment serialization."""
        from src.divergence.models import Segment
        
        segment = Segment(
            id="seg-123",
            chat_id=1,
            start_message_idx=0,
            end_message_idx=5,
            summary="Test",
            divergence_score=0.5,
        )
        
        d = segment.to_dict()
        assert d["id"] == "seg-123"
        assert d["divergence_score"] == 0.5
        assert "created_at" in d
    
    def test_divergence_metrics(self):
        """Test DivergenceMetrics defaults."""
        from src.divergence.models import DivergenceMetrics
        
        metrics = DivergenceMetrics()
        assert metrics.max_drift == 0.0
        assert metrics.num_topics == 1
        assert metrics.mean_relevance == 10.0
    
    def test_message_relation_enum(self):
        """Test MessageRelation enum values."""
        from src.divergence.models import MessageRelation
        
        assert MessageRelation.CONTINUING.value == "continuing"
        assert MessageRelation.BRANCHING.value == "branching"


# ==================== Embedding Drift Tests ====================

class TestEmbeddingDrift:
    """Test embedding drift analyzer."""
    
    @pytest.fixture
    def analyzer(self):
        """Create analyzer with mock model."""
        from src.divergence.embedding_drift import EmbeddingDriftAnalyzer
        
        analyzer = EmbeddingDriftAnalyzer()
        return analyzer
    
    def test_embed_empty_text(self, analyzer):
        """Test embedding empty text returns zero vector."""
        # Mock the model
        mock_model = MagicMock()
        mock_model.get_sentence_embedding_dimension.return_value = 384
        analyzer._model = mock_model
        
        result = analyzer.embed("")
        assert isinstance(result, np.ndarray)
        assert len(result) == 384
        assert np.all(result == 0)
    
    def test_compute_drift_metrics(self, analyzer):
        """Test drift metrics computation."""
        drift_scores = [0.0, 0.1, 0.2, 0.3, 0.4, 0.3, 0.2]
        
        metrics = analyzer._compute_metrics(drift_scores)
        
        assert metrics['max_drift'] == 0.4
        assert 0.2 < metrics['mean_drift'] < 0.25
        assert metrics['final_drift'] == 0.2
        assert metrics['return_count'] >= 0
    
    def test_compute_drift_empty(self, analyzer):
        """Test drift metrics with empty scores."""
        metrics = analyzer._compute_metrics([])
        
        assert metrics['max_drift'] == 0.0
        assert metrics['mean_drift'] == 0.0
    
    def test_detect_changepoints_short(self, analyzer):
        """Test changepoint detection with short input."""
        drift_scores = [0.1, 0.2]
        
        changepoints = analyzer.detect_changepoints(drift_scores)
        
        assert changepoints == []  # Too short
    
    def test_detect_changepoints_threshold(self, analyzer):
        """Test changepoint detection with clear threshold crossing."""
        # Drift that stays low then jumps high
        drift_scores = [0.1, 0.1, 0.1, 0.5, 0.6, 0.6, 0.6, 0.6]
        
        changepoints = analyzer.detect_changepoints(
            drift_scores,
            threshold=0.3,
            min_segment_length=2,
        )
        
        # Should detect a changepoint around index 3
        assert len(changepoints) > 0
        assert 3 in changepoints or 4 in changepoints


# ==================== Topic Modeling Tests ====================

class TestTopicModeling:
    """Test topic modeling analyzer."""
    
    def test_topic_entropy_single(self):
        """Test entropy with single topic."""
        from src.divergence.topic_modeling import TopicDivergenceAnalyzer
        
        analyzer = TopicDivergenceAnalyzer()
        entropy = analyzer.compute_topic_entropy([0, 0, 0, 0])
        
        assert entropy == 0.0  # Single topic = 0 entropy
    
    def test_topic_entropy_uniform(self):
        """Test entropy with uniform distribution."""
        from src.divergence.topic_modeling import TopicDivergenceAnalyzer
        
        analyzer = TopicDivergenceAnalyzer()
        # 4 topics, each appearing twice = uniform distribution
        entropy = analyzer.compute_topic_entropy([0, 1, 2, 3, 0, 1, 2, 3])
        
        # Uniform over 4 = log2(4) = 2 bits
        assert abs(entropy - 2.0) < 0.01
    
    def test_extract_segments(self):
        """Test segment extraction from topic assignments."""
        from src.divergence.topic_modeling import TopicDivergenceAnalyzer
        
        analyzer = TopicDivergenceAnalyzer()
        topics = [0, 0, 0, 1, 1, 0, 0]
        
        segments = analyzer._extract_segments(topics)
        
        assert len(segments) == 3
        assert segments[0]['topic_id'] == 0
        assert segments[0]['start_idx'] == 0
        assert segments[0]['end_idx'] == 2
        assert segments[1]['topic_id'] == 1
        assert segments[2]['topic_id'] == 0
    
    def test_get_segment_boundaries(self):
        """Test boundary extraction."""
        from src.divergence.topic_modeling import TopicDivergenceAnalyzer
        
        analyzer = TopicDivergenceAnalyzer()
        topics = [0, 0, 1, 1, 2, 2]
        
        boundaries = analyzer.get_segment_boundaries(topics)
        
        assert boundaries == [2, 4]  # Where topics change
    
    def test_empty_result(self):
        """Test empty result structure."""
        from src.divergence.topic_modeling import TopicDivergenceAnalyzer
        
        analyzer = TopicDivergenceAnalyzer()
        result = analyzer._empty_result(0)
        
        assert result['topics'] == []
        assert result['metrics']['num_topics'] == 1
        assert result['metrics']['topic_entropy'] == 0.0


# ==================== LLM Judge Tests ====================

class TestLLMJudge:
    """Test LLM-as-Judge analyzer."""
    
    def test_format_conversation(self):
        """Test conversation formatting."""
        from src.divergence.llm_judge import LLMDivergenceAnalyzer
        
        analyzer = LLMDivergenceAnalyzer()
        
        messages = [
            {"role": "user", "text": "Hello"},
            {"role": "assistant", "text": "Hi there!"},
        ]
        
        formatted = analyzer._format_conversation(messages, include_indices=True)
        
        assert "[0] USER: Hello" in formatted
        assert "[1] ASSISTANT: Hi there!" in formatted
    
    def test_format_conversation_truncation(self):
        """Test long message truncation."""
        from src.divergence.llm_judge import LLMDivergenceAnalyzer
        
        analyzer = LLMDivergenceAnalyzer()
        
        long_text = "x" * 2000
        messages = [{"role": "user", "text": long_text}]
        
        formatted = analyzer._format_conversation(messages)
        
        assert len(formatted) < len(long_text)
        assert "..." in formatted
    
    def test_message_classification_structure(self):
        """Test MessageClassification dataclass."""
        from src.divergence.models import MessageClassification, MessageRelation
        
        classification = MessageClassification(
            message_idx=5,
            relation=MessageRelation.BRANCHING,
            relevance_score=3.0,
            suggested_segment_break=True,
            reasoning="Topic changed completely",
        )
        
        assert classification.message_idx == 5
        assert classification.relation == MessageRelation.BRANCHING
        assert classification.suggested_segment_break is True
        
        d = classification.to_dict()
        assert d['relation'] == 'branching'


# ==================== Segmenter Tests ====================

class TestSegmenter:
    """Test ensemble segmenter."""
    
    def test_interpret_score(self):
        """Test score interpretation."""
        from src.divergence.segmenter import ConversationSegmenter
        
        segmenter = ConversationSegmenter(use_llm=False)
        
        assert "focused" in segmenter._interpret_score(0.1).lower()
        assert "tangent" in segmenter._interpret_score(0.3).lower()
        assert "divergent" in segmenter._interpret_score(0.9).lower()
    
    def test_create_single_segment(self):
        """Test single segment creation for short chats."""
        from src.divergence.segmenter import ConversationSegmenter
        
        segmenter = ConversationSegmenter(use_llm=False)
        
        messages = [
            {"role": "user", "text": "Hello"},
            {"role": "assistant", "text": "Hi"},
        ]
        
        segment = segmenter._create_single_segment(chat_id=1, messages=messages)
        
        assert segment.chat_id == 1
        assert segment.start_message_idx == 0
        assert segment.end_message_idx == 1
    
    @patch('src.divergence.segmenter.EmbeddingDriftAnalyzer')
    def test_segment_chat_short(self, mock_analyzer_class):
        """Test segmentation with very short chat."""
        from src.divergence.segmenter import ConversationSegmenter
        
        segmenter = ConversationSegmenter(use_llm=False)
        
        messages = [{"role": "user", "text": "Hi"}]
        
        segments = segmenter.segment_chat(
            chat_id=1,
            messages=messages,
            min_segment_messages=3,
        )
        
        # Should return single segment
        assert len(segments) == 1
        assert segments[0].chat_id == 1


# ==================== Database Tests ====================

class TestDivergenceDatabase:
    """Test divergence database operations."""
    
    @pytest.fixture
    def db_conn(self, tmp_path):
        """Create temporary database connection."""
        import sqlite3
        
        db_path = tmp_path / "test.db"
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        
        # Create minimal chat schema for foreign keys
        conn.execute("""
            CREATE TABLE IF NOT EXISTS chats (
                id INTEGER PRIMARY KEY,
                messages_count INTEGER DEFAULT 0,
                last_updated_at TEXT
            )
        """)
        conn.execute("INSERT INTO chats (id, messages_count) VALUES (1, 10)")
        conn.commit()
        
        yield conn
        conn.close()
    
    def test_schema_creation(self, db_conn):
        """Test schema is created correctly."""
        from src.divergence.db import DivergenceDatabase
        
        div_db = DivergenceDatabase(db_conn)
        
        # Check tables exist
        cursor = db_conn.cursor()
        cursor.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name='segments'
        """)
        assert cursor.fetchone() is not None
        
        cursor.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name='divergence_scores'
        """)
        assert cursor.fetchone() is not None
    
    def test_save_and_get_segment(self, db_conn):
        """Test segment save and retrieval."""
        from src.divergence.db import DivergenceDatabase
        from src.divergence.models import Segment
        
        div_db = DivergenceDatabase(db_conn)
        
        segment = Segment(
            id="test-seg-1",
            chat_id=1,
            start_message_idx=0,
            end_message_idx=5,
            summary="Test segment",
            divergence_score=0.3,
        )
        
        div_db.save_segment(segment)
        
        retrieved = div_db.get_segment("test-seg-1")
        
        assert retrieved is not None
        assert retrieved.id == "test-seg-1"
        assert retrieved.chat_id == 1
        assert retrieved.divergence_score == 0.3
    
    def test_save_segment_with_embedding(self, db_conn):
        """Test segment with embedding."""
        from src.divergence.db import DivergenceDatabase
        from src.divergence.models import Segment
        
        div_db = DivergenceDatabase(db_conn)
        
        embedding = np.random.randn(384).astype(np.float32)
        embedding = embedding / np.linalg.norm(embedding)
        
        segment = Segment(
            id="emb-seg-1",
            chat_id=1,
            start_message_idx=0,
            end_message_idx=5,
            anchor_embedding=embedding,
        )
        
        div_db.save_segment(segment)
        retrieved = div_db.get_segment("emb-seg-1")
        
        assert retrieved.anchor_embedding is not None
        assert len(retrieved.anchor_embedding) == 384
        # Check embedding values are close
        assert np.allclose(retrieved.anchor_embedding, embedding, atol=1e-6)
    
    def test_save_divergence_report(self, db_conn):
        """Test divergence report save and retrieval."""
        from src.divergence.db import DivergenceDatabase
        from src.divergence.models import DivergenceReport, DivergenceMetrics
        
        div_db = DivergenceDatabase(db_conn)
        
        metrics = DivergenceMetrics(
            max_drift=0.5,
            mean_drift=0.3,
            num_topics=3,
        )
        
        report = DivergenceReport(
            chat_id=1,
            overall_score=0.45,
            embedding_drift_score=0.3,
            topic_entropy_score=0.5,
            topic_transition_score=0.4,
            metrics=metrics,
            num_segments=3,
            should_split=False,
            interpretation="Moderate divergence",
        )
        
        div_db.save_divergence_report(report)
        retrieved = div_db.get_divergence_report(1)
        
        assert retrieved is not None
        assert retrieved.overall_score == 0.45
        assert retrieved.metrics.max_drift == 0.5
        assert retrieved.interpretation == "Moderate divergence"
    
    def test_queue_operations(self, db_conn):
        """Test processing queue operations."""
        from src.divergence.db import DivergenceDatabase
        
        div_db = DivergenceDatabase(db_conn)
        
        # Queue a chat
        div_db.queue_chat_for_processing(1, priority=5)
        
        # Get next pending
        chat_id = div_db.get_next_pending_chat()
        assert chat_id == 1
        
        # Should be marked as processing now
        stats = div_db.get_queue_stats()
        assert stats['processing'] == 1
        
        # Mark complete
        div_db.mark_processing_complete(1)
        stats = div_db.get_queue_stats()
        assert stats['completed'] == 1


# ==================== Integration Tests ====================

class TestIntegration:
    """Integration tests with real (mocked) data flow."""
    
    def test_full_analysis_flow(self, single_topic_messages):
        """Test complete analysis flow."""
        from src.divergence.segmenter import ConversationSegmenter
        
        segmenter = ConversationSegmenter(use_llm=False)
        
        # This will use real embedding model if available
        try:
            report, segments = segmenter.analyze_chat_full(
                chat_id=1,
                messages=single_topic_messages,
                generate_summaries=False,
            )
            
            # Single topic should have low divergence
            assert report.overall_score < 0.5
            assert len(segments) >= 1
            
        except ImportError:
            pytest.skip("sentence-transformers not installed")
    
    def test_find_best_link_target(self):
        """Test segment linking."""
        from src.divergence.segmenter import find_best_link_target
        from src.divergence.models import Segment, LinkType
        
        # Create segments with embeddings
        embedding1 = np.array([1.0, 0.0, 0.0])
        embedding2 = np.array([0.9, 0.1, 0.0])  # Similar to 1
        embedding3 = np.array([0.0, 1.0, 0.0])  # Different
        
        source = Segment(
            id="source",
            chat_id=1,
            start_message_idx=0,
            end_message_idx=5,
            anchor_embedding=embedding1,
        )
        
        targets = [
            Segment(
                id="target1",
                chat_id=2,
                start_message_idx=0,
                end_message_idx=5,
                anchor_embedding=embedding2,
            ),
            Segment(
                id="target2",
                chat_id=3,
                start_message_idx=0,
                end_message_idx=5,
                anchor_embedding=embedding3,
            ),
        ]
        
        result = find_best_link_target(source, targets)
        
        assert result is not None
        assert result['target_segment_id'] == 'target1'  # Most similar
        assert result['similarity_score'] >= 0.9


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
