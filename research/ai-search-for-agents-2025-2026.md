# AI-Powered Search for Agents: Research Report (2024-2026)

**Prepared for:** Nobla Agent Project
**Date:** March 2026
**Author:** [NABILNET.AI](https://nabilnet.ai)

---

## Table of Contents

1. [AI Search Synthesis Systems](#1-ai-search-synthesis-systems)
2. [SearxNG Integration](#2-searxng-integration)
3. [Multi-Source Search](#3-multi-source-search)
4. [Search + Memory Integration](#4-search--memory-integration)
5. [Search API Comparison](#5-search-api-comparison)
6. [Recommendations for Nobla Agent](#6-recommendations-for-nobla-agent)

---

## 1. AI Search Synthesis Systems

### 1.1 Perplexity AI Architecture

**How it works:** Perplexity is a real-time answer engine combining RAG with LLMs. Its pipeline:

1. **Query Intent Parsing** — An LLM parses user intent at a semantic level (beyond keywords)
2. **Web Index Retrieval** — Searches a live web index for relevant pages
3. **Passage Extraction** — Extracts relevant passages from retrieved documents
4. **LLM Synthesis** — Uses an LLM to synthesize a coherent answer with inline numbered citations
5. **Verification** — Enterprise "Comet" framework adds a verification agent that validates citations against live sources

**Model routing:** Perplexity uses its own **Sonar** model (built on Llama 3.1 70B, fine-tuned for retrieval/ranking/synthesis) alongside GPT-5.2, Claude 4.5, Gemini 3 Pro, Grok 4.1, and Kimi K2 — routing each query to the best model for the task.

**Key insight for Nobla:** The multi-agent research workflow (retrieval agent + synthesis agent + verification agent) is the gold standard. Sonar handles retrieval while stronger models handle synthesis.

**Sources:**
- [How Perplexity Built an AI Google](https://blog.bytebytego.com/p/how-perplexity-built-an-ai-google) — ByteByteGo
- [Perplexity AI vs Traditional LLMs Architecture](https://medium.com/@kpallukuri/perplexity-ai-vs-traditional-llms-the-architecture-that-changes-everything-bb1e3b9d6096)
- [AI Search Architecture Deep Dive](https://ipullrank.com/ai-search-manual/search-architecture) — iPullRank
- [Perplexity's LLM Tech Stack](https://rankstudio.net/articles/en/perplexity-llm-tech-stack) — RankStudio

### 1.2 Tavily — Search API Built for AI Agents

**Architecture:** Tavily retrieves live web data, extracts relevant content, and returns it structured and chunked for LLMs. Agents reason over facts without hallucinating.

**Key APIs:**
- **Search API** — Returns ranked snippets with relevance scores and citations formatted for agent workflows
- **Extract API** — Pulls structured content from specific URLs
- **Map API** — Site mapping for crawling
- **Crawl API** — Full site crawling

**Integrations:** Native support for LangChain, LlamaIndex, and Model Context Protocol (MCP). Used by Groq, Cohere, MongoDB, and Writer.

**Funding:** $25M raised (August 2025) to connect AI agents to the web.

**Relevance to Nobla:** Tavily is the most agent-friendly search API. Its MCP support makes it a natural fit for the tool platform. The structured output format (ranked snippets + relevance scores + citations) is exactly what an LLM router needs.

**Sources:**
- [Tavily Official](https://www.tavily.com/)
- [Beyond Tavily - Complete Guide to AI Search APIs 2025](https://websearchapi.ai/blog/tavily-alternatives)
- [Tavily Raises $25M](https://techcrunch.com/2025/08/06/tavily-raises-25m-to-connect-ai-agents-to-the-web/) — TechCrunch
- [Tavily Review 2026](https://aiagentslist.com/agents/tavily)

### 1.3 Phind — Developer-Focused AI Search

**Architecture:** Phind uses its own models (Phind-70B, Phind-405B) fine-tuned on programming corpora, combined with RAG. It delivers:

- Code snippets with contextual explanations
- Embedded images, diagrams, live code execution via Jupyter
- Multi-step reasoning with chained web searches mid-answer
- Deep integration with documentation, repos, and engineering best practices

**Key insight:** In practice, power users in 2026 use a hybrid stack: Perplexity (research) + Google (navigation) + Phind (coding). This validates Nobla's approach of routing different query types to different search backends.

**Sources:**
- [Phind AI Tool Review 2025](https://aiappgenie.com/post/phind-ai-tool-review)
- [AI Search Engines Compared 2026](https://www.haoqq.com/en/guides/ai-search-engines-compared-2026)
- [Phind vs Perplexity for Coding 2026](https://www.index.dev/blog/phind-vs-perplexity-ai-coding)

### 1.4 Exa AI — Neural Semantic Search

**Architecture:** Exa is the first web-scale neural search engine. Unlike keyword-based search, Exa trains transformer models to preprocess documents into embeddings, enabling filtering by meaning.

**Key endpoints (Exa 2.0, trained on 144x H200 cluster):**
- **Exa Fast** — <350ms P50 latency, 30% faster than next fastest API
- **Exa Deep** — 3.5s P50, agentically searches/processes/re-searches for highest quality
- **Exa Auto** — Balances latency and quality

**Pricing:** $5 per 1,000 queries (same as Brave)

**Key insight for Nobla:** Exa's "Deep" endpoint is essentially an agentic search within the search API itself — it iteratively refines results. This pattern (search -> evaluate -> re-search) is what Nobla's search tool should implement.

**Sources:**
- [Exa API 2.0 Blog](https://exa.ai/blog/exa-api-2-0)
- [Perfect Web Search for AI Agents](https://exa.ai/blog/perfect-search)
- [Exa Raises $85M](https://exa.ai/blog/announcing-series-b)

### 1.5 You.com

**Approach:** Emphasizes mode selection and customization, allowing users to control how answers are produced. Attractive for teams experimenting with different model behaviors.

**Source:**
- [AI Search Engines Compared 2026](https://www.haoqq.com/en/guides/ai-search-engines-compared-2026)

### 1.6 Key Research Papers on Search-Augmented Generation

#### "Agentic Retrieval-Augmented Generation: A Survey on Agentic RAG"
- **Authors:** Aditi Singh, Abul Ehtesham, Saket Kumar, Tala Talaei Khoei
- **Date:** January 2025 (arXiv:2501.09136)
- **Key findings:** Agentic RAG transcends traditional RAG by embedding autonomous agents into the pipeline using reflection, planning, tool use, and multi-agent collaboration. Taxonomy covers single-agent, multi-agent, and hierarchical architectures.
- **Relevance:** Directly maps to Nobla's multi-agent orchestrator design.

#### "A-RAG: Scaling Agentic RAG via Hierarchical Retrieval Interfaces"
- **Date:** February 2026 (arXiv:2602.03442)
- **Key findings:** Exposes three retrieval tools (keyword search, semantic search, chunk read) enabling agents to adaptively search across multiple granularities.
- **Relevance:** Validates Nobla's planned multi-tier search (web + vector + knowledge graph).

#### "MA-RAG: Multi-Agent RAG via Collaborative Chain-of-Thought"
- **Date:** May 2025 (arXiv:2505.20096)
- **Key findings:** Specialized agents handle distinct RAG stages: query disambiguation, targeted evidence extraction, and answer synthesis using chain-of-thought reasoning.
- **Relevance:** Maps to Nobla's planned agent orchestrator architecture.

#### "Agentic RAG with Knowledge Graphs for Complex Multi-Hop Reasoning"
- **Date:** July 2025 (arXiv:2507.16507)
- **Key findings:** INRAExplorer uses an LLM-based agent with multi-tool architecture to dynamically query a knowledge graph for iterative, targeted retrieval and multi-hop reasoning.
- **Relevance:** Directly relevant to Nobla's NetworkX knowledge graph in the memory engine.

#### "Deep Research Agents: A Systematic Examination and Roadmap"
- **Authors:** Yuxuan Huang et al. (13 authors)
- **Date:** June 2025 (arXiv:2506.18096)
- **Key findings:** Proposes taxonomy of static vs dynamic workflows. Classifies architectures by planning strategies and agent composition. Reviews information acquisition (API-based vs browser-based). Examines MCP integration for extensibility.
- **Relevance:** Comprehensive framework for designing Nobla's deep research capability.

#### "Comprehensive Survey of RAG: Architectures, Enhancements, and Robustness"
- **Date:** June 2025 (arXiv:2506.00054)
- **Key findings:** Taxonomy categorizing RAG architectures into retriever-centric, generator-centric, hybrid, and robustness-oriented designs.

**Sources:**
- [arXiv:2501.09136](https://arxiv.org/abs/2501.09136)
- [arXiv:2506.18096](https://arxiv.org/abs/2506.18096)
- [arXiv:2602.03442](https://arxiv.org/abs/2602.03442)
- [arXiv:2505.20096](https://arxiv.org/pdf/2505.20096)
- [arXiv:2507.16507](https://arxiv.org/abs/2507.16507)

---

## 2. SearxNG Integration

### 2.1 Overview

SearxNG is a free, open-source metasearch engine that aggregates results from 70+ search engines while protecting user privacy. It is the gold standard for privacy-preserving search.

### 2.2 LLM Integration Patterns

**Pattern 1: Direct API Integration**
- SearxNG exposes a JSON API when configured with `format=json`
- LiteLLM has built-in SearxNG support for web search augmentation
- Configure via Docker with `SEARXNG_QUERY_URL` environment variable

**Pattern 2: MCP Server**
- **SearxNG MCP Server by netixc** — Open-source MCP server giving AI assistants (Claude, etc.) web search via SearxNG
- Queries are anonymized; major search providers never see the LLM's specific queries
- Perfect for Nobla's privacy-first design

**Pattern 3: Local LLM + SearxNG Agent**
- [Dev-TechT/local-llm-searxng-agent](https://github.com/Dev-TechT/local-llm-searxng-agent) — Python CLI agent connecting local LLMs to local SearxNG
- Demonstrates the full privacy stack: local LLM + local search = zero external data leakage

### 2.3 Self-Hosting Best Practices (2025-2026)

1. **Docker Compose deployment** — Most reliable method; use official `searxng/searxng` image
2. **Reverse proxy with SSL** — Nginx/Caddy in front for HTTPS
3. **Tailscale integration** — Private network access without port forwarding ([Hostbor guide](https://hostbor.com/private-search-searxng-tailscale/))
4. **Engine selection** — Disable unreliable engines; weight Google, Bing, DuckDuckGo higher
5. **Rate limiting** — Configure per-engine rate limits to avoid IP bans
6. **Result format** — Use `format=json` for API access; configure `results_count` for quality

### 2.4 Search Quality Optimization

- Enable/disable specific engines per category (general, images, news, science, files)
- Adjust language preferences and safe search settings
- Use SearxNG's built-in result scoring/ranking
- Combine with LLM re-ranking for best results

**Sources:**
- [IntelTechniques: Self-Hosted SearXNG Guide](https://inteltechniques.com/blog/2025/07/11/extreme-privacy-update-self-hosted-searxng-guide/)
- [SearXNG on LiteLLM](https://docs.litellm.ai/docs/search/searxng)
- [Self-Hosted Search SearXNG 2026](https://dasroot.net/posts/2026/03/self-hosted-search-searxng-installation-configuration/)
- [SearxNG MCP Server](https://skywork.ai/skypage/en/searxng-mcp-server-ai-engineer-gateway/1977985483780575232)
- [local-llm-searxng-agent](https://github.com/Dev-TechT/local-llm-searxng-agent)

---

## 3. Multi-Source Search

### 3.1 Deep Research Mode (Multi-Step Search with Refinement)

The dominant paradigm in 2025-2026 is **Deep Research** — autonomous agents that perform multi-step, iterative search:

**OpenAI Deep Research:**
- Plans and executes multi-step search trajectory
- Finds, analyzes, and synthesizes hundreds of online sources
- Backtracking and reacting to real-time information
- Produces research analyst-level reports

**Google Gemini Deep Research (Gemini 3.1 Pro):**
- Autonomously plans, executes, and synthesizes multi-step research
- Navigates both web search and user's own data
- Produces detailed, cited reports

**Advanced systems using RL:**
- **AutoGLM Rumination** (Zhipu AI) — RL-based, self-reflection, iterative refinement, autonomously interacts with web, executes code, invokes APIs
- **Tool-Star, Kimi-Researcher, MiroRL** — RL/self-reflection for planning searches and multi-step reasoning

**Taxonomy (from Deep Research Agents survey):**
- **Deep Search** — Multi-step reasoning for single targets
- **Wide Search** — Broad aggregation across extensive sources
- **DeepWide Search** — Hybrid combining both approaches

### 3.2 Combining Web + Academic + Code Search

**AIsa Multi-Source Search** demonstrates a unified API integrating:
- Web search (general queries)
- Academic search with year filtering
- Tavily operations for structured results
- Full-text search with confidence scoring

**PaSa** (LLM Agent for Comprehensive Academic Paper Search) — Specialized agent for academic literature discovery.

**Code search** — Modern systems like Claude Code use agentic search: pattern matching (grep), file discovery (glob), and direct file access combined as tools.

### 3.3 Search Result Ranking and Deduplication

Modern approaches to deduplication and citation:
- **URL canonicalization** — Normalize URL variants before deduplication
- **Entity resolution** — Identify when different sources describe the same information
- **Evidence preservation** — Keep citation trails even after deduplication
- **Confidence scoring** — Assign trust scores to results from different sources
- **Cross-source correlation** — Match findings across different search backends

### 3.4 Source Citation and Attribution

Best practices from 2025-2026:
- Inline numbered citations (Perplexity style) with source URLs
- Citation validation against live sources (Perplexity's Comet verification agent)
- Group citations by root domain for cleaner presentation
- Track citation performance over time to identify reliable sources

**Sources:**
- [OpenAI Deep Research](https://openai.com/index/introducing-deep-research/)
- [Gemini Deep Research Agent](https://ai.google.dev/gemini-api/docs/deep-research)
- [Deep Research Agents Survey](https://arxiv.org/abs/2506.18096)
- [Deep Research Survey: Autonomous Research Agents](https://arxiv.org/html/2508.12752v1)
- [AIsa Multi-Source Search](https://termo.ai/skills/aisa-multi-source-search)

---

## 4. Search + Memory Integration

### 4.1 When to Search vs. When to Use Memory

The key distinction from 2025 research:

| Source | Use Case | Example |
|--------|----------|---------|
| **RAG (Search)** | Static knowledge bases, documentation, reference material | "What is the Python syntax for list comprehension?" |
| **Memory** | User-specific facts that evolve with conversations | "What LLM provider does the user prefer?" |
| **Both** | Personalized answers grounded in facts | "Find me a tutorial on X, similar to what I liked before" |

**Decision logic for Nobla:**
```
if query_requires_current_info -> search web
elif query_is_about_user_context -> check memory first
elif query_is_factual_and_stable -> check memory cache, fallback to search
elif query_is_complex_research -> search + memory (for user preferences)
```

### 4.2 Caching Search Results in Memory

**Short-term (Redis/in-process):**
- Session state and recent search results
- Tool/results caching to avoid repeating calls within the same run
- "Keep last N results" or "expire after X minutes"
- **Semantic Cache** — Store query-response pairs, retrieve for semantically similar future queries

**Long-term (Vector DB):**
- Valuable search findings stored as episodic memories
- Semantic search over past search results (ChromaDB)
- Lifecycle policies to remove outdated information

### 4.3 Building Knowledge from Search Results

Key architecture pattern:
1. Search returns raw results
2. LLM extracts key facts/entities
3. Facts stored in knowledge graph (NetworkX)
4. Entity relationships linked
5. Future queries check knowledge graph before searching again

This reduces token costs by retrieving stored facts instead of reprocessing.

### 4.4 Adaptive Search (Learning Reliable Sources)

From the research:
- Track which sources produce accurate, cited information
- Weight reliable sources higher in future searches
- Use Brave's **Goggles** re-ranking system for source-level control
- Build source reliability scores over time in the knowledge graph

### 4.5 Key Memory Frameworks (2025-2026)

- **Mem0** — Universal memory layer for AI agents (open-source). Supports vector search + graph structures. Used with Amazon ElastiCache + Neptune Analytics.
- **Redis** — AI agent memory management with short-term and long-term memory patterns
- **MongoDB** — Agent memory with flexible document storage

**Key paper:** "Memory in the Age of AI Agents" (December 2025, arXiv:2512.13564)

**Sources:**
- [Memory in the Age of AI Agents](https://arxiv.org/abs/2512.13564)
- [AI Memory Layer Guide 2025](https://mem0.ai/blog/ai-memory-layer-guide)
- [Mem0 GitHub](https://github.com/mem0ai/mem0)
- [Build AI Agents with Redis Memory](https://redis.io/blog/build-smarter-ai-agents-manage-short-term-and-long-term-memory-with-redis/)
- [Best AI Agent Memory Frameworks 2026](https://machinelearningmastery.com/the-6-best-ai-agent-memory-frameworks-you-should-try-in-2026/)
- [Memory for AI Agents: Context Engineering](https://thenewstack.io/memory-for-ai-agents-a-new-paradigm-of-context-engineering/)

---

## 5. Search API Comparison

### 5.1 Brave Search API

**Unique advantage:** Operates its own full web index (not scraping others).

**LLM Context API (launched 2025-2026):**
- Extracts actual page content: text chunks, tables, code blocks, structured data (JSON-LD)
- <130ms overhead at P90; total latency <600ms at P90
- Configurable token and URL limits
- **Goggles** re-ranking system for source-level control
- Powers 22M+ answers/day internally in Brave Search

**Pricing:** $5/1k queries (free tier removed, replaced with $5 monthly credits)

**Sources:**
- [Brave Search API](https://brave.com/search/api/)
- [Brave LLM Context API Documentation](https://api-dashboard.search.brave.com/documentation/services/llm-context)
- [Brave Most Powerful Search API for AI](https://brave.com/blog/most-powerful-search-api-for-ai/)

### 5.2 Comparison Table

| API | Pricing | Speed | Best For | Index | Free Tier |
|-----|---------|-------|----------|-------|-----------|
| **Brave Search** | $5/1k queries | <600ms P90 | Privacy-first, LLM context extraction | Own full web index | $5/mo credits (~1k queries) |
| **Tavily** | $8 CPM | Moderate | AI agent integration, structured results | Aggregated | 1,000 credits/mo |
| **Exa** | $5/1k queries | <350ms (Fast), 3.5s (Deep) | Semantic/neural search | Own neural index | Limited |
| **SerpAPI** | $0.015/search | Varies | Raw SERP data, 20+ engines | Scrapes Google etc. | 100/mo |
| **Serper** | ~$1/1k queries | Fast | Budget Google SERP | Scrapes Google | 2,500 free queries |
| **SearxNG** | Free (self-hosted) | Varies | Privacy, customization, no cost | Meta-search (70+ engines) | N/A (self-hosted) |
| **Google PSE** | Free (100/day), $5/1k after | Fast | Google results | Google index | 100/day |

### 5.3 Recommendations by Use Case

| Use Case | Recommended API | Reasoning |
|----------|----------------|-----------|
| **Default/Privacy** | SearxNG (self-hosted) | Free, private, 70+ engines, perfect for Nobla's privacy-first design |
| **High-quality LLM grounding** | Brave LLM Context API | Extracts actual content, not just snippets; own index |
| **Agent tool calls** | Tavily | Purpose-built for agents, MCP support, structured output |
| **Semantic/research search** | Exa Deep | Neural search by meaning, iterative refinement |
| **Code search** | Phind API or specialized | Fine-tuned on programming corpora |
| **Budget fallback** | SearxNG or Google PSE free tier | Zero cost |

---

## 6. Recommendations for Nobla Agent

### 6.1 Proposed Search Architecture

```
User Query
    |
    v
[Query Classifier] -- determines: search type, complexity, domain
    |
    +-- Simple factual --> Check Memory Cache --> if miss --> SearxNG (fast, free)
    |
    +-- Current events --> Brave LLM Context API (extracts content directly)
    |
    +-- Research/deep --> Deep Research Mode:
    |       1. Plan search strategy (decompose into sub-queries)
    |       2. Execute parallel searches (SearxNG + Brave + Exa)
    |       3. Deduplicate and rank results
    |       4. LLM synthesizes with citations
    |       5. Verify citations (optional verification agent)
    |       6. Store key findings in memory/knowledge graph
    |
    +-- Code/technical --> Tavily (structured) + code-specific search
    |
    +-- Academic --> Exa Deep or academic search APIs
    |
    v
[Result Processor]
    |
    +-- Extract key facts --> Knowledge Graph (NetworkX)
    +-- Cache results --> Redis (short-term) + ChromaDB (semantic)
    +-- Format citations --> Inline numbered with source URLs
    +-- Return to LLM Router --> Synthesis with chosen model
```

### 6.2 Implementation Priority (aligned with Plan.md phases)

**Phase 2 (Weeks 5-8) — Intelligence Core:**
1. SearxNG self-hosted instance (Docker Compose) — free, private baseline
2. Tavily integration as primary agent search tool (MCP support)
3. Basic search result caching in Redis
4. Simple query-to-search routing

**Phase 3-4 (Weeks 9-16):**
5. Brave LLM Context API for content extraction
6. Exa integration for semantic search
7. Deep Research mode (multi-step, iterative)
8. Search result -> Knowledge Graph pipeline

**Phase 6 (Weeks 21-24):**
9. Multi-agent search orchestration (retrieval + synthesis + verification agents)
10. Adaptive source reliability scoring
11. Full citation tracking and attribution

### 6.3 Cost Optimization Strategy

```
Tier 1 (Free):     SearxNG self-hosted — unlimited, private
Tier 2 (Cheap):    Brave ($5/1k) or Serper ($1/1k) — when SearxNG quality insufficient
Tier 3 (Quality):  Tavily ($8 CPM) or Exa ($5/1k) — for agent tool calls / semantic search
Tier 4 (Premium):  Exa Deep (3.5s, higher cost) — for deep research mode only

Budget controls: Track per-user search API costs, auto-switch to SearxNG when budget exceeded
```

### 6.4 Key Design Decisions

1. **SearxNG as default** — Aligns with privacy-first, cost-conscious design. Falls back to paid APIs only when quality is insufficient.
2. **Tavily for agent tools** — Its MCP support and structured output format make it ideal for the tool platform.
3. **Brave LLM Context for grounding** — The content extraction capability (tables, code, structured data) is superior to snippet-based APIs.
4. **Agentic search pattern** — Implement the A-RAG pattern: keyword search + semantic search + chunk read as three retrieval tools the agent can compose.
5. **Memory-first** — Always check memory/cache before hitting external search APIs to reduce costs and latency.
6. **Citation-always** — Every search-synthesized response must include inline citations. Build verification into the pipeline early.

---

## Appendix: All Sources

### Research Papers
- [Agentic RAG Survey (2501.09136)](https://arxiv.org/abs/2501.09136) — Singh et al., Jan 2025
- [Deep Research Agents Survey (2506.18096)](https://arxiv.org/abs/2506.18096) — Huang et al., Jun 2025
- [A-RAG: Hierarchical Retrieval (2602.03442)](https://arxiv.org/abs/2602.03442) — Feb 2026
- [MA-RAG: Multi-Agent RAG (2505.20096)](https://arxiv.org/pdf/2505.20096) — May 2025
- [Agentic RAG with Knowledge Graphs (2507.16507)](https://arxiv.org/abs/2507.16507) — Jul 2025
- [Comprehensive RAG Survey (2506.00054)](https://arxiv.org/abs/2506.00054) — Jun 2025
- [RAG Evaluation Survey (2504.14891)](https://arxiv.org/abs/2504.14891) — Apr 2025
- [Memory in the Age of AI Agents (2512.13564)](https://arxiv.org/abs/2512.13564) — Dec 2025
- [Deep Research Survey: Autonomous Agents (2508.12752)](https://arxiv.org/html/2508.12752v1) — Aug 2025
- [Retrieval-Augmented Code Generation Survey (2510.04905)](https://arxiv.org/abs/2510.04905) — Oct 2025

### Products & APIs
- [Perplexity AI API Platform](https://www.perplexity.ai/api-platform)
- [Tavily](https://www.tavily.com/)
- [Brave Search API](https://brave.com/search/api/)
- [Exa AI](https://exa.ai/)
- [Phind](https://phindai.org/)
- [SearxNG](https://github.com/searxng/searxng)

### Technical Guides
- [How Perplexity Built an AI Google](https://blog.bytebytego.com/p/how-perplexity-built-an-ai-google)
- [Self-Hosted SearXNG Guide](https://inteltechniques.com/blog/2025/07/11/extreme-privacy-update-self-hosted-searxng-guide/)
- [SearxNG MCP Server](https://skywork.ai/skypage/en/searxng-mcp-server-ai-engineer-gateway/1977985483780575232)
- [local-llm-searxng-agent](https://github.com/Dev-TechT/local-llm-searxng-agent)
- [Best SERP API Comparison 2025](https://dev.to/ritza/best-serp-api-comparison-2025-serpapi-vs-exa-vs-tavily-vs-scrapingdog-vs-scrapingbee-2jci)
- [Best Web Search APIs for AI 2026](https://www.firecrawl.dev/blog/top_web_search_api_2025)
- [Brave LLM Context API Docs](https://api-dashboard.search.brave.com/documentation/services/llm-context)
- [Mem0 Memory Layer](https://mem0.ai/blog/ai-memory-layer-guide)
- [Redis AI Agent Memory](https://redis.io/blog/build-smarter-ai-agents-manage-short-term-and-long-term-memory-with-redis/)

### Industry Coverage
- [OpenAI Deep Research](https://openai.com/index/introducing-deep-research/)
- [Gemini Deep Research](https://ai.google.dev/gemini-api/docs/deep-research)
- [Tavily Raises $25M](https://techcrunch.com/2025/08/06/tavily-raises-25m-to-connect-ai-agents-to-the-web/)
- [Exa Raises $85M](https://exa.ai/blog/announcing-series-b)
- [Brave Drops Free API Tier](https://www.implicator.ai/brave-drops-free-search-api-tier-puts-all-developers-on-metered-billing/)
