# Phase 2A Design Spec: Memory System + Conversation Persistence

**Date:** 2026-03-19
**Author:** NABILNET.AI
**Status:** Draft
**Scope:** 5-layer memory engine, conversation persistence, retrieval pipeline, Flutter updates, skill/plugin schema foundation
**Research basis:** 80+ papers (2024-2026). See `research/phase2-research-synthesis.md`

---

## 1. Overview

Phase 2A builds the intelligence core of Nobla Agent — a 5-layer memory system that makes the agent remember, learn, and improve over time. Conversation persistence is unified as the episodic memory layer, not a separate system.

### Goals
- Agent remembers facts, preferences, and context across conversations
- Conversations persist server-side with search and switching
- Knowledge graph tracks entities and relationships incrementally
- Learned workflows improve with Bayesian scoring
- All memory operations respect privacy-first, cost-conscious constraints
- Skill/plugin schema laid as foundation for Phase 6 community marketplace

### Non-Goals (Phase 2A)
- Community marketplace UI (Phase 6)
- Plugin runtime execution engine (Phase 4)
- Voice integration with memory (Phase 3)
- Multi-agent memory sharing (Phase 6)

---

## 2. Architecture

### 2.1 Layered Pipeline (Approach 2 — Distributed)

Each memory layer is an independent module. A thin orchestrator coordinates them.

```
backend/nobla/memory/
├── orchestrator.py      # Thin coordinator — routes to layers
├── working.py           # Context window management (in-memory)
├── episodic.py          # Conversation storage + search (PostgreSQL)
├── semantic.py          # Facts + embeddings (ChromaDB + PostgreSQL)
├── procedural.py        # Learned workflows + Bayesian scoring (PostgreSQL)
├── graph.py             # Entity relationships (NetworkX, lazy-built)
├── retrieval.py         # Hybrid retrieval (0.7 semantic + 0.3 BM25 + re-ranking)
├── extraction.py        # NER + keyword extraction (spaCy, lightweight)
├── consolidation.py     # Warm path: post-conversation LLM extraction
├── maintenance.py       # Cold path: decay, dedup, graph rebuild
└── models.py            # Shared data models
```

### 2.2 Three Processing Paths

#### Hot Path (real-time, per message, <50ms overhead)
- Store raw message in PostgreSQL (episodic)
- Extract lightweight signals without LLM call:
  - spaCy NER: people, organizations, locations, dates
  - TF-IDF keyword extraction: top terms
  - Embed message via sentence-transformers (for later retrieval)
- Update working memory context window
- **Cost: $0. No LLM calls.**

#### Warm Path (post-conversation, async)
Triggers when: conversation ends, app backgrounded, or 5 min idle (configurable).
- Generate conversation summary (1 cheap LLM call)
- Extract facts and preferences from conversation
- For each extracted fact:
  - Check if similar fact exists (vector similarity >0.85): update + merge
  - If new: create memory node + embed in ChromaDB
- Update knowledge graph:
  - Add new entities from accumulated NER results
  - Create/strengthen relationship edges
  - Update entity metadata (last_seen, mention_count)
- Score any learned procedures (Bayesian Beta posterior update)
- **Cost: 1-3 cheap LLM calls per conversation.**

#### Cold Path (nightly background job via APScheduler)
Runs daily at 3 AM (configurable):
- Decay: reduce confidence on memories not accessed in 30+ days
- Dedup: merge semantically similar facts (cosine >0.92)
- Prune: archive memories below confidence threshold (0.1)
- Graph maintenance: remove orphan nodes, recalculate edge strengths
- Stats: log memory health metrics
- **Cost: ~0. Uses local computation only.**

---

## 3. Data Models

### 3.1 Extensions to Existing Tables

**conversations table** — Add:
| Column | Type | Purpose |
|--------|------|---------|
| `summary` | TEXT | Auto-generated conversation summary (warm path) |
| `topics` | TEXT[] | Extracted topic keywords |
| `message_count` | INTEGER | Cached count for UI display |

