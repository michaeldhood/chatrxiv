# Analytics & Graphics: Implementation Plan

> Transforming raw chat extracts into visual insights, curated collections, and personal learning journals.

## Overview

This document outlines the phased implementation plan for adding analytics, visualizations, and curation features to chatrxiv. The goal is to turn exported chat data into meaningful insights about coding patterns, learning journeys, and knowledge evolution.

---

## Architecture

### Data Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                        RAW EXTRACTION                           │
│                    (existing: src/extractor.py)                 │
└─────────────────────────────────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────┐
│                      ENRICHMENT PIPELINE                        │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐             │
│  │ Tokenizer   │  │ Topic       │  │ Sentiment   │             │
│  │ & NLP       │  │ Extractor   │  │ Analyzer    │             │
│  └─────────────┘  └─────────────┘  └─────────────┘             │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐             │
│  │ Temporal    │  │ N-gram      │  │ Question    │             │
│  │ Normalizer  │  │ Builder     │  │ Classifier  │             │
│  └─────────────┘  └─────────────┘  └─────────────┘             │
└─────────────────────────────────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────┐
│                       ENRICHED STORAGE                          │
│              (SQLite or extended JSON with indices)             │
└─────────────────────────────────────────────────────────────────┘
                                 │
              ┌──────────────────┼──────────────────┐
              ▼                  ▼                  ▼
┌─────────────────────┐ ┌─────────────────┐ ┌─────────────────────┐
│     ANALYTICS       │ │  VISUALIZATIONS │ │    COLLECTIONS      │
│  - Aggregations     │ │  - Static imgs  │ │  - Auto-clustering  │
│  - Time series      │ │  - Interactive  │ │  - Manual curation  │
│  - Comparisons      │ │  - Dashboards   │ │  - Book export      │
└─────────────────────┘ └─────────────────┘ └─────────────────────┘
```

### Module Structure (Proposed)

```
src/
├── analytics/
│   ├── __init__.py
│   ├── enrichment.py      # Core enrichment pipeline
│   ├── topics.py          # Topic extraction & modeling
│   ├── sentiment.py       # Sentiment analysis
│   ├── temporal.py        # Time-based aggregations
│   └── stats.py           # Summary statistics
├── viz/
│   ├── __init__.py
│   ├── calendar.py        # Calendar heatmaps
│   ├── frequency.py       # Word/topic frequency charts
│   ├── timeline.py        # Topics over time (river charts)
│   ├── network.py         # Concept network graphs
│   └── fingerprint.py     # Abstract conversation signatures
├── collections/
│   ├── __init__.py
│   ├── cluster.py         # Auto-clustering into chapters
│   ├── curator.py         # Manual collection management
│   ├── toc.py             # Table of contents generation
│   └── export.py          # Book/journal export formats
└── cli/
    ├── analytics.py       # `src analytics` commands
    ├── viz.py             # `src viz` commands
    └── collections.py     # `src collections` commands
