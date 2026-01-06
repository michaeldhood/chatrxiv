"""
Tests for topic divergence + conversation segmentation.
"""

import os
import tempfile
from datetime import datetime

import pytest

from src.core.db import ChatDatabase
from src.core.models import Chat, Message, Workspace, ChatMode, MessageRole
from src.services.topic_analysis import (
    TopicAnalysisService,
    ConversationSegmenter,
    EmbeddingDriftAnalyzer,
    TopicDivergenceAnalyzer,
    SklearnTfidfEmbedder,
)


@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    db = ChatDatabase(path)
    yield db
    db.close()
    os.unlink(path)


def _insert_chat(temp_db: ChatDatabase, composer_id: str, texts: list[str]) -> int:
    workspace_id = temp_db.upsert_workspace(Workspace(workspace_hash=f"ws-{composer_id}"))
    chat = Chat(
        cursor_composer_id=composer_id,
        workspace_id=workspace_id,
        title=f"Chat {composer_id}",
        mode=ChatMode.CHAT,
        created_at=datetime.now(),
        last_updated_at=datetime.now(),
        messages=[
            Message(role=(MessageRole.USER if i % 2 == 0 else MessageRole.ASSISTANT), text=t)
            for i, t in enumerate(texts)
        ],
    )
    return temp_db.upsert_chat(chat)


def _analysis_service(temp_db: ChatDatabase) -> TopicAnalysisService:
    # Use deterministic lightweight backends (no model downloads, no BERTopic).
    segmenter = ConversationSegmenter(
        embedding_analyzer=EmbeddingDriftAnalyzer(embedder=SklearnTfidfEmbedder()),
        topic_analyzer=TopicDivergenceAnalyzer(backend="tfidf"),
        llm_analyzer=None,
    )
    return TopicAnalysisService(temp_db, segmenter=segmenter)


def test_divergence_score_ordering_and_persistence(temp_db: ChatDatabase):
    """
    Relative ordering should hold across archetypes:
      focused < tangent < branch < meandering
    """
    focused_id = _insert_chat(
        temp_db,
        "focused",
        [
            "How do I write a Python function to parse JSON?",
            "Use json.loads, validate fields, and handle exceptions.",
            "Should I use dataclasses for the parsed structure?",
            "Yes, dataclasses can help with type hints and defaults.",
            "How do I add unit tests for this parsing function?",
            "Use pytest, cover valid/invalid payloads, and edge cases.",
        ],
    )

    tangent_id = _insert_chat(
        temp_db,
        "tangent",
        [
            "Help me write a Python function to parse JSON.",
            "Use json.loads and validate required keys.",
            "What about nested objects and lists?",
            "Recursively validate or use pydantic/dataclasses.",
            "By the way, what's a good coffee grinder?",
            "Back to Python: how do I test invalid JSON input?",
        ],
    )

    branch_id = _insert_chat(
        temp_db,
        "branch",
        [
            "Help me write a Python function to parse JSON.",
            "Use json.loads and validate required keys.",
            "Can you show an example with dataclasses?",
            "Sure: define a dataclass and map dict -> dataclass.",
            "Switching topics: how do I deploy this as a Kubernetes job?",
            "Use a Docker image, write a Job manifest, configure resources.",
            "How do I set up a CronJob schedule for it?",
            "Use a CronJob with schedule, jobTemplate, and limits.",
        ],
    )

    meander_id = _insert_chat(
        temp_db,
        "meander",
        [
            "Explain options trading greeks in simple terms.",
            "What's the best way to season a cast iron pan?",
            "How does an electric guitar pickup work?",
            "Write a short poem about winter storms.",
            "How do I change a tire safely?",
            "What are the causes of inflation?",
            "Recommend a sci-fi novel and why.",
            "How do I configure a router firewall?",
        ],
    )

    svc = _analysis_service(temp_db)

    focused = svc.analyze_chat(focused_id, include_llm=False)
    tangent = svc.analyze_chat(tangent_id, include_llm=False)
    branch = svc.analyze_chat(branch_id, include_llm=False)
    meander = svc.analyze_chat(meander_id, include_llm=False)

    assert focused.overall_score <= tangent.overall_score
    assert tangent.overall_score <= branch.overall_score
    assert branch.overall_score <= meander.overall_score

    # sanity bounds
    assert 0.0 <= focused.overall_score <= 1.0
    assert 0.0 <= meander.overall_score <= 1.0

    # segmentation expectations (soft, but should generally hold)
    assert focused.num_segments >= 1
    assert branch.num_segments >= 2
    assert meander.num_segments >= 2

    # persistence: analysis row + segments should be stored
    stored = temp_db.get_topic_analysis(branch_id)
    assert stored is not None
    stored_segments = temp_db.get_chat_segments(branch_id)
    assert len(stored_segments) == branch.num_segments
    assert stored_segments[0]["start_message_idx"] == 0