**messages table** — Add:
| Column | Type | Purpose |
|--------|------|---------|
| `parent_message_id` | UUID (FK, nullable) | Tree structure for future branching |
| `entities_extracted` | JSONB | NER results from hot path |
| `keywords` | TEXT[] | TF-IDF keywords from hot path |

**memory_nodes table** — Add:
| Column | Type | Purpose |
|--------|------|---------|
| `source_conversation_ids` | UUID[] | Provenance: which conversations produced this fact |
| `last_accessed` | TIMESTAMP | For recency scoring in retrieval |
| `access_count` | INTEGER | For frequency scoring in retrieval |
| `decay_factor` | FLOAT | Current decay value (cold path updates) |

**procedures table** — Modify:
| Column | Change | Purpose |
|--------|--------|---------|
| `beta_success` | FLOAT (replaces success_count) | Bayesian Beta distribution alpha parameter |
| `beta_failure` | FLOAT (replaces failure_count) | Bayesian Beta distribution beta parameter |
| `trigger_context` | TEXT (new) | When to suggest this procedure |
| `last_triggered` | TIMESTAMP (new) | Recency tracking |

### 3.2 New Indexes

```sql
-- Full-text search on messages (BM25 via GIN)
CREATE INDEX idx_messages_content_fts ON messages USING GIN (to_tsvector('english', content));

-- Full-text search on conversation summaries
CREATE INDEX idx_conversations_summary_fts ON conversations USING GIN (to_tsvector('english', summary));

-- Topic search on conversations
CREATE INDEX idx_conversations_topics ON conversations USING GIN (topics);

-- Memory retrieval by user + type + confidence
CREATE INDEX idx_memory_nodes_retrieval ON memory_nodes (user_id, note_type, confidence DESC);

-- Knowledge graph traversal
CREATE INDEX idx_memory_links_source ON memory_links (source_id, link_type);
CREATE INDEX idx_memory_links_target ON memory_links (target_id, link_type);
```

---

## 4. Retrieval Pipeline

### 4.1 Query Flow

```
User message arrives
  │
  ├─ Step 1: PARALLEL QUERY (async, <200ms target)
  │   ├─ ChromaDB: top 10 by embedding similarity (semantic)
  │   ├─ PostgreSQL: top 10 by BM25 full-text search (keyword)
  │   └─ NetworkX: 1-hop neighbors of detected entities (graph)
  │
  ├─ Step 2: MERGE + DEDUPLICATE
  │   └─ Union results, remove duplicates by memory_node_id
  │
  ├─ Step 3: RE-RANK (no LLM call)
  │   score = 0.4 * similarity
  │         + 0.3 * recency_decay(last_accessed, half_life=7d)
  │         + 0.2 * access_frequency_normalized
  │         + 0.1 * source_confidence
  │   └─ Return top K (default K=5, configurable)
  │
  ├─ Step 4: FORMAT FOR CONTEXT
  │   └─ Inject as system message block:
  │       "[Memory] User prefers Python. User works at X.
  │        Last discussed: deployment pipeline (2 days ago).
  │        Known entities: Alice (colleague), ProjectX (active)."
  │
  └─ Step 5: PASS TO LLM ROUTER
      └─ Original message + memory context + conversation history
```

### 4.2 Re-ranking Formula

```python
def score_memory(memory, query_embedding, now):
    similarity = cosine_similarity(query_embedding, memory.embedding)

    days_since_access = (now - memory.last_accessed).days
    recency = math.exp(-0.693 * days_since_access / 7)  # half-life = 7 days

    freq = min(memory.access_count / 100, 1.0)  # normalize, cap at 100

    confidence = memory.confidence

    return 0.4 * similarity + 0.3 * recency + 0.2 * freq + 0.1 * confidence
```

