# Agent Prompt: Session Personas Feature Exploration

## Your Mission

You are tasked with designing the **"Session Personas"** feature for the Cursor Chat Extractor project. This feature aims to automatically generate and maintain context-aware "personas" that capture a developer's working context, preferences, and project knowledge—then inject that wisdom back into future AI coding sessions.

The goal is to close the loop: **chats become knowledge, knowledge becomes context, context improves chats**.

---

## Context: What Already Exists

Before you design, understand what you're building on:

1. **Chat Database**: SQLite with full-text search (FTS5), BM25 ranking
2. **Data Model**: Chats have messages, tags, workspaces, modes (chat/edit/agent/composer/debug)
3. **Tagging System**: Auto-tags by language, framework, topic; hierarchical tags like `tech/python`, `topic/api`
4. **Journal Generator**: Template-based markdown generation from chat data
5. **Search Service**: Instant search, faceted filtering, snippet extraction
6. **Web UI**: Flask app with SSE for live updates

Key files to understand:
- `src/core/models.py` - Chat, Message, Workspace dataclasses
- `src/tagger.py` - TagManager with pattern matching
- `src/journal.py` - JournalGenerator with templates
- `src/services/search.py` - ChatSearchService
- `src/core/db.py` - ChatDatabase with FTS5

---

## The Core Problem to Solve

Every Cursor session starts from zero. The AI doesn't know:
- What architecture decisions you've made
- What patterns you prefer
- What mistakes you keep making
- What you were working on yesterday
- What "that weird bug" was that you fixed last month

**Your job**: Design a system that extracts this knowledge from chat history and makes it available for future sessions.

---

## Design Questions to Explore

### 1. Persona Types & Hierarchy

What kinds of personas should exist? Consider:

- **Project Persona**: Tied to a workspace/repo. Architecture, conventions, gotchas.
- **Session Persona**: Ephemeral, recent. "What am I working on right now?"
- **Personal Persona**: Cross-project. Coding style, preferences, common errors.
- **Team Persona**: Shared conventions for multi-developer projects.

Questions to answer:
- How do these layer? (Personal → Project → Session?)
- Should personas inherit from each other?
- How do you handle conflicts? (Personal preference vs. project convention)

### 2. Knowledge Extraction

How do you extract meaningful "persona facts" from raw chat data?

Options to explore:
- **Rule-based extraction**: Regex patterns for decisions ("we decided to...", "let's use...", "don't forget...")
- **LLM summarization**: Use local models (Ollama) to extract insights
- **Embedding clustering**: Group similar chats and summarize clusters
- **User confirmation**: Surface suggestions for user to approve/reject
- **Implicit learning**: Track what code suggestions were accepted vs. rejected

Consider the signal-to-noise problem:
- 90% of chat is debugging noise
- 10% contains actual decisions/preferences
- How do you find the gold?

### 3. Persona Data Structure

What does a persona actually look like in code?

```python
# Option A: Flat key-value
class Persona:
    facts: Dict[str, str]  # "orm": "SQLAlchemy", "test_framework": "pytest"
    
# Option B: Structured sections
class Persona:
    architecture: ArchitectureContext
    conventions: List[Convention]
    gotchas: List[Gotcha]
    recent_work: List[WorkItem]
    preferences: Dict[str, str]

# Option C: Knowledge graph
class Persona:
    nodes: List[KnowledgeNode]  # Concepts, decisions, patterns
    edges: List[Relationship]   # "uses", "avoids", "prefers"
    
# Option D: Natural language chunks
class Persona:
    chunks: List[str]  # Pre-formatted context strings
    embeddings: np.array  # For semantic retrieval
```

Which structure is:
- Most useful for injection into prompts?
- Easiest to update incrementally?
- Most queryable/searchable?

### 4. Update Strategies

How and when do personas get updated?

Options:
- **Real-time**: Update after every chat session
- **Batch**: Nightly/weekly processing
- **On-demand**: User triggers update
- **Continuous background**: Daemon process

Consider:
- Stale data (project evolved, persona didn't)
- Conflicting information (said X last month, said Y today)
- Version history (track persona evolution over time?)

### 5. Output Formats

How does the persona get used?

**For Cursor Rules** (`.cursor/rules/*.md`):
```markdown
# Project Context (Auto-generated)
- FastAPI backend with SQLAlchemy ORM
- Use Pydantic v2 model_validator, not v1 validator
- All endpoints need OpenAPI docstrings
```

**For direct prompt injection**:
```
<system_context>
You are helping a developer who:
- Prefers explicit code over magic
- Often forgets error handling (remind them)
- Is currently refactoring the auth module
</system_context>
```

**For RAG retrieval**:
```python
# When user asks about testing, retrieve relevant persona chunks
relevant_context = persona.query("testing patterns")
```

### 6. Privacy & Control

Users need control over their data:
- What gets extracted?
- What gets stored?
- What gets injected?
- Can they edit/delete persona facts?
- Can they see what the AI "thinks" about them?

Design a transparency layer:
```bash
python -m src persona show           # See current persona
python -m src persona explain        # Why does it think X?
python -m src persona forget "X"     # Remove a fact
python -m src persona pause          # Stop learning
```

---

## Creative Challenges

### Challenge 1: The Cold Start Problem
New project, no chat history. How do you bootstrap a useful persona?
- Scan codebase for conventions?
- Ask user directly?
- Inherit from personal persona?

### Challenge 2: The Drift Problem
Your preferences 6 months ago aren't your preferences today. How do you:
- Detect when knowledge is stale?
- Weight recent information higher?
- Handle explicit contradictions?

### Challenge 3: The Noise Problem
Most chat is "fix this error" → "try X" → "still broken" → "try Y". How do you extract signal from debugging sessions without capturing noise?

### Challenge 4: The Injection Problem
Context windows are finite. If your persona is 10,000 tokens, how do you:
- Prioritize what to include?
- Dynamically select relevant facts?
- Compress without losing meaning?

### Challenge 5: The Meta Problem
Can the persona system learn about itself? 
- "User often ignores persona suggestions about testing"
- "User finds architecture context most useful"
- Self-improving relevance?

---

## Deliverables Expected

1. **Architecture Document**: How the system is structured
2. **Data Model**: Python dataclasses/schemas for personas
3. **Extraction Pipeline**: How raw chats become persona facts
4. **CLI Commands**: User-facing commands for the feature
5. **Integration Points**: How this connects to existing codebase
6. **Trade-off Analysis**: Options considered and why you chose what you chose

---

## Constraints

- Must work offline (no external API dependencies for core functionality)
- Should be incremental (don't re-process entire history on each update)
- Must integrate with existing database schema (extend, don't replace)
- Should be usable within 1 week of development effort for MVP
- Local LLM support is optional enhancement, not requirement

---

## Inspiration Sources

- **Obsidian's knowledge graph**: How notes link to create emergent structure
- **Git's blame/log**: Attribution and history tracking
- **Spaced repetition**: Weight by recency and frequency
- **Collaborative filtering**: "Developers like you also..."
- **Rubber duck debugging**: Sometimes articulating is the value

---

## Your Approach

1. Start by exploring the existing codebase to understand patterns and conventions
2. Consider multiple architectural approaches before committing
3. Think about the user experience—what would make this *delightful* to use?
4. Identify the minimum viable version vs. the full vision
5. Be creative—this is a novel problem space

Remember: The best features feel inevitable in hindsight but require creative leaps to discover. Don't just implement the obvious solution—explore the problem space and find something elegant.

Good luck. Make something that makes developers feel *understood*.
