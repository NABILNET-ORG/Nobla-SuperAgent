# Phase 2 Research Synthesis — Nobla Agent
## Date: 2026-03-19
## Sources: 80+ papers, frameworks, and systems (2024-2026)

---

## 1. MEMORY SYSTEMS — Key Papers & Findings

### Landmark Surveys
- **"Memory in the Age of AI Agents"** (Dec 2025, arXiv 2512.13564) — 47 co-authors, "Forms-Functions-Dynamics" taxonomy
- **"Memory for Autonomous LLM Agents"** (Mar 2026, arXiv 2603.07670) — write-manage-read loop, five mechanism families

### Production Frameworks (Ranked by Relevance to Nobla)
| Framework | Architecture | Key Metric | License |
|-----------|-------------|------------|---------|
| **Mem0** | Vector + KV + Graph triple-store | 26% accuracy boost, 91% lower latency | Open Source |
| **Letta (MemGPT)** | Two-tier virtual context (RAM/disk metaphor) | Production-ready | Open Source |
| **Zep/Graphiti** | Temporal knowledge graph | 18.5% accuracy improvement, 90% latency reduction | Open Source |
| **CoPaw/ReMe** | File-based + hybrid retrieval (0.7 semantic / 0.3 BM25) | Multi-channel, local-first | Apache 2.0 |
| **EverMemOS** | MemCell→MemScene hierarchy | SOTA on LoCoMo + LongMemEval | Open Source |

### Critical Papers per Memory Layer
1. **Working Memory**: MemGPT/Letta virtual context paging (arXiv 2310.08560)
2. **Episodic Memory**: MemRL two-phase retrieval with Q-value utility scoring (arXiv 2601.03192)
3. **Semantic Memory**: A-MEM Zettelkasten-inspired self-organizing notes (arXiv 2502.12110, NeurIPS 2025)
4. **Procedural Memory**: MACLA Bayesian Beta posteriors for workflow reliability (arXiv 2512.18950, AAMAS)
5. **Knowledge Graph**: LazyGraphRAG deferred summarization (Microsoft, 700x cheaper than full GraphRAG)

### Memory Retrieval Formula (Research Consensus)
```
score = α * recency_decay(timestamp)        # Stanford Generative Agents
      + β * importance_score(memory)         # LLM-rated 1-10
      + γ * relevance_similarity(query, mem) # Cosine similarity
      + δ * access_frequency(memory)         # Usage tracking
      + ε * utility_qvalue(memory)           # MemRL Q-learning
```

### Memory Consolidation Pipeline (2026 Consensus)
```
Context Window → Working Memory → Episodic (raw) → Semantic (facts) → Procedural (skills)
                                   ↓                  ↓                  ↓
                              PostgreSQL          ChromaDB + PG      PostgreSQL
```

### Forgetting (Feature, Not Bug)
- Exponential decay + relevance-based retention + access frequency tracking
- MACLA: Beta distribution posteriors for confidence scoring
- Strategic forgetting prevents memory bloat and improves retrieval quality

---

## 2. LLM ROUTING — Key Papers & Findings

### Routing Frameworks (Ranked)
| System | Approach | Key Result | Status |
|--------|----------|------------|--------|
| **RouteLLM** | Matrix factorization on preference data | 95% GPT-4 quality with 26% GPT-4 calls (ICLR 2025) | Open Source |
| **Router-R1** | RL-trained multi-round routing | Outperforms single-round on multi-hop QA (NeurIPS 2025) | Research |
| **OptiRoute** | kNN + hierarchical filtering | User preference-aware routing | Research |
| **LiteLLM** | OpenAI-compatible proxy, 100+ models | Built-in retry/fallback/budget | Open Source |
| **Portkey** | AI Gateway, 1,600+ LLMs | MCP-compatible, circuit breakers | Open Source |

### Key Architectural Decisions
- **Streaming**: SSE for LLM calls, WebSocket for client (bidirectional voice needed)
- **Fallback**: Circuit breaker pattern (Closed→Open→Half-Open) with rolling latency metrics
- **Cost tracking**: `tokencost` library for cross-provider pricing
- **Prompt compression**: LLMLingua-2 achieves 3-6x compression with minimal quality loss (ACL 2024)
- **Token budgets**: Including budget hints in prompts reduces output 3x (ACL 2025 Findings)

### Local Inference (2025-2026)
- **Ollama GGUF Q4_K_M**: Best balance for consumer hardware (~62 tok/s single-stream)
- **vLLM AWQ Marlin**: Best for multi-user production (741 tok/s)
- **Speculative decoding**: Up to 3x faster with zero quality loss
- **86% of queries can be handled by cheap models** at 95% quality parity (RouteLLM data)

### Hybrid Local+Cloud Consensus
- 40% of enterprises now run hybrid architectures
- Local handles 85% of routine queries, cloud APIs for 15% complex edge cases
- ~60% cost reduction vs pure cloud, 98% quality maintained