### 4.3 Hard-Query LLM Re-ranking (Optional)

For queries classified as HARD by the LLM router:
- After Step 3, pass top 15 results to cheap LLM
- Prompt: "Which of these memories are most relevant to: {query}? Return top 5."
- Adds ~300ms + ~200 tokens. Quality boost for complex questions.

### 4.4 Edge Cases

| Scenario | Behavior |
|----------|----------|
| New user (empty memory) | Skip retrieval, pass message directly |
| Too many results | Hard cap at 2K tokens of memory context |
| ChromaDB unavailable | Fall back to PostgreSQL keyword search only |
| NetworkX not loaded (cold start) | Skip graph step, use vector + keyword |
| All layers empty/unavailable | Graceful degradation: agent works without memory |

---

## 5. Working Memory & Context Window

### 5.1 Context Budget Allocation

```
Context Window Budget (default 8K tokens, configurable per model)
  │
  ├─ System prompt + persona          (~500 tokens, fixed)
  ├─ Retrieved memory block           (~500 tokens max, from retrieval pipeline)
  ├─ Conversation history             (variable, fills remaining budget)
  │   ├─ Recent messages: verbatim    (last 10 messages, ~2K tokens)
  │   ├─ Older messages: summarized   (rolling summary, ~500 tokens)
  │   └─ Tool results: masked         (action kept, raw output hidden)
  └─ Current user message             (variable)
```

### 5.2 Key Behaviors

**Observation masking** (JetBrains, NeurIPS 2025): Tool outputs stored in episodic memory but masked from context. Only the action + one-line summary stays. Halves context cost, no quality loss.

**Rolling summary**: When conversation exceeds verbatim window (10 messages), older messages compressed into rolling summary. One cheap LLM call when buffer overflows.

**Token counting**: `tiktoken` for OpenAI-compatible. Provider-specific tokenizers for others. Pre-count before sending.

**Priority if budget is tight** (minimum viable context):
1. System prompt (never truncated)
2. Current user message (never truncated)
3. Retrieved memories (truncate to 500 tokens max)
4. Last 3 messages verbatim (minimum coherence)
5. Remaining history fills whatever budget is left

---

## 6. Conversation Persistence

### 6.1 Lifecycle

```
User opens app
  → Create or resume conversation (by ID)
  → Load history from PostgreSQL
  → Rebuild working memory (last N messages + rolling summary)
  → Load knowledge graph into NetworkX (if not already in memory)

User sends messages
  → Hot path processing (store + lightweight extraction)
  → Retrieval → LLM → response stored in episodic memory

User closes app / 5 min idle / switches conversation
  → Warm path triggers (summarize, extract facts, update graph)
  → Conversation marked as inactive

User searches past conversations
  → Full-text search across messages.content (GIN index)
  → Semantic search across conversation summaries (ChromaDB)
  → Return ranked results with title + date + preview
```

### 6.2 New JSON-RPC Methods

