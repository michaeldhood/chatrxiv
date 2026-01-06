# Topic Divergence Detection & Conversation Segmentation

## Overview

This system measures topic divergence in chat conversations and detects natural segment boundaries. It enables identifying when conversations branch into child topics and allows for segment-level linking between chats.

## Architecture

The solution uses a multi-modal approach combining three signals:
1.  **Semantic Embedding Drift**: Measures cosine distance from the conversation start using `sentence-transformers`.
2.  **Topic Modeling**: Uses `BERTopic` to identify discrete topics and transitions.
3.  **LLM-as-Judge**: Uses Claude (via Anthropic API) to classify message relationships (e.g., "branching", "tangent").

These signals are combined in a voting ensemble to determine segment boundaries.

## Data Model

### Segments
Conversations are broken down into `Segment` entities, stored in the `segments` table.
- `id`: UUID
- `chat_id`: Reference to the chat
- `start_message_idx`, `end_message_idx`: Range of messages
- `anchor_embedding`: Vector representation of the segment's core topic
- `divergence_score`: How far this segment diverged from the root

### Metrics
Analysis results are stored in `chat_divergence_metrics`:
- `overall_score`: Composite divergence score (0-1)
- `embedding_drift_score`: Mean drift from anchor
- `topic_entropy_score`: Entropy of topic distribution
- `topic_transition_score`: Rate of topic changes

## Usage

### CLI

The `analyze` command processes chats and computes divergence scores.

```bash
# Analyze a specific chat
python -m src analyze --chat-id 123

# Analyze all chats
python -m src analyze --all
```

### Configuration

- **Drift Threshold**: Adjustable via `--threshold` (default 0.35).
- **LLM Model**: Defaults to `claude-3-5-sonnet-20241022` if `ANTHROPIC_API_KEY` is present.

## Implementation Details

- **EmbeddingDriftAnalyzer**: Uses `all-MiniLM-L6-v2` for fast, local embedding generation.
- **TopicDivergenceAnalyzer**: Uses `BERTopic` with `all-MiniLM-L6-v2`.
- **ConversationSegmenter**: Orchestrates the analyzers and implements the voting logic.
    - A boundary is confirmed if 2+ methods agree or if the LLM provides a strong "branching" signal.

## Database Schema Changes

New tables added to `chats.db`:
- `segments`
- `segment_links`
- `chat_divergence_metrics`
- `ingestion_state` (also added for incremental ingestion tracking)