```

---

## Implementation Phases

### Phase 0: Enrichment Foundation

**Goal**: Build the data processing layer that powers everything else.

**Deliverables**:
- [ ] Enriched data schema design (document in `docs/schema/`)
- [ ] NLP preprocessing pipeline (tokenization, stopword removal, lemmatization)
- [ ] Topic extraction (v1: keyword-based with tech term dictionary)
- [ ] Basic sentiment scoring
- [ ] Temporal normalization (consistent datetime handling)
- [ ] Storage layer (SQLite recommended for query flexibility)
- [ ] CLI command: `src enrich` to process extracted data

**Key Decisions**:
- NLP library: `spaCy` (full-featured) vs `NLTK` (lighter) vs custom (minimal deps)
- Topic approach: Start with keyword dictionaries, graduate to ML later
- Storage: SQLite enables SQL queries for complex analytics

**Estimated Complexity**: Medium-High (foundational, must be solid)

---

### Phase 1: Quick Wins

**Goal**: Deliver visible, satisfying features fast. Prove the pipeline works.

**Deliverables**:
- [ ] Word frequency visualization
  - Bar chart of top N words/terms
  - Optional: word cloud (if tastefully done)
  - Filter by role (user vs AI)
- [ ] Calendar heatmap
  - GitHub-style contribution view
  - Daily/weekly/monthly aggregations
  - Clickable to see that day's chats
- [ ] Basic stats command
  - Total conversations, messages, tokens
  - Date range covered
  - Top topics summary
  - Most active days/times
- [ ] CLI commands: `src stats`, `src viz frequency`, `src viz calendar`

**Output Formats**:
- PNG/SVG for static images
- HTML for interactive versions (using Plotly or similar)

**Estimated Complexity**: Medium

---

### Phase 2: Temporal Intelligence

**Goal**: Understand how topics and patterns evolve over time.

**Deliverables**:
- [ ] Topics over time visualization
  - River/stream chart showing topic volume over time
  - Stacked area chart alternative
  - Drill-down by clicking on a topic
- [ ] Learning arc detection
  - Identify topic "first contact" vs "maturity"
  - Visualize progression from novice to proficient questions
- [ ] Time-of-day patterns
  - Radial chart showing activity by hour
  - Weekday vs weekend patterns
  - "Night owl" vs "early bird" classification
- [ ] Trend detection
  - Identify topics gaining/losing attention
  - "Rabbit hole" detection (sudden deep dives)
  - Abandoned topic identification
- [ ] CLI commands: `src viz timeline`, `src analytics trends`

**Estimated Complexity**: Medium-High

---

### Phase 3: Collections & Curation

**Goal**: Transform raw chats into curated, shareable artifacts.

**Deliverables**:
- [ ] Auto-clustering
  - Group related conversations across time
  - Suggest chapter boundaries
  - Handle cross-topic conversations
- [ ] Manual collection management
  - Create/edit/delete collections
  - Add/remove chats from collections
  - Reorder and organize
- [ ] Table of contents generation
  - Hierarchical TOC from collection structure
  - Auto-generated summaries per chapter
  - Key highlights extraction
- [ ] Export formats
  - Markdown "book" with proper structure
  - HTML static site (browsable)
  - PDF via pandoc (optional)
  - ePub for e-readers (stretch goal)
- [ ] CLI commands: `src collections create`, `src collections export`

**Estimated Complexity**: High

---

### Phase 4: Advanced Features

**Goal**: The delightful, impressive, "wow" features.

**Deliverables**:
- [ ] Conversation fingerprints
  - Unique visual signature per chat
  - Based on length, topic mix, sentiment arc, question types
  - Abstract/artistic representation
- [ ] Concept network graph
  - Topics as nodes, co-occurrence as edges
  - Interactive exploration
  - Cluster visualization
- [ ] Sentiment overlays
  - Layer sentiment onto existing visualizations
  - Frustration detection and patterns
  - "Breakthrough moment" identification
- [ ] Comparative analysis
  - Compare time periods
  - Compare projects/workspaces
  - "Your coding personality" insights
- [ ] Question taxonomy
  - Classify question types (debugging, learning, architecture, etc.)
  - Visualize your question profile
  - Track evolution of question sophistication

**Estimated Complexity**: Varies (some easy, some experimental)

---

## Technical Decisions

### NLP Tooling Options

| Option | Pros | Cons | Recommendation |
|--------|------|------|----------------|
| **spaCy** | Full-featured, fast, good models | Heavy dependency (~500MB) | Best for serious NLP |
| **NLTK** | Lighter, well-documented | Older, slower | Good middle ground |
| **Custom** | Minimal deps, full control | More work, less accurate | For simple keyword matching |
| **Transformers** | State-of-art, embeddings | Very heavy, overkill? | For advanced topic modeling |

**Recommendation**: Start with custom keyword-based + NLTK for basics. Add spaCy as optional "enhanced" mode.

### Visualization Libraries

| Library | Type | Pros | Cons |
|---------|------|------|------|
| **matplotlib** | Static | Universal, familiar | Ugly defaults, verbose |
| **seaborn** | Static | Pretty defaults | Less flexible |
| **Plotly** | Interactive | Great interactivity, HTML export | Heavier |
| **Altair** | Both | Declarative, clean | Learning curve |
| **Rich** | Terminal | CLI-native, no files needed | Limited graphics |

**Recommendation**: Plotly for HTML output, matplotlib/seaborn for static. Rich for CLI previews.

### Storage Options

| Option | Pros | Cons |
|--------|------|------|
| **Extended JSON** | Simple, portable | Slow queries, no indexing |
| **SQLite** | Fast queries, indexing, SQL | Extra file, schema management |
| **DuckDB** | Analytical queries, fast | Newer, another dependency |

**Recommendation**: SQLite. The query flexibility is essential for analytics.

---

## CLI Interface Design

```bash
# Enrichment
src enrich                    # Process all extracted data
src enrich --force            # Re-process even if already enriched

# Statistics
src stats                     # Overall summary
src stats --topic "react"     # Stats for specific topic
src stats --period 2024-01    # Stats for time period

# Visualizations
src viz frequency             # Word frequency chart
src viz frequency --top 50    # Top 50 words
src viz frequency --role user # Only user messages

src viz calendar              # Activity heatmap
src viz calendar --year 2024  # Specific year
src viz calendar --topic X    # Filtered by topic

src viz timeline              # Topics over time
src viz timeline --topics 5   # Top 5 topics only

src viz network               # Concept network graph
src viz fingerprint CHAT_ID   # Single conversation fingerprint

# Collections
src collections list                    # List all collections
src collections create "React Journey"  # Create new collection
src collections add COLLECTION CHAT_ID  # Add chat to collection
src collections auto-cluster            # Generate suggested chapters
src collections export COLLECTION       # Export to book format
src collections export COLLECTION --format html
```

---

## Success Metrics

- **Phase 0**: Can enrich 1000 chats in < 30 seconds
- **Phase 1**: Users can generate their first visualization in < 2 minutes after install
- **Phase 2**: Timeline accurately reflects topic evolution (validated manually)
- **Phase 3**: Exported "book" is genuinely readable and useful
- **Phase 4**: At least one feature makes users say "whoa"

---

## Open Questions

1. Should visualizations be primarily static files or a local web dashboard?
2. How much NLP sophistication is worth the dependency cost?
3. Should we support real-time/incremental enrichment as new chats happen?
4. Is there value in a "share" feature (anonymized insights)?
5. Should collections support collaborative editing?

---

## Next Steps

1. Review and refine this plan
2. Design enriched data schema (Phase 0 blocker)
3. Spike on NLP tooling to assess dependency tradeoffs
4. Begin Phase 0 implementation