| Method | Auth | Description |
|--------|------|-------------|
| `conversation.list` | Required | Paginated list with title, date, preview, topic tags |
| `conversation.get` | Required | Full message history for a conversation |
| `conversation.search` | Required | Full-text + semantic search across all conversations |
| `conversation.delete` | Required | Soft delete (archive, don't destroy data) |
| `conversation.rename` | Required | Update conversation title |
| `memory.search` | Required | Search across all memory layers |
| `memory.facts` | Required | List extracted facts (semantic memory) |
| `memory.graph` | Required | Get entity relationships (knowledge graph) |
| `memory.stats` | Required | Memory health dashboard data |

### 6.3 Tree-Structured Messages

Messages stored with `parent_message_id` for future branching support (ChatGPT-style). In Phase 2A, all messages are linear (parent = previous message). The tree structure is a forward-compatible schema choice — branching UI comes in a later phase.

---

## 7. Knowledge Graph (LazyGraphRAG)

### 7.1 Architecture

- **Runtime**: NetworkX in-process Python graph
- **Persistence**: Serialized to PostgreSQL `memory_nodes` + `memory_links` tables
- **Build strategy**: Lazy — graph grows incrementally from conversations (no upfront bulk processing)
- **Cost**: 700x cheaper than full GraphRAG (Microsoft benchmarks)

### 7.2 Entity Types

| Type | Examples | Extraction |
|------|----------|------------|
| PERSON | "Alice", "my manager" | spaCy NER (hot path) |
| ORGANIZATION | "Google", "my company" | spaCy NER (hot path) |
| PROJECT | "ProjectX", "the website redesign" | LLM extraction (warm path) |
| TOOL | "Python", "Docker", "Figma" | Keyword matching (hot path) |
| CONCEPT | "machine learning", "deployment" | LLM extraction (warm path) |
| LOCATION | "New York", "the office" | spaCy NER (hot path) |
| DATE | "March 30 deadline" | spaCy NER (hot path) |

### 7.3 Relationship Types

| Relationship | Example |
|-------------|---------|
| `works_on` | Alice → ProjectX |
| `works_at` | User → Google |
| `uses` | ProjectX → Python |
| `relates_to` | ProjectX → deployment |
| `prefers` | User → Python (over Java) |
| `mentioned_with` | Alice → Bob (co-occurred) |
| `deadline` | ProjectX → March 30 |

### 7.4 Graph Queries

```python
# "What do I know about Alice?"
neighbors = graph.neighbors("Alice")  # 1-hop

# "Who works on ProjectX?"
workers = [n for n in graph.predecessors("ProjectX")
           if graph.edges[n, "ProjectX"]["type"] == "works_on"]

# "What tools does ProjectX use?"
tools = [n for n in graph.successors("ProjectX")
         if graph.edges["ProjectX", n]["type"] == "uses"]
```

---

## 8. Procedural Memory (Bayesian)

### 8.1 How Procedures Are Learned

When the warm path detects a repeated pattern (user asked agent to do the same multi-step task 2+ times), it creates a procedure:

```python
Procedure(
    name="Deploy frontend to Vercel",
    description="Run tests, build, deploy to Vercel, verify",
    steps=[
        {"action": "code.execute", "params": {"cmd": "npm test"}},
        {"action": "code.execute", "params": {"cmd": "npm run build"}},
        {"action": "code.execute", "params": {"cmd": "vercel --prod"}},
        {"action": "browser.navigate", "params": {"url": "https://mysite.vercel.app"}}
    ],
    trigger_context="user asks to deploy frontend or push to production",
    beta_success=2.0,  # Prior: 2 successes
    beta_failure=1.0    # Prior: 1 failure (mild optimism)
)
```

### 8.2 Bayesian Scoring

```python
from scipy.stats import beta

def procedure_score(proc):
    # Expected success probability
    mean = proc.beta_success / (proc.beta_success + proc.beta_failure)

    # Lower confidence bound (pessimistic estimate)
    lcb = beta.ppf(0.05, proc.beta_success, proc.beta_failure)

    return lcb  # Use lower bound to avoid over-suggesting unreliable procedures

# After execution:
if success:
    proc.beta_success += 1.0
else:
    proc.beta_failure += 1.0
```

### 8.3 Auto-Suggestion

When a user message matches a procedure's `trigger_context` (embedding similarity > 0.8), the agent suggests it:

> "I know how to deploy your frontend to Vercel (worked 4/5 times). Want me to run it?"

User can approve, modify, or decline. Approval/decline updates the Bayesian score.

---

## 9. Skill & Plugin Schema (Foundation for Phase 6)

### 9.1 Directory Structure

Mirrors Claude Code's plugin architecture, adapted for Nobla:

```
skills/
├── bundled/                    # Ships with Nobla
│   ├── web-search/
│   │   ├── skill.json          # Skill manifest
│   │   └── SKILL.md            # Prompt/instructions
│   └── summarize/
│       ├── skill.json
│       └── SKILL.md
├── community/                  # Installed from marketplace
│   └── (downloaded plugins go here)
└── custom/                     # User-created
    └── (user's own skills/plugins)

plugins/
├── bundled/
│   └── example-plugin/
│       ├── plugin.json         # Plugin manifest
│       ├── skills/             # Plugin's skills
│       ├── agents/             # Plugin's agents
│       ├── hooks/              # Event-driven automation
│       └── commands/           # Slash commands
├── community/                  # From marketplace
└── custom/                     # User-created
```

### 9.2 Skill Manifest (skill.json)

```json
{
  "name": "web-search",
  "version": "1.0.0",
  "description": "Search the web using SearxNG and synthesize results",
  "author": "nabilnet.ai",
  "license": "MIT",
  "triggers": ["search", "look up", "find online", "what is"],
  "permissions": ["network"],
  "min_security_tier": "SAFE",
  "config": {
    "default_engine": "searxng",
    "max_results": 10
  }
}
```

### 9.3 Plugin Manifest (plugin.json)

```json
{
  "name": "productivity-suite",
  "version": "1.0.0",
  "description": "Calendar, email, and task management tools",
  "author": "community-user",
  "license": "MIT",
  "skills": ["skills/calendar", "skills/email", "skills/tasks"],
  "agents": ["agents/scheduler"],
  "hooks": {
    "on_morning": "hooks/daily-briefing.md",
    "on_calendar_event": "hooks/event-reminder.md"
  },
  "commands": {
    "/briefing": "commands/briefing.md",
    "/schedule": "commands/schedule.md"
  },
  "permissions": ["network", "calendar_api", "email_api"],
  "min_security_tier": "STANDARD",
  "mcp_servers": []
}
```

### 9.4 Community Marketplace (Phase 6 — Schema Only)

```json
{
  "marketplace_entry": {
    "id": "uuid",
    "type": "skill | plugin",
    "name": "string",
    "author": "string",
    "description": "string",
    "version": "string",
    "downloads": "integer",
    "rating": "float (1-5)",
    "reviews": "integer",
    "categories": ["productivity", "development", "media", "automation"],
    "security_audit": "passed | pending | failed",
    "permissions_required": ["network", "filesystem"],
    "min_security_tier": "SAFE | STANDARD | ELEVATED | ADMIN",
    "screenshots": ["url"],
    "source_url": "github url",
    "created_at": "timestamp",
    "updated_at": "timestamp"
  }
}
```

### 9.5 Marketplace Features (Phase 6)

- Browse by category, search by name/description
- One-tap install from Flutter app
- Auto-update with version pinning
- Security audit: every published plugin scanned for dangerous patterns
- Ratings and reviews
- Author profiles linked to community accounts
- Plugin revenue sharing (optional, for premium plugins)

---

## 10. Flutter App Updates

### 10.1 New Screens

**Conversation Drawer** (left sidebar):
- List of conversations grouped by: Today, Yesterday, This Week, Older
- Each item: title (auto-generated or user-set), preview of last message, topic tags
- Search bar at top (queries `conversation.search`)
- Swipe to archive, long-press to rename
- "New Conversation" button

**Memory Viewer** (new tab in bottom nav or accessible from dashboard):
- **Facts tab**: List of extracted semantic memories with confidence scores
- **Entities tab**: Knowledge graph entities with relationship counts
- **Procedures tab**: Learned workflows with success rates
- **Stats**: Total memories, graph nodes/edges, last consolidation time
- Read-only in Phase 2A. Edit/delete in a later phase.

**Community tab** (Phase 6 placeholder):
- Tab visible in bottom nav from Phase 2A (shows "Coming Soon" state)
- Reserved in routing structure so the nav doesn't change later

### 10.2 Updated Screens

**Dashboard** — Add:
- Memory stats card (total facts, entities, procedures, graph density)
- Recent conversations card (last 5, tap to resume)
- Placeholder community card ("Skills Marketplace — Coming Soon")

**Chat Screen** — Add:
- Conversation drawer toggle (hamburger menu or swipe from left)
- Memory indicator: subtle icon when memory was used in response
- "New Conversation" action in app bar

**Settings** — Add:
- Memory settings section:
  - Context window budget (tokens)
  - Warm path idle timeout (minutes)
  - Cold path schedule (time)
  - Memory retention period (days before decay)
- Conversation settings:
  - Auto-title conversations (on/off)
  - Conversation search scope (this device / all synced)

### 10.3 New Providers (Riverpod)

```dart
// Conversation list
final conversationListProvider = StateNotifierProvider<ConversationListNotifier, ConversationListState>(...);

// Memory stats for dashboard
final memoryStatsProvider = FutureProvider<MemoryStats>(...);

// Memory search
final memorySearchProvider = StateNotifierProvider<MemorySearchNotifier, MemorySearchState>(...);

// Conversation search
final conversationSearchProvider = StateNotifierProvider<ConversationSearchNotifier, ConversationSearchState>(...);
```

### 10.4 New Models

```dart
class Conversation {
  final String id;
  final String title;
  final String? summary;
  final List<String> topics;
  final DateTime createdAt;
  final DateTime updatedAt;
  final int messageCount;
  final String? lastMessagePreview;
}

class MemoryFact {
  final String id;
  final String content;
  final double confidence;
  final List<String> keywords;
  final DateTime lastAccessed;
  final int accessCount;
}

class MemoryEntity {
  final String id;
  final String name;
  final String type; // PERSON, ORG, PROJECT, etc.
  final int relationshipCount;
  final DateTime lastSeen;
}

class MemoryStats {
  final int totalFacts;
  final int totalEntities;
  final int totalProcedures;
  final int graphEdges;
  final DateTime lastConsolidation;
  final double avgConfidence;
}
```

---

## 11. Dependencies (New)

### Backend
| Package | Purpose | Cost |
|---------|---------|------|
| `spacy` + `en_core_web_sm` | NER extraction (hot path) | Free, ~50MB model |
| `sentence-transformers` | Embedding generation | Free, already in deps |
| `scikit-learn` | TF-IDF keyword extraction | Free, already in deps |
| `scipy` | Beta distribution for Bayesian scoring | Free |

No new paid services. All new dependencies are free/open-source.

### Flutter
No new package dependencies. Uses existing: `flutter_riverpod`, `go_router`, `web_socket_channel`.

---

## 12. Testing Strategy

### Unit Tests (per module)
- `test_working_memory.py` — Context budget allocation, rolling summary trigger, observation masking
- `test_episodic.py` — Store/retrieve messages, conversation lifecycle, full-text search
- `test_semantic.py` — Fact creation, dedup detection, embedding storage/retrieval
- `test_procedural.py` — Bayesian scoring, procedure matching, auto-suggestion threshold
- `test_graph.py` — Entity CRUD, relationship management, graph queries, serialization
- `test_retrieval.py` — Parallel query, merge/dedup, re-ranking formula, edge cases
- `test_extraction.py` — NER accuracy, keyword extraction, entity type classification
- `test_consolidation.py` — Fact extraction, merge logic, graph updates
- `test_maintenance.py` — Decay, dedup, pruning, orphan cleanup

### Integration Tests
- `test_memory_flow.py` — Full hot→warm→cold path with real database
- `test_retrieval_integration.py` — ChromaDB + PostgreSQL + NetworkX together
- `test_conversation_lifecycle.py` — Create, chat, switch, search, archive

### Flutter Tests
- Widget tests for conversation drawer, memory viewer, new dashboard cards
- Provider tests for conversation list, memory stats, search

### Coverage Target
- Backend memory modules: 90%+ (security-critical data handling)
- Flutter new screens: 80%+

---

## 13. Performance Targets

| Operation | Target | Measurement |
|-----------|--------|-------------|
| Hot path (store + extract) | <50ms | Per message overhead |
| Retrieval (full pipeline) | <200ms | Query to ranked results |
| Working memory assembly | <50ms | Build context for LLM |
| Warm path (consolidation) | <10s | Per conversation |
| Cold path (maintenance) | <5min | Nightly run |
| Conversation list load | <100ms | First 20 conversations |
| Conversation search | <500ms | Full-text + semantic |
| Memory search | <300ms | Across all layers |

---

## 14. Security Considerations

- Memory data is user-scoped: all queries filter by `user_id`
- No cross-user memory access (even in future multi-user scenarios)
- Memory search and facts endpoints require authentication
- Extracted facts never include raw passwords, tokens, or secrets (extraction prompt explicitly excludes sensitive data)
- Conversation delete is soft-delete (archive) — hard delete available via ADMIN tier only
- Audit trail logs all memory write operations
- ChromaDB collections are per-user (isolated embedding spaces)

---

## 15. Migration Plan

### Database Migration (Alembic)
1. Add columns to `conversations` table (summary, topics, message_count)
2. Add columns to `messages` table (parent_message_id, entities_extracted, keywords)
3. Add columns to `memory_nodes` table (source_conversation_ids, last_accessed, access_count, decay_factor)
4. Modify `procedures` table (beta_success, beta_failure, trigger_context, last_triggered)
5. Create new indexes (GIN full-text, retrieval composite, graph traversal)

### Backward Compatibility
- All new columns have defaults (nullable or default values)
- Existing conversations continue to work without memory features
- Memory features activate gradually as data accumulates
- No breaking changes to existing JSON-RPC methods

---

## 16. Phase 2A Sub-phases

### 2A-1: Memory Foundation (~1 week)
- Database migrations
- Orchestrator + working memory + episodic memory
- Hot path (store + lightweight extraction)
- Basic conversation persistence (list, get, create)
- Flutter conversation drawer

### 2A-2: Intelligence Layers (~1 week)
- Semantic memory + ChromaDB integration
- Retrieval pipeline (parallel query + re-ranking)
- Knowledge graph (NetworkX + lazy building)
- Warm path consolidation

### 2A-3: Learning & Polish (~1 week)
- Procedural memory + Bayesian scoring
- Cold path maintenance
- Conversation search (full-text + semantic)
- Memory viewer screen in Flutter
- Dashboard memory stats card
- Skill/plugin schema files (manifests only, no runtime)
- Comprehensive tests

---

## 17. Research References

Key papers informing this design:

| Paper | Year | Contribution to Design |
|-------|------|----------------------|
| Mem0 (arXiv 2504.19413) | 2025 | Triple-store pattern, extraction pipeline |
| MemGPT/Letta (arXiv 2310.08560) | 2023 | Virtual context management, working memory |
| EverMemOS (arXiv 2601.02163) | 2026 | MemCell→MemScene hierarchy, consolidation |
| MACLA (arXiv 2512.18950) | 2025 | Bayesian procedural memory scoring |
| A-MEM (arXiv 2502.12110) | 2025 | Zettelkasten-style self-organizing memory |
| MemRL (arXiv 2601.03192) | 2026 | Two-phase retrieval with utility scoring |
| LazyGraphRAG (Microsoft) | 2025 | Cost-efficient incremental graph building |
| Zep/Graphiti (arXiv 2501.13956) | 2025 | Temporal knowledge graph |
| JetBrains Complexity Trap (NeurIPS) | 2025 | Observation masking > summarization |
| CoPaw/ReMe (Alibaba) | 2026 | Hybrid retrieval 0.7/0.3 blend |
| Stanford Generative Agents | 2023 | Recency-importance-relevance scoring |

Full bibliography: `research/phase2-research-synthesis.md`
