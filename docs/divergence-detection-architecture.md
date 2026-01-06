# Topic Divergence Detection & Conversation Segmentation Architecture

## Overview

This document describes the architecture for detecting topic divergence in chat conversations and identifying natural segment boundaries. The system enables:

1. **Divergence Scoring**: Measure how much a conversation drifts from its original topic
2. **Segment Detection**: Identify natural break points where topics change
3. **Cross-Chat Linking**: Find related conversations via segment similarity
4. **Split Recommendations**: Suggest when conversations should be split into child chats

## Module Structure

```
src/divergence/
├── __init__.py           # Public API exports
├── models.py             # Data models (Segment, SegmentLink, DivergenceReport)
├── embedding_drift.py    # Approach 1: Semantic embedding drift analysis
├── topic_modeling.py     # Approach 2: BERTopic-based topic modeling
├── llm_judge.py          # Approach 3: Claude-as-Judge classification
├── segmenter.py          # Ensemble segmenter combining all approaches
├── db.py                 # Database layer for divergence data
└── processor.py          # Batch and background processing infrastructure
```

## Data Models

### Core Entities

```python
@dataclass
class Segment:
    """A contiguous segment of conversation on a single topic."""
    id: str
    chat_id: int
    start_message_idx: int
    end_message_idx: int
    anchor_embedding: np.ndarray  # For similarity matching
    summary: str                   # LLM-generated summary
    topic_label: str              # Human-readable topic
    parent_segment_id: str        # For hierarchical topics
    divergence_score: float       # 0-1 divergence from parent

@dataclass
class SegmentLink:
    """Link between two segments (same or different chats)."""
    id: str
    source_segment_id: str
    target_segment_id: str
    link_type: LinkType           # continues, references, branches_from, resolves
    similarity_score: float

@dataclass
class DivergenceReport:
    """Complete divergence analysis for a chat."""
    chat_id: int
    overall_score: float          # 0 = focused, 1 = divergent
    embedding_drift_score: float
    topic_entropy_score: float
    topic_transition_score: float
    llm_relevance_score: float
    num_segments: int
    segments: list[Segment]
    should_split: bool
    suggested_split_points: list[int]
```

## Analysis Approaches

### Approach 1: Embedding Drift Analysis

Uses sentence embeddings to measure semantic drift from the conversation anchor.

**How it works:**
1. Embed all messages using sentence-transformers (default: all-MiniLM-L6-v2)
2. Compute anchor embedding from first N messages
3. Measure cosine distance from anchor for each subsequent message
4. Track drift curve over time

**Metrics:**
- `max_drift`: Furthest point from anchor (0-1)
- `mean_drift`: Average distance across conversation
- `drift_velocity`: Rate of drift change
- `return_count`: Times conversation returned to anchor

**Changepoint Detection:**
- Threshold-based with persistence requirement
- Detects when drift exceeds threshold for sustained period
- Also detects "returns" to the anchor topic

### Approach 2: Topic Modeling with BERTopic

Extracts discrete topics and measures topic diversity.

**How it works:**
1. Fit BERTopic model on conversation messages
2. Assign each message to a topic
3. Compute topic entropy and transition rates

**Metrics:**
- `num_topics`: Count of distinct topics
- `topic_entropy`: Shannon entropy of topic distribution (higher = more diverse)
- `transition_rate`: Frequency of topic changes
- `dominant_topic_ratio`: Concentration in primary topic

**Segment Extraction:**
- Groups contiguous messages with same topic
- Provides topic labels from top words

### Approach 3: LLM-as-Judge

Uses Claude to classify each message's relationship to the conversation anchor.

**Classification Categories:**
- `CONTINUING`: Stays on main topic
- `CLARIFYING`: Asking for clarification
- `DRILLING`: Going deeper into subtopic
- `BRANCHING`: Starting new topic
- `TANGENT`: Brief aside
- `CONCLUDING`: Wrapping up
- `RETURNING`: Coming back to earlier topic

**Output per message:**
- Relation classification
- Relevance score (0-10)
- Segment break suggestion
- Reasoning

**Metrics:**
- `mean_relevance`: Average relevance to anchor
- `branch_count`: Number of BRANCHING classifications

## Ensemble Segmentation

The `ConversationSegmenter` combines all three approaches:

```python
# Segment detection strategy:
1. Run embedding drift analysis
2. Run topic modeling (if enough messages)
3. Run LLM analysis (optional)
4. Collect changepoint candidates from each approach
5. Vote on boundaries:
   - Embedding changepoint = 1 vote
   - Topic model transition = 1 vote  
   - LLM segment_break = 2 votes (higher weight)
6. Confirm boundary if votes >= 2
```

**Composite Score Calculation:**
```python
if llm_available:
    composite = (
        0.35 * embedding_drift_score +
        0.20 * topic_entropy_score +
        0.20 * topic_transition_score +
        0.25 * llm_relevance_score
    )
else:
    composite = (
        0.45 * embedding_drift_score +
        0.30 * topic_entropy_score +
        0.25 * topic_transition_score
    )
```

## Database Schema

### New Tables