---

## 3. AI SEARCH — Key Papers & Findings

### Architecture Patterns
| System | Architecture | Key Innovation |
|--------|-------------|----------------|
| **Perplexity** | Query→Retrieve→Extract→Synthesize→Verify | 3-agent pipeline ("Comet") |
| **A-RAG** | Expose 3 retrieval tools to LLM agent | Agent composes searches adaptively (Feb 2026) |
| **MA-RAG** | Multi-agent RAG | Specialized agents per pipeline stage |
| **AutoGLM** | RL-based rumination | Self-reflection for iterative web search |

### Recommended Search Stack for Nobla (Cost-Ordered)
1. **SearxNG** — Free, self-hosted, privacy-first (default)
2. **Brave LLM Context API** — $5/1K queries, extracts page content, <600ms P90
3. **Tavily** — $8 CPM, agent-native with MCP support
4. **Exa Deep** — Semantic/research queries

### Search Modes (Industry Standard 2025-2026)
- **Quick Search**: Single query, top results, fast synthesis
- **Deep Search**: Depth-first, follow links, detailed analysis
- **Wide Search**: Breadth-first, multiple sources, comparison
- **DeepWide**: Hybrid depth + breadth (most thorough)

### Search + Memory Integration
- Always check memory BEFORE searching externally
- Cache search results: Redis (short-term), ChromaDB (long-term)
- Extract facts from search results into knowledge graph
- Track source reliability over time for adaptive ranking

---

## 4. CONVERSATION PERSISTENCE — Key Papers & Findings

### Architecture Patterns
| Pattern | Source | Key Innovation |
|---------|--------|----------------|
| **Tree-structured messages** | ChatGPT branching (Sep 2025) | Fork at any point, context isolation |
| **Agentic retrieval** | Azure AI Search (2025) | 40% better relevance via subquery decomposition |
| **Observation masking** | JetBrains (NeurIPS 2025) | Halves cost vs raw context, matches LLM summarization |
| **ACON compression** | OpenReview 2025 | 26-54% memory reduction, gradient-free |

### Context Management (Research Winner)
**The Complexity Trap (JetBrains, NeurIPS 2025)**: Simple observation masking (hiding env output, keeping action/reasoning history) is AS EFFECTIVE as LLM summarization but 50% cheaper. A hybrid approach (masking + summarization) gives 7-11% further cost reduction.

### Conversation-to-Memory Pipeline (Best Practice)
1. **Mem0 pipeline**: Extract candidates → evaluate against existing → add/update/delete
2. **Zep/Graphiti**: Temporal knowledge graph with dual-timeline (valid-time + transaction-time)
3. **EverMemOS**: MemCell→MemScene hierarchy with semantic consolidation
4. **Memoria**: Dynamic summarization + weighted knowledge graph

### Cost Savings from Smart Persistence
- Mem0 chat summarization: 5-20x compression, 70-94% cost savings
- Three techniques: narrative summarization, keyphrase extraction, semantic chunking

### Open-Source Reference Implementations
- **Open WebUI**: SQLite + vector DB, adaptive memory (experimental)
- **LibreChat**: MongoDB, key/value memory agent per request
- **AnythingLLM**: SQLite + LanceDB, workspace isolation

---

## 5. CROSS-CUTTING INSIGHTS

### Priority Order (Research-Informed)
The research strongly suggests: **Memory > Conversation Persistence > LLM Router > Search**

**Why Memory First:**
- Memory is the #1 differentiator (80+ papers in 2025-2026 alone)
- Without memory, every conversation starts from zero — the agent can't learn
- Conversation persistence is a subset of memory (episodic layer)
- The LLM router already works in Phase 1 — enhancements are incremental
- Search is an integration layer that benefits from memory (check memory before searching)

### Key Design Principle: Triple-Store Pattern
The emerging best practice (Mem0, Jan 2026) is to store each memory across THREE backends:
1. **Vector store** (ChromaDB) — semantic similarity search
2. **Key-value store** (Redis) — fast lookups, caching
3. **Graph database** (NetworkX) — relational queries

This maps exactly to Nobla's existing database choices.

### Retrieval: Hybrid is King
- Vector-only retrieval misses keyword matches
- Keyword-only retrieval misses semantic similarity
- **Hybrid (0.7 semantic + 0.3 BM25)** is the production consensus (CoPaw/ReMe)

### Cost-Consciousness Validated
- RouteLLM: 86% of queries handled by cheap models at 95% quality
- LLMLingua-2: 3-6x prompt compression
- LazyGraphRAG: 700x cheaper than full GraphRAG
- Observation masking: 50% cheaper than LLM summarization
- Local Ollama: $0 for 70%+ of tasks

---

## Sources (80+ papers and systems)
See individual research reports in this directory for full citations.