```sql
-- Segments within chats
CREATE TABLE segments (
    id TEXT PRIMARY KEY,
    chat_id INTEGER NOT NULL,
    start_message_idx INTEGER NOT NULL,
    end_message_idx INTEGER NOT NULL,
    summary TEXT,
    topic_label TEXT,
    parent_segment_id TEXT,
    divergence_score REAL DEFAULT 0.0,
    created_at TEXT,
    FOREIGN KEY (chat_id) REFERENCES chats(id) ON DELETE CASCADE
);

-- Segment embeddings (stored as blobs)
CREATE TABLE segment_embeddings (
    segment_id TEXT PRIMARY KEY,
    embedding BLOB NOT NULL,
    embedding_dim INTEGER NOT NULL,
    model_name TEXT,
    created_at TEXT,
    FOREIGN KEY (segment_id) REFERENCES segments(id) ON DELETE CASCADE
);

-- Links between segments
CREATE TABLE segment_links (
    id TEXT PRIMARY KEY,
    source_segment_id TEXT NOT NULL,
    target_segment_id TEXT NOT NULL,
    link_type TEXT NOT NULL,
    similarity_score REAL DEFAULT 0.0,
    created_at TEXT,
    metadata TEXT,
    FOREIGN KEY (source_segment_id) REFERENCES segments(id),
    FOREIGN KEY (target_segment_id) REFERENCES segments(id)
);

-- Divergence scores per chat
CREATE TABLE divergence_scores (
    chat_id INTEGER PRIMARY KEY,
    overall_score REAL NOT NULL,
    embedding_drift_score REAL,
    topic_entropy_score REAL,
    topic_transition_score REAL,
    llm_relevance_score REAL,
    metrics_json TEXT,
    num_segments INTEGER DEFAULT 1,
    should_split INTEGER DEFAULT 0,
    suggested_split_points TEXT,
    interpretation TEXT,
    computed_at TEXT,
    FOREIGN KEY (chat_id) REFERENCES chats(id) ON DELETE CASCADE
);

-- Processing queue
CREATE TABLE divergence_processing_queue (
    chat_id INTEGER PRIMARY KEY,
    status TEXT DEFAULT 'pending',
    priority INTEGER DEFAULT 0,
    queued_at TEXT,
    started_at TEXT,
    completed_at TEXT,
    error_message TEXT,
    FOREIGN KEY (chat_id) REFERENCES chats(id) ON DELETE CASCADE
);
```

## Processing Infrastructure

### Batch Processing

For backfilling divergence scores on existing chats:

```python
processor = DivergenceProcessor(chat_db)
stats = processor.backfill_all(
    batch_size=50,
    max_chats=1000,
    skip_existing=True,
)
```

### Background Processing

For automatic processing of new/updated chats:

```python
processor = DivergenceProcessor(chat_db)
processor.start_background_processing(
    poll_interval=30.0,  # seconds
    batch_size=10,
)
```

**Background Process Flow:**
1. Poll for chats updated since last check
2. Queue them for processing
3. Process queue items in batches
4. Update divergence scores in database

### Integration with Ingestion Pipeline

Hook into the existing watcher service:

```python
from src.divergence.processor import DivergenceProcessorIntegration

# Create callback for ingestion pipeline
callback = DivergenceProcessorIntegration.create_ingestion_callback(processor)

# Or create callback for watcher
watcher_callback = DivergenceProcessorIntegration.create_watcher_callback(processor)
```

## CLI Commands

```bash
# Analyze a specific chat
python -m src divergence analyze 123
python -m src divergence analyze 123 --no-llm --json

# Backfill all chats
python -m src divergence backfill
python -m src divergence backfill --max-chats 100 --llm

# List high-divergence chats
python -m src divergence list-high --threshold 0.5

# Find related chats
python -m src divergence related 123

# Show segments
python -m src divergence segments 123

# Show stats
python -m src divergence stats

# Run background daemon
python -m src divergence daemon --interval 30
```

## Score Interpretation

| Score Range | Interpretation | Recommendation |
|------------|----------------|----------------|
| 0.0 - 0.2 | Highly focused - single topic | Keep as is |
| 0.2 - 0.4 | Mostly focused with minor tangents | Keep as is |
| 0.4 - 0.6 | Moderate divergence - multiple related topics | Review segments |
| 0.6 - 0.8 | Significant divergence - distinct branches | Consider splitting |
| 0.8 - 1.0 | Highly divergent - multiple unrelated topics | Strongly recommend split |

## Cross-Chat Linking

### Finding Related Chats

```python
# Find chats with similar segments
related = processor.find_related_chats(
    chat_id=123,
    min_similarity=0.5,
    limit=10,
)
```

### Segment-to-Segment Links

```python
from src.divergence.segmenter import find_best_link_target

# Find best matching segment in another chat
match = find_best_link_target(
    source_segment=segment,
    target_segments=other_chat_segments,
)
# Returns: {target_segment_id, similarity_score, link_type}
```

## Dependencies

```
sentence-transformers>=2.2.0  # Embedding drift
bertopic>=0.16.0              # Topic modeling
anthropic>=0.39.0             # LLM judge
numpy>=1.21.0
scipy>=1.7.0
scikit-learn>=1.0.0
```

## Performance Considerations

1. **Embedding Model**: Uses `all-MiniLM-L6-v2` by default (fast, good quality)
2. **Lazy Loading**: Models are loaded on first use to avoid startup cost
3. **Batch Embeddings**: Messages are embedded in batches for efficiency
4. **Embedding Storage**: Stored as binary blobs to save space
5. **WAL Mode**: Database uses WAL for concurrent read/write access
6. **LLM Cost**: LLM analysis is optional and can be disabled for batch processing

## Future Enhancements

1. **Promote to Child Chat**: UI for splitting high-divergence chats
2. **Segment Graph Visualization**: Visual representation of topic flow
3. **Cross-Chat Navigation**: Jump between related segments
4. **Automatic Tagging**: Tag segments based on detected topics
5. **Embedding Model Selection**: Support for code-optimized models
