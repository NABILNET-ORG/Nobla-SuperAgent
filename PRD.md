# Nobla Agent — Product Requirements Document (PRD)

**Version:** 1.1
**Date:** March 24, 2026
**Status:** In Development — Phases 1-3 + Phase 4-Pre + 4A + 4C Complete
**Author:** [NABILNET.AI](https://nabilnet.ai)

---

## Table of Contents
1. [Executive Summary](#1-executive-summary)
2. [Problem Statement](#2-problem-statement)
3. [Market Research](#3-market-research)
4. [Product Vision](#4-product-vision)
5. [Target Users](#5-target-users)
6. [System Architecture](#6-system-architecture)
7. [Tech Stack](#7-tech-stack)
8. [Security Architecture](#8-security-architecture)
9. [Feature Requirements](#9-feature-requirements)
10. [Voice & Persona System](#10-voice--persona-system)
11. [Multi-Agent System](#11-multi-agent-system)
12. [Deployment Options](#12-deployment-options)
13. [Cost Structure](#13-cost-structure)
14. [Project Structure](#14-project-structure)
15. [Development Phases & Roadmap](#15-development-phases--roadmap)
16. [Competitive Analysis](#16-competitive-analysis)
17. [Success Metrics](#17-success-metrics)
18. [Risks & Mitigations](#18-risks--mitigations)

---

## 1. Executive Summary

**Nobla Agent** is an open-source, privacy-first, ultra-capable AI super agent that unifies the best capabilities from 35+ existing AI agent projects while fixing their critical shortcomings. It is controlled primarily through a Flutter mobile app with voice/avatar interaction powered by NVIDIA PersonaPlex, and alternatively through 20+ messaging channels.

**Key Principles:**
- **Security First** — 4-tier permission model, sandboxed execution, full audit trail (fixing OpenClaw's CVEs)
- **Free/Low-Cost** — Multi-LLM routing with local + free API options
- **Privacy-First** — All data stays on user's machine by default
- **Reliability Over Capability** — 10 things done perfectly > 100 things done poorly
- **One Agent, Everything** — Replaces 5+ separate AI tools with one unified super agent
- **Open Source** — MIT/Apache 2.0 licensed, community-driven

---

## 2. Problem Statement

### Current Landscape Issues (Based on Research)

| Problem | Evidence | Impact |
|---------|----------|--------|
| **Critical security vulnerabilities** | OpenClaw CVE-2026-25253 (CVSS 8.8), 135K+ exposed instances, ClawJacked flaw | Users' machines compromised remotely |
| **Malware-infested marketplaces** | 1,000+ malicious skills on ClawHub, 354 from single user | Data exfiltration, credential theft |
| **Runaway costs** | Users report $200+/day, $400 testing costs | Financial harm, trust erosion |
| **Complex setup** | OpenClaw: 430K lines, "legitimate engineering project" | Locks out 95% of potential users |
| **Unreliable execution** | Auto-GPT loops, Open Interpreter freezes, agents hallucinate | Wasted time, broken trust |
| **Fragmented capabilities** | No single agent does search + voice + computer control + memory + channels | Users need 5+ tools |
| **No mobile-first experience** | All agents are desktop/CLI-first | Can't control agent on the go |
| **Weak voice support** | Only 5 of 35 projects offer meaningful voice | Missing the most natural interface |
| **No cost controls** | Most agents have no budget limits | Unpredictable spending |
| **Basic memory** | Most agents forget between sessions | Can't learn or improve |

### User Sentiment (Reddit/Hacker News Consensus)
> "Simpler alternatives like Claude Code with a Telegram integration cover 99% of real-world use cases without the security risks or runaway costs."

> Users want agents that are **reliable over capable** — they'd rather have an agent that does 10 things perfectly than 100 things unreliably.

---

## 3. Market Research

### 3.1 Competitive Landscape (35 Projects Analyzed)

#### Tier 1: Personal AI Assistants
| Project | Stars | Strengths | Weaknesses |
|---------|-------|-----------|------------|
| **OpenClaw** | 319K | 20+ channels, skills platform, cron/webhooks | Security disasters, complex setup, costly |
| **CoPaw** | 12.4K | Modular, persistent memory (ReMe), China ecosystem | Beta quality, poor built-in skills |
| **Open WebUI** | 65K | Best local LLM frontend, voice/video calls | Not an agent — just a UI |
| **Khoj** | 32.8K | "Second brain", deep document integration | Limited automation |
| **Jan.ai** | 25K | 100% offline, MCP support | No voice, limited tools |
| **LocalAI** | 30K | Drop-in OpenAI API, voice cloning, P2P | Infrastructure tool, not end-user agent |
| **Leon AI** | 15K | Voice, beginner-friendly | Small ecosystem |

#### Tier 2: Computer Control Agents
| Project | Stars | Strengths | Weaknesses |
|---------|-------|-----------|------------|
| **UI-TARS Desktop** (ByteDance) | 27K | SOTA GUI vision, no HTML parsing needed | Desktop only, no mobile |
| **Agent S** (Simular) | 15K | 69.9% OSWorld score, beats Claude/OpenAI | Research-focused |
| **Agent Zero** | 13.5K | Docker VM, dynamic tool creation | Complex, single-user |

#### Tier 3: Multi-Agent Frameworks
| Project | Stars | Strengths | Weaknesses |
|---------|-------|-----------|------------|
| **CrewAI** | 44.5K | Role-based collaboration, fastest-growing | Framework, not end-user product |
| **MetaGPT** | 45K | Software company simulation | Narrow use case |
| **AutoGen** (Microsoft) | 50.4K | Enterprise backing | Merging into MS Agent Framework |
| **Dify** | 100K | Visual workflows, 50+ tools, RAG | SaaS-focused |
| **n8n** | 179K | 400+ integrations | Workflow tool, not AI agent |

#### Tier 4: Coding Agents
| Project | Stars | Strengths | Weaknesses |
|---------|-------|-----------|------------|
| **OpenHands** | 65K | Most Devin-like, 50%+ GitHub issues | Coding only |
| **Cline** | 58.2K | VS Code native, 5M installs | IDE plugin, not standalone |
| **Aider** | 30K | Terminal AI pair programming | Coding only |

#### Tier 5: Search/Research
| Project | Stars | Strengths | Weaknesses |
|---------|-------|-----------|------------|
| **Vane** | 33.1K | Privacy-first AI search, self-hosted | Search only, not an agent |
| **GPT Researcher** | 25.6K | Autonomous deep research with citations | Research only |

### 3.2 User Feedback Analysis

#### What Users LOVE (Must Have)
1. Local/privacy-first execution
2. Morning briefings / automated daily reports
3. Multi-channel messaging (be where users are)
4. Persistent memory that learns over time
5. Free/open-source with no vendor lock-in
6. Developer-friendly code review automation
7. Skills/plugin extensibility

#### What Users HATE (Must Fix)
1. Security vulnerabilities and unsafe defaults
2. Malware in skill marketplaces
3. Runaway API costs with no controls
4. Complex setup requiring engineering expertise
5. Post-update breakages destroying workflows
6. Prompt injection attacks with no defense
7. Agents that loop, hallucinate, or fail silently

#### What Users REQUEST (Must Build)
1. Better sandboxing (code runs isolated, not on bare metal)
2. Cost controls (budgets, alerts, auto-shutoff)
3. Multi-model routing (expensive for hard, cheap for easy)
4. Multi-agent collaboration (sub-agents working together)
5. Simpler one-click setup
6. Vetted marketplace with malware scanning
7. Mobile-first experience
8. Voice interaction

---

## 4. Product Vision

### 4.1 One-Line Vision
**"One agent to rule them all — secure, smart, and always available."**

### 4.2 Core Value Proposition
Nobla Agent is the first AI super agent that:
- **Replaces 5+ AI tools** with one unified agent
- **Is actually secure** (4-tier permissions, sandbox, audit, kill switch)
- **Is mobile-first** (Flutter app with voice + avatar as primary interface)
- **Is free/low-cost** (local LLMs + free APIs + smart routing)
- **Learns and improves** (4-type memory + self-improvement + procedural learning)
- **Controls your computer** (vision-based screen understanding + full system control)
- **Speaks naturally** (PersonaPlex full-duplex + voice cloning + emotion detection)
- **Connects everywhere** (20+ messaging channels + 50+ productivity integrations)
- **Is open source** (community-driven, no vendor lock-in)

---

## 5. Target Users

### Primary
- **Tech-savvy professionals** who want to automate their digital life
- **Developers** who want an AI assistant for coding, DevOps, and productivity
- **Power users** who are frustrated with fragmented AI tools

### Secondary
- **Small teams** who want a shared AI assistant for collaboration
- **Privacy-conscious users** who refuse cloud-only solutions
- **Arabic-speaking users** (first-class Levantine Arabic voice support)

### Tertiary
- **Smart home enthusiasts** who want voice-controlled home automation
- **Content creators** who need automated social media management
- **Students** who want an AI tutor and research assistant

---

## 6. System Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    FLUTTER MOBILE APP                        │
│            (Primary Interface — iOS + Android)               │
│                                                              │
│  ┌────────┐ ┌────────┐ ┌─────────┐ ┌──────────┐ ┌────────┐ │
│  │  Chat  │ │ Voice  │ │ Avatar  │ │Dashboard │ │Settings│ │
│  │  (NLP) │ │ (STT/  │ │ (Rive/  │ │(Status/  │ │(Config/│ │
│  │        │ │  TTS)  │ │ Lottie) │ │Controls) │ │Security│ │
│  └────────┘ └────────┘ └─────────┘ └──────────┘ └────────┘ │
└──────────────────────────┬──────────────────────────────────┘
                           │ WebSocket (TLS) / HTTPS
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                     NOBLA GATEWAY                            │
│               (Python FastAPI — Control Plane)               │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  Core Services                                        │   │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌─────────┐ │   │
│  │  │Auth & JWT│ │ Session  │ │ Channel  │ │  Audit  │ │   │
│  │  │ Manager  │ │ Manager  │ │ Router   │ │ Logger  │ │   │
│  │  └──────────┘ └──────────┘ └──────────┘ └─────────┘ │   │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌─────────┐ │   │
│  │  │  Cron &  │ │ Webhook  │ │  Cost    │ │  Kill   │ │   │
│  │  │Scheduler │ │ Manager  │ │ Control  │ │ Switch  │ │   │
│  │  └──────────┘ └──────────┘ └──────────┘ └─────────┘ │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  Intelligence Layer                                   │   │
│  │  ┌────────────┐  ┌──────────────┐  ┌──────────────┐ │   │
│  │  │ LLM Router │  │ Memory Engine│  │ Search Engine│ │   │
│  │  │            │  │              │  │              │ │   │
│  │  │ • Ollama   │  │ • Episodic   │  │ • Brave API  │ │   │
│  │  │ • Gemini   │  │ • Semantic   │  │ • SearXNG    │ │   │
│  │  │ • DeepSeek │  │ • Procedural │  │ • Academic   │ │   │
│  │  │ • Groq     │  │ • Knowledge  │  │ • Domain     │ │   │
│  │  │ • OpenAI   │  │   Graph      │  │   Scoped     │ │   │
│  │  │ • Claude   │  │ • RAG        │  │ • Citations  │ │   │
│  │  │ • Any LLM  │  │ • ChromaDB   │  │              │ │   │
│  │  │            │  │              │  │              │ │   │
│  │  │ Routing:   │  │ Self-improve:│  │ Modes:       │ │   │
│  │  │ Hard→Best  │  │ Learn from   │  │ Speed/       │ │   │
│  │  │ Easy→Cheap │  │ interactions │  │ Balanced/    │ │   │
│  │  │ Fallback   │  │              │  │ Deep         │ │   │
│  │  └────────────┘  └──────────────┘  └──────────────┘ │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  Voice Engine                                         │   │
│  │  ┌─────────────────┐  ┌───────────────────────────┐  │   │
│  │  │ Default (Free)  │  │ Premium (PersonaPlex)     │  │   │
│  │  │ • Faster-Whisper │  │ • 7B speech-to-speech     │  │   │
│  │  │   + Levantine AR│  │ • Full-duplex real-time   │  │   │
│  │  │ • Fish Speech/  │  │ • Voice conditioning      │  │   │
│  │  │   CosyVoice TTS│  │ • Persona text prompts    │  │   │
│  │  │ • Emotion detect│  │ • Requires GPU (A100/4090)│  │   │
│  │  └─────────────────┘  └───────────────────────────┘  │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  Tool Platform (100+ Tools)                           │   │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌─────────┐ │   │
│  │  │ Browser  │ │  Screen  │ │ Computer │ │  Code   │ │   │
│  │  │ Control  │ │  Vision  │ │ Control  │ │Executor │ │   │
│  │  │(Chromium)│ │(UI-TARS) │ │(KB/Mouse)│ │(Sandbox)│ │   │
│  │  └──────────┘ └──────────┘ └──────────┘ └─────────┘ │   │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌─────────┐ │   │
│  │  │  Email   │ │ Calendar │ │ Finance  │ │  Media  │ │   │
│  │  │ Manager  │ │ Manager  │ │ Tracker  │ │ Creator │ │   │
│  │  └──────────┘ └──────────┘ └──────────┘ └─────────┘ │   │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌─────────┐ │   │
│  │  │  Social  │ │  Smart   │ │  Health  │ │ Travel  │ │   │
│  │  │  Media   │ │  Home    │ │ Tracker  │ │ Planner │ │   │
│  │  └──────────┘ └──────────┘ └──────────┘ └─────────┘ │   │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌─────────┐ │   │
│  │  │  OCR /   │ │ Database │ │  System  │ │   SSH   │ │   │
│  │  │  Docs    │ │ Manager  │ │ Monitor  │ │ Remote  │ │   │
│  │  └──────────┘ └──────────┘ └──────────┘ └─────────┘ │   │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌─────────┐ │   │
│  │  │  Git /   │ │   Web    │ │   Form   │ │  Notes  │ │   │
│  │  │  CI/CD   │ │ Scraper  │ │  Filler  │ │ Manager │ │   │
│  │  └──────────┘ └──────────┘ └──────────┘ └─────────┘ │   │
│  │  ┌──────────┐ ┌──────────┐                           │   │
│  │  │Education │ │ Security │                           │   │
│  │  │  Tutor   │ │  Tools   │                           │   │
│  │  └──────────┘ └──────────┘                           │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  Multi-Agent Orchestrator                             │   │
│  │  • Agent Cloning (parallel instances)                 │   │
│  │  • Sub-agents (specialized tasks)                     │   │
│  │  • A2A Protocol (agent-to-agent)                      │   │
│  │  • Role-based agents (researcher/coder/reviewer)      │   │
│  │  • MCP Client + Server                                │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  Channels (20+)                                       │   │
│  │  Telegram | Discord | WhatsApp | Slack | Signal       │   │
│  │  iMessage | MS Teams | Google Chat | Matrix | IRC     │   │
│  │  Feishu | LINE | Mattermost | WebChat | DingTalk     │   │
│  │  QQ | Nostr | Synology Chat | Twitch | Zalo          │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  Sandbox & Isolation                                  │   │
│  │  • Docker containers for code execution               │   │
│  │  • gVisor/Firecracker for sensitive operations        │   │
│  │  • Network isolation per container                    │   │
│  │  • File system isolation with volume mounts           │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

---

## 7. Tech Stack

| Layer | Technology | Rationale |
|-------|-----------|-----------|
| **Backend Framework** | Python 3.12+ / FastAPI | Best AI/ML ecosystem, async, fast |
| **WebSocket** | FastAPI WebSocket + uvicorn | Real-time bidirectional communication |
| **Mobile App** | Flutter 3.x / Dart | Cross-platform iOS + Android, single codebase |
| **State Management** | Riverpod (Flutter) | Scalable, testable, recommended for Flutter |
| **Local LLM** | Ollama | Supports all open models, REST API, easy setup |
| **Cloud LLM** | Gemini (free), Groq (free), DeepSeek (cheap), OpenAI, Claude | Multi-provider for reliability + cost optimization |
| **STT (Default)** | Faster-Whisper | 4x faster than Whisper, same quality |
| **STT (Arabic)** | Custom Levantine model via Faster-Whisper | User's trained model for Arabic dialects |
| **TTS (Default)** | Fish Speech V1.5 / CosyVoice2-0.5B | Open-source, voice cloning, multilingual |
| **Voice Premium** | NVIDIA PersonaPlex 7B | Full-duplex speech-to-speech, persona control |
| **Emotion Detection** | Hume AI / open-source alternative | Detect user mood, adapt responses |
| **Search Primary** | Brave Search API | Independent index, LLM Context API, $5/1K queries |
| **Search Fallback** | SearXNG (self-hosted) | Free, private, meta-search |
| **Vector DB** | ChromaDB | Local, Python-native, free |
| **Structured DB** | SQLite | Zero config, embedded, proven |
| **Knowledge Graph** | NetworkX + SQLite | Local graph storage, Python-native |
| **Sandbox** | Docker + gVisor | Industry standard, OWASP recommended |
| **Screen Vision** | UI-TARS / screenshot analysis | SOTA GUI understanding without HTML parsing |
| **OCR** | Tesseract + EasyOCR | Free, multilingual |
| **Image Generation** | Stable Diffusion (local) / DALL-E API | Free local + API option |
| **Browser Automation** | Playwright | Cross-browser, reliable |
| **Cron/Scheduling** | APScheduler | Python-native, persistent job storage |
| **MCP** | Model Context Protocol | Industry standard for tool integration |
| **A2A** | Agent-to-Agent Protocol (Google) | Multi-agent communication standard |
| **Channels** | python-telegram-bot, discord.py, etc. | Mature, well-documented libraries |
| **Smart Home** | Home Assistant MCP Server | 2000+ device integrations, 80+ tools |
| **Encryption** | AES-256 (at rest), TLS 1.3 (in transit) | Industry standard |
| **Audit Logging** | OpenTelemetry-compatible | Standard observability format |
| **Avatar (Mobile)** | Rive / Lottie animations | Lightweight, cross-platform, beautiful |

---

## 8. Security Architecture

### 8.1 4-Tier Permission Model

```
┌─────────────────────────────────────────────────────┐
│ TIER 4: ADMIN                                        │
│ Full system control, keyboard/mouse, screen record   │
│ Every action: logged + approved + undoable            │
├─────────────────────────────────────────────────────┤
│ TIER 3: ELEVATED                                     │
│ Full filesystem, code+network, SSH, Git, packages    │
│ Each action needs mobile approval (2FA-style)        │
├─────────────────────────────────────────────────────┤
│ TIER 2: STANDARD                                     │
│ Designated folders, sandboxed code, web browse,      │
│ whitelisted APIs. Initial user approval.             │
├─────────────────────────────────────────────────────┤
│ TIER 1: SAFE (Default)                               │
│ Read-only. Search, summarize, answer.                │
│ No files, no code, no network, no commands.          │
└─────────────────────────────────────────────────────┘
```

### 8.2 Security Features (Fixing Industry Failures)

| Feature | Addresses | Implementation |
|---------|-----------|----------------|
| **Sandbox Execution** | Open Interpreter's bare-metal code, OpenClaw's RCE | Docker/gVisor containers for all code execution |
| **Audit Trail** | No accountability in existing agents | OpenTelemetry-compatible logging, every action timestamped |
| **Kill Switch** | Auto-GPT's runaway loops | Instant stop from mobile app, emergency shutdown endpoint |
| **Cost Controls** | OpenClaw's $200+/day bills | Per-session token budget, daily limit, auto-shutoff |
| **Rate Limiting** | Loop prevention | Max iterations per task, configurable cooldowns |
| **Input Sanitization** | Prompt injection attacks | Structured output validation, input filtering |
| **Marketplace Vetting** | OpenClaw's 1000+ malicious skills | VirusTotal scan + code review + community reports |
| **Encrypted Storage** | Data at rest vulnerability | AES-256 encryption for secrets, memory, config |
| **Network Isolation** | Sandbox escape via network | Containers have no host network access by default |
| **Undo System** | Irreversible destructive actions | Every file/system change recorded and rollback-able |
| **DM Pairing** | Unauthorized access via messaging | Pairing codes for new contacts, allowlist management |
| **Secret Management** | Hardcoded credentials | .env files, encrypted vault, no plaintext secrets |

### 8.3 OWASP Top 10 Compliance (Agentic Applications)
- Treat agent as untrusted third party
- Least-privilege with scoped API keys per tool
- Human-in-the-loop for all high-risk actions (Tier 3+)
- Comprehensive audit logging aligned with OpenTelemetry
- Kill switches for runaway agents
- Input/output validation at every boundary

---

## 9. Feature Requirements

### 9.1 Core Features (Phase 1-2)

#### FR-001: Gateway Server
- WebSocket + REST API with TLS
- JWT authentication and session management
- Rate limiting and request throttling
- Health check and status endpoints

#### FR-002: 4-Tier Security System
- Configurable security levels from Flutter dashboard
- Per-action approval flow for Tier 3+
- Real-time approval notifications on mobile

#### FR-003: Sandbox System
- Docker container management for code execution
- File system isolation with volume mounts
- Network isolation with configurable rules
- Resource limits (CPU, memory, time)

#### FR-004: Audit Logging
- OpenTelemetry-compatible event logging
- Every action: who, what, when, result, reversible?
- Log viewer in Flutter app
- Export capability for compliance

#### FR-005: Kill Switch
- Instant stop from mobile app (one tap)
- Emergency shutdown API endpoint
- Graceful cleanup of running operations
- Notification to all connected clients

#### FR-006: Cost Control
- Per-session token budget
- Daily/weekly/monthly spending limits
- Automatic shutoff when budget exceeded
- Cost dashboard in Flutter app
- Per-provider cost tracking

#### FR-007: Multi-LLM Router
- Abstraction layer supporting any LLM provider
- Smart routing: task complexity → model selection
- Supported: Ollama, Gemini, DeepSeek, Groq, OpenAI, Claude
- Fallback chain: primary → secondary → tertiary
- User-configurable model preferences per task type

#### FR-008: Advanced Memory System
- **Episodic**: conversation history with timestamps + context
- **Semantic**: extracted facts/knowledge (ChromaDB embeddings)
- **Procedural**: learned skills/workflows (reusable)
- **Knowledge Graph**: entities + relationships (NetworkX)
- **RAG Pipeline**: embed → store → retrieve → augment
- Natural language search across all memory types
- Memory management UI in Flutter app

#### FR-009: Smart Search
- Brave Search API (primary, LLM Context API)
- SearXNG self-hosted (fallback, free, private)
- Search modes: Speed, Balanced, Deep Research
- Source citations on every answer
- Academic search (ArXiv, Google Scholar)
- Domain-scoped search

### 9.2 Voice & Interface Features (Phase 3)

#### FR-010: Voice Engine (Default — Free)
- Faster-Whisper STT with language auto-detection
- Levantine Arabic model for Arabic speakers
- Fish Speech V1.5 / CosyVoice2 TTS (open-source, voice cloning)
- Voice Activity Detection (VAD)
- Audio streaming via WebSocket

#### FR-011: Voice Engine (Premium — PersonaPlex)
- PersonaPlex 7B deployment on server (Docker)
- Full-duplex conversation (listen + speak simultaneously)
- Voice prompt conditioning (custom voice character)
- Text prompt conditioning (persona attributes)
- CPU offload mode for smaller GPUs

#### FR-012: Emotion Detection
- Detect user mood from voice (Hume AI or open-source)
- Adapt response tone based on emotional context

#### FR-013: Persona System
- Pre-built personas: Professional, Friendly, Military, Custom
- Custom persona creation (name, voice, personality, language style)
- Persona marketplace (share/download community personas)
- Per-conversation persona switching

#### FR-014: Flutter App — Chat
- Text messaging with markdown support
- Voice chat with waveform visualization
- Push-to-talk and auto-detect modes
- File sharing (images, documents, audio, video)
- Conversation history with search
- Background voice mode

#### FR-015: Flutter App — Dashboard
- Agent status (online/offline/busy)
- Security level selector (4 tiers)
- Active tasks and progress
- Cost tracker (today/week/month)
- Quick actions (kill switch, restart, change model)

#### FR-016: Flutter App — Avatar
- Animated avatar synced with speech (Rive/Lottie)
- Lip-sync with TTS output
- Emotion-reactive expressions
- Customizable avatar appearance

### 9.3 Computer Control Features (Phase 4)

#### FR-017: Screen Vision ✅ (Phase 4A — Implemented)
- ✅ Screenshot capture and analysis (`screenshot.capture` — mss, multi-monitor, downscaling)
- ✅ UI-TARS integration for GUI element detection (`ui.detect_elements` — OCR heuristics + UI-TARS stub)
- ✅ OCR text extraction (`ocr.extract` — Tesseract primary + EasyOCR fallback)
- ✅ Natural language element targeting (`ui.target_element` — keyword matching + fuzzy search)

#### FR-018: Computer Control
- Mouse: move, click, drag, scroll
- Keyboard: type, shortcuts, key combinations
- Application launch and management
- Window management (resize, move, minimize, maximize)
- File management (browse, create, delete, move, copy)
- Clipboard management

#### FR-019: Code Execution
- Sandboxed execution: Python, JavaScript, Bash, more
- Package installation in sandbox
- Code generation from natural language
- Debug assistant (analyze errors, suggest fixes)
- Git integration (clone, commit, push, PR creation)
- Project scaffolding from description

#### FR-020: Remote Control
- SSH integration with audit logging
- Remote command execution
- File transfer (SCP/SFTP)
- Multi-machine orchestration

### 9.4 Channels & Integrations (Phase 5)

#### FR-021: Messaging Channels (20+)
Telegram, Discord, WhatsApp, Slack, Signal, iMessage, Microsoft Teams, Google Chat, Matrix, IRC, Feishu/Lark, LINE, Mattermost, WebChat, DingTalk, QQ, Nostr, Synology Chat, Twitch, Zalo

#### FR-022: Channel Features
- Unified message format across all channels
- Media handling (images, audio, video, files)
- Group chat support with activation modes
- Channel-specific formatting
- DM pairing/security

#### FR-023: Productivity Integrations
- Email (Gmail, Outlook): read, send, organize, summarize
- Calendar (Google, Apple): read, create, modify events
- Notes (Obsidian, Notion, Apple Notes): sync, search, create
- Task managers (Todoist, Linear, Jira, Trello)
- Cloud storage (Google Drive, Dropbox, OneDrive)

### 9.5 Automation & Multi-Agent (Phase 6)

#### FR-024: Automation Engine
- Cron jobs with APScheduler
- Webhook receiver and processor
- Natural language workflow builder
- IFTTT-style trigger-action rules
- Batch processing (parallel)
- Morning/Evening briefings
- Scheduled report generation
- Web scraping (automated data collection)
- Form filling (auto-complete web forms)

#### FR-025: Multi-Agent System
- Agent cloning (parallel instances)
- Sub-agents for specialized tasks
- A2A Protocol (agent-to-agent communication)
- Role-based agents (researcher, coder, reviewer)
- Configurable memory sharing/isolation
- Agent orchestrator for multi-agent workflows

#### FR-026: MCP Integration
- MCP Client (connect to external MCP servers)
- MCP Server (expose Nobla to other tools)
- Dynamic tool discovery
- MCP marketplace

### 9.6 Full Feature Set (Phase 7)

#### FR-027: Media & Creative
- Image generation (Stable Diffusion / API)
- Image editing (crop, resize, filter, background removal)
- Video generation (AI video models)
- Music generation (AI music models)
- Presentation builder (auto-create slides)
- Document converter (PDF, DOCX, XLSX, PPTX)

#### FR-028: Finance
- Expense tracking (parse notifications, categorize)
- Budget management (alerts, limits)
- Crypto portfolio tracking
- Stock tracking (real-time, alerts)
- Bill reminders
- Price comparison

#### FR-029: Health & Life
- Health data integration (Apple Health, Google Fit)
- Medication reminders
- Meal planning (recipes, grocery lists)
- Exercise suggestions
- Habit tracking
- Sleep analysis

#### FR-030: Social Media
- Multi-platform posting and scheduling
- Content calendar
- Engagement monitoring
- Smart auto-reply
- Reputation monitoring

#### FR-031: Smart Home
- Home Assistant integration (2000+ devices, 80+ tools)
- Google Home / Alexa integration
- Automation rules (time, event, condition triggers)
- Energy monitoring
- Security camera integration

#### FR-032: Education
- AI tutor (explains at your level)
- Flashcard generation
- Language practice (conversation)
- Exam prep (practice questions)
- Lecture summarization

#### FR-033: Travel
- Flight/hotel search and comparison
- Trip itinerary generation
- Navigation suggestions
- Airport reminders

#### FR-034: System Administration
- System monitoring (CPU, RAM, disk, network)
- Process management
- Network monitoring
- Backup management
- Database management
- Log analysis

#### FR-035: Security Tools
- Dark web monitoring (credential leak alerts)
- Password manager integration (Bitwarden/1Password)
- System security scanning
- VPN management

### 9.7 Self-Improvement System

#### FR-036: Self-Improving Agent
- User feedback loops (response ratings improve future quality)
- Procedural memory (successful workflows saved and reused)
- Skill auto-creation (task repeated 3x → reusable skill)
- A/B model routing (test approaches, keep the better one)
- Community skill marketplace (vetted + scanned)

### 9.8 Proactive Intelligence

#### FR-037: Proactive Agent
- Pattern learning (notices routines, automates them)
- Smart notifications ("Flight delayed 30 min" before you check)
- Anomaly detection ("Unusual $500 charge on your card")
- Recommendation engine (suggests actions based on context)
- Deadline awareness ("Report due tomorrow, want me to draft it?")
- Morning briefing (auto-generated daily report at preferred time)

---

## 10. Voice & Persona System

### 10.1 Voice Pipeline

```
USER SPEAKS → [Flutter App captures audio]
             → [WebSocket stream to Gateway]
             → [Language Detection]
             ├── Arabic → Levantine Faster-Whisper model
             └── Other → Standard Faster-Whisper large-v3
             → [Text to LLM Router]
             → [LLM generates response]
             → [TTS Engine]
             ├── Default → Fish Speech / CosyVoice2
             └── Premium → PersonaPlex (full-duplex)
             → [WebSocket stream to Flutter App]
             → [Avatar lip-sync + audio playback]
```

### 10.2 PersonaPlex Integration

```
CONFIGURATION:
├── Voice Prompt: Audio tokens defining vocal characteristics
├── Text Prompt: Persona attributes (role, background, style)
├── Model: personaplex-7b-v1 (via Docker/GPU server)
└── Fallback: If GPU unavailable → default pipeline

DEPLOYMENT:
├── Local: NVIDIA GPU (RTX 4090+ recommended, A100 ideal)
├── Cloud: RunPod/Vast.ai A100 on-demand (~$1.10/hr)
└── CPU Offload: --cpu-offload flag for smaller GPUs (slower)
```

### 10.3 Persona Attributes
```yaml
persona:
  name: "Nobla"
  language_style: "professional, clear, concise"
  voice: "custom_voice_prompt.wav"
  personality: "helpful, proactive, security-aware"
  background: "Expert AI assistant specialized in productivity"
  rules:
    - "Always confirm before destructive actions"
    - "Explain reasoning when asked"
    - "Adapt tone to user's emotional state"
```

---

## 11. Multi-Agent System

### 11.1 Agent Types
```
ORCHESTRATOR (Main Nobla Instance)
├── RESEARCHER — Deep research, fact-checking, citations
├── CODER — Code generation, debugging, git operations
├── WRITER — Content creation, editing, translation
├── ANALYST — Data analysis, reporting, visualization
├── MONITOR — System monitoring, alerts, health checks
├── AUTOMATOR — Workflow execution, cron jobs, batch processing
└── CUSTOM — User-defined agents with custom roles
```

### 11.2 Communication
- **MCP Protocol** — Tool integration standard
- **A2A Protocol** — Agent-to-agent communication (Google standard)
- **Shared Memory** — Configurable: isolated or shared knowledge base
- **Task Queue** — Central task distribution with priority handling

---

## 12. Deployment Options

### Option A: Local Only ($0/month)
```
User's Computer → Docker (Nobla Backend + Ollama + SearXNG)
Flutter App → Same network or Tailscale (free VPN)
```
**Requirements:** 8GB+ RAM, 4GB+ VRAM (for local LLM)
**Limitation:** Must be on same network (or use Tailscale)

### Option B: VPS ($10-50/month)
```
VPS (cloud) → Docker (Nobla Backend + SearXNG) → API LLMs
Flutter App → VPS (accessible from anywhere)
```
**Requirements:** VPS with 2+ vCPU, 4GB+ RAM
**Advantage:** Always-on, accessible from anywhere

### Option C: Hybrid — Recommended ($0-5/month)
```
User's Computer → Docker (Nobla Backend + Ollama)
                → Relay Server (lightweight, free tier — e.g., Cloudflare Tunnel)
Flutter App → Relay → Computer (accessible from anywhere)
```
**Requirements:** Computer with 8GB+ RAM
**Advantage:** Free, private, accessible from anywhere

### Option D: With PersonaPlex (+$30-100/month)
```
Any of above + GPU Server (local or cloud) for PersonaPlex
On-demand pricing: ~$0.04-0.09 per 5-minute voice call
```

---

## 13. Cost Structure

### For End Users
| Deployment | Monthly Cost | Best For |
|-----------|-------------|----------|
| Full local (Ollama only) | **$0** | Users with GPU (8GB+ VRAM) |
| Hybrid (local + free APIs) | **$0-5** | Best balance (recommended) |
| Cloud APIs only (Gemini+Groq) | **$0-10** | Users without GPU |
| Full VPS | **$10-50** | Always-on, accessible everywhere |
| PersonaPlex voice (on-demand) | **+$30-100** | Premium voice experience |
| PersonaPlex voice (dedicated GPU) | **+$300-1200** | Professional use |

### Free API Options
| Provider | Free Tier | Quality |
|----------|-----------|---------|
| Google Gemini | 15 RPM, 1M tokens/day | Excellent |
| Groq | 6K tokens/min | Good (fast) |
| DeepSeek | $0.14/M input tokens | Excellent (very cheap) |
| Ollama (local) | Unlimited | Depends on model/GPU |

---

## 14. Project Structure

```
nobla-agent/
├── backend/                       # Python backend
│   ├── nobla/
│   │   ├── __init__.py
│   │   ├── main.py               # FastAPI app entry
│   │   ├── gateway/              # WebSocket + REST API
│   │   │   ├── server.py         # FastAPI server
│   │   │   ├── websocket.py      # WebSocket handler
│   │   │   ├── routes/           # REST endpoints
│   │   │   └── middleware/       # Auth, CORS, rate limit
│   │   ├── brain/                # LLM intelligence
│   │   │   ├── router.py         # Smart LLM router
│   │   │   ├── providers/        # Ollama, Gemini, etc.
│   │   │   ├── prompts/          # System prompts, templates
│   │   │   └── agents/           # Multi-agent orchestrator
│   │   ├── memory/               # Advanced memory system
│   │   │   ├── episodic.py       # Conversation history
│   │   │   ├── semantic.py       # Knowledge embeddings (ChromaDB)
│   │   │   ├── procedural.py     # Learned workflows
│   │   │   ├── knowledge_graph.py # Entity relationships
│   │   │   └── rag.py            # RAG pipeline
│   │   ├── tools/                # Tool implementations
│   │   │   ├── base.py           # Tool base class
│   │   │   ├── browser/          # Browser automation
│   │   │   ├── vision/           # Screen capture + UI-TARS
│   │   │   ├── computer/         # Mouse, keyboard, files
│   │   │   ├── search/           # Brave + SearXNG
│   │   │   ├── code/             # Code execution (sandboxed)
│   │   │   ├── email/            # Email integration
│   │   │   ├── calendar/         # Calendar integration
│   │   │   ├── finance/          # Finance tools
│   │   │   ├── media/            # Image/video/audio gen
│   │   │   ├── social/           # Social media management
│   │   │   ├── smarthome/        # Home Assistant
│   │   │   ├── health/           # Health tracking
│   │   │   ├── travel/           # Travel planning
│   │   │   ├── education/        # AI tutor
│   │   │   ├── sysadmin/         # System monitoring
│   │   │   ├── security_tools/   # Dark web, passwords
│   │   │   ├── documents/        # OCR, PDF, DOCX
│   │   │   ├── git_ops/          # Git, CI/CD
│   │   │   ├── ssh/              # Remote control
│   │   │   ├── scraper/          # Web scraping
│   │   │   └── database/         # DB management
│   │   ├── voice/                # Voice engine
│   │   │   ├── stt.py            # Speech-to-text (Faster-Whisper)
│   │   │   ├── tts.py            # Text-to-speech (Fish/Coqui)
│   │   │   ├── personaplex.py    # PersonaPlex integration
│   │   │   ├── emotion.py        # Emotion detection
│   │   │   └── persona.py        # Persona management
│   │   ├── security/             # Security layer
│   │   │   ├── auth.py           # JWT, API keys
│   │   │   ├── sandbox.py        # Docker/gVisor management
│   │   │   ├── audit.py          # OpenTelemetry logging
│   │   │   ├── permissions.py    # 4-tier permission system
│   │   │   ├── encryption.py     # AES-256 at rest
│   │   │   ├── kill_switch.py    # Emergency stop
│   │   │   └── cost_control.py   # Budget management
│   │   ├── channels/             # Messaging channels
│   │   │   ├── base.py           # Channel base class
│   │   │   ├── telegram.py
│   │   │   ├── discord.py
│   │   │   ├── whatsapp.py
│   │   │   ├── slack.py
│   │   │   ├── signal.py
│   │   │   ├── imessage.py
│   │   │   ├── teams.py
│   │   │   ├── webchat.py
│   │   │   └── ... (15+ more)
│   │   ├── automation/           # Automation engine
│   │   │   ├── cron.py           # Scheduled tasks
│   │   │   ├── webhooks.py       # Webhook receiver
│   │   │   ├── workflows.py      # Workflow engine
│   │   │   └── triggers.py       # IFTTT-style triggers
│   │   ├── skills/               # Skill platform
│   │   │   ├── loader.py         # Skill discovery/loading
│   │   │   ├── marketplace.py    # Community skills
│   │   │   └── bundled/          # Pre-installed skills
│   │   └── config/               # Configuration
│   │       ├── settings.py       # App settings
│   │       └── defaults.yaml     # Default configuration
│   ├── tests/                    # Test suite
│   ├── docker/                   # Docker configs
│   │   ├── Dockerfile            # Main backend
│   │   ├── Dockerfile.sandbox    # Sandbox container
│   │   └── Dockerfile.personaplex # PersonaPlex
│   ├── docker-compose.yml        # Full stack
│   ├── pyproject.toml
│   └── README.md
│
├── app/                           # Flutter mobile app
│   ├── lib/
│   │   ├── core/                 # Core infrastructure
│   │   │   ├── theme/            # App theme (dark mode default)
│   │   │   ├── routing/          # Navigation (GoRouter)
│   │   │   ├── di/               # Dependency injection (Riverpod)
│   │   │   ├── network/          # WebSocket + HTTP clients
│   │   │   └── config/           # App configuration
│   │   ├── features/             # Feature modules
│   │   │   ├── auth/             # Login, registration, JWT
│   │   │   ├── chat/             # Text + voice chat
│   │   │   ├── dashboard/        # Agent status, controls
│   │   │   ├── voice/            # Voice UI, waveform, recording
│   │   │   ├── avatar/           # Animated avatar display
│   │   │   ├── persona/          # Persona selector/creator
│   │   │   ├── memory/           # Memory viewer/search
│   │   │   ├── search/           # Search interface
│   │   │   ├── automation/       # Workflows, cron manager
│   │   │   ├── agents/           # Multi-agent dashboard
│   │   │   ├── channels/         # Channel configuration
│   │   │   ├── security/         # Security settings, tier selector
│   │   │   ├── finance/          # Finance dashboard
│   │   │   ├── health/           # Health dashboard
│   │   │   ├── smarthome/        # Smart home controls
│   │   │   ├── social/           # Social media manager
│   │   │   ├── screen_mirror/    # See agent's screen
│   │   │   └── settings/         # App settings
│   │   ├── shared/               # Shared widgets, utils
│   │   └── main.dart
│   ├── test/
│   ├── pubspec.yaml
│   └── README.md
│
├── skills/                        # Community skills
│   ├── bundled/                  # Pre-installed
│   └── marketplace/              # Community contributed
│
├── docs/                          # Documentation
│   ├── setup/                    # Installation guides
│   ├── api/                      # API documentation
│   ├── skills/                   # Skill development guide
│   └── security/                 # Security documentation
│
├── docker-compose.yml             # One-command deployment
├── docker-compose.personaplex.yml # With PersonaPlex
├── .env.example                   # Example configuration
├── LICENSE                        # MIT or Apache 2.0
├── CONTRIBUTING.md
├── SECURITY.md
└── README.md
```

---

## 15. Development Phases & Roadmap

### Phase 1: Secure Foundation (Weeks 1-4)
**Goal:** Unbreakable secure backbone.

| # | Task | Priority |
|---|------|----------|
| 1 | Python project setup (FastAPI, pyproject.toml, Docker) | P0 |
| 2 | Gateway server (WebSocket + REST API + TLS) | P0 |
| 3 | JWT authentication + session management | P0 |
| 4 | 4-tier security model | P0 |
| 5 | Docker sandbox system for code execution | P0 |
| 6 | OpenTelemetry audit logging | P0 |
| 7 | Kill switch endpoint + notification | P0 |
| 8 | Cost control (token counting, budgets, auto-shutoff) | P0 |
| 9 | Configuration system (YAML + .env) | P0 |
| 10 | Basic LLM integration (Ollama + Gemini) | P0 |
| 11 | Flutter project setup (clean arch, Riverpod) | P0 |
| 12 | Flutter auth flow (login, JWT) | P0 |
| 13 | Flutter WebSocket connection | P0 |
| 14 | Flutter basic chat UI | P0 |
| 15 | Flutter dashboard (status, security selector) | P0 |
| 16 | Flutter kill switch button | P0 |
| 17 | Flutter push notifications (FCM) | P1 |
| 18 | Unit + integration + security tests | P0 |
| 19 | Docker Compose for one-command deploy | P0 |
| 20 | README + setup documentation | P1 |

**Deliverable:** Secure chat between Flutter app and backend with sandbox execution.

---

### Phase 2: Intelligence Core (Weeks 5-8)
**Goal:** Smart brain with memory and search.

| # | Task | Priority |
|---|------|----------|
| 1 | LLM abstraction layer (any provider) | P0 |
| 2 | Smart routing (complexity → model selection) | P0 |
| 3 | All LLM providers (Ollama, Gemini, DeepSeek, Groq, OpenAI, Claude) | P0 |
| 4 | Fallback chains + token tracking | P0 |
| 5 | Episodic memory (conversation history + context) | P0 |
| 6 | Semantic memory (ChromaDB embeddings) | P0 |
| 7 | Procedural memory (learned workflows) | P1 |
| 8 | Knowledge Graph (NetworkX) | P1 |
| 9 | RAG pipeline (embed → store → retrieve → augment) | P0 |
| 10 | SearXNG Docker integration | P0 |
| 11 | Brave Search API integration | P0 |
| 12 | Search routing (Brave primary, SearXNG fallback) | P0 |
| 13 | Source citations | P0 |
| 14 | Search modes (Speed, Balanced, Deep) | P1 |
| 15 | Academic search (ArXiv, Scholar) | P2 |
| 16 | Flutter memory viewer | P1 |
| 17 | Flutter search UI with citations | P1 |
| 18 | Flutter LLM settings + cost display | P0 |
| 19 | Flutter conversation history with search | P1 |

**Deliverable:** Intelligent agent with persistent memory, smart search, and multi-LLM support.

---

### Phase 3: Voice & Persona (Weeks 9-12)
**Goal:** Natural voice interaction with personality.

| # | Task | Priority |
|---|------|----------|
| 1 | Faster-Whisper STT integration | P0 |
| 2 | Levantine Arabic model integration | P0 |
| 3 | Language auto-detection routing | P0 |
| 4 | Fish Speech / CosyVoice2 TTS | P0 |
| 5 | Voice Activity Detection (VAD) | P1 |
| 6 | Audio streaming WebSocket pipeline | P0 |
| 7 | PersonaPlex 7B Docker deployment | P1 |
| 8 | PersonaPlex full-duplex integration | P1 |
| 9 | Voice/text prompt conditioning | P1 |
| 10 | CPU offload mode | P2 |
| 11 | Emotion detection (Hume AI / open-source) | P2 |
| 12 | Pre-built personas (4 types) | P0 |
| 13 | Custom persona creation | P1 |
| 14 | Persona marketplace | P2 |
| 15 | Flutter voice chat UI (waveform, PTT) | P0 |
| 16 | Flutter avatar display (Rive/Lottie) | P1 |
| 17 | Flutter persona selector/creator | P1 |
| 18 | Flutter background voice mode | P2 |

**Deliverable:** Voice-enabled agent with personas and avatar.

---

### Phase 4: Computer Control & Vision (Weeks 13-16)
**Goal:** See and control the screen like a human.

| # | Task | Priority | Status |
|---|------|----------|--------|
| 0 | Tool Platform Foundation (BaseTool, registry, executor, approval) | P0 | ✅ Phase 4-Pre |
| 1 | Screenshot capture pipeline | P0 | ✅ Phase 4A |
| 2 | UI-TARS integration for GUI detection | P0 | ✅ Phase 4A (stub + OCR fallback) |
| 3 | OCR (Tesseract + EasyOCR) | P0 | ✅ Phase 4A |
| 4 | Natural language element targeting | P0 | ✅ Phase 4A |
| 5 | Mouse control (move, click, drag, scroll) | P0 | Phase 4B |
| 6 | Keyboard control (type, shortcuts) | P0 | Phase 4B |
| 7 | Application launch/management | P0 | Phase 4B |
| 8 | Window management | P1 | Phase 4B |
| 9 | File manager (browse, create, delete, move) | P0 | Phase 4B |
| 10 | Clipboard management | P1 | Phase 4B |
| 11 | Sandboxed code runner (Python, JS, Bash) | P0 | ✅ Complete |
| 12 | Package installation in sandbox | P1 | ✅ Complete |
| 13 | Code generation from natural language | P0 | ✅ Complete |
| 14 | Git integration (clone, commit, push, PR) | P1 | ✅ Complete |
| 15 | SSH integration + audit logging | P1 | Phase 4D |
| 16 | Remote command execution | P1 | Phase 4D |
| 17 | Flutter screen mirror (real-time) | P1 | Phase 4E |
| 18 | Flutter approval dialogs for actions | P0 | Phase 4B |
| 19 | Flutter activity feed (live log) | P0 | Phase 4E |

**Deliverable:** Agent that can see, understand, and control any computer.

---

### Phase 5: Channels & Integrations (Weeks 17-20)
**Goal:** Connect to every messaging platform and productivity tool.

| # | Task | Priority |
|---|------|----------|
| 1 | Channel base class + unified message format | P0 |
| 2 | Telegram bot | P0 |
| 3 | Discord bot | P0 |
| 4 | WhatsApp integration | P0 |
| 5 | Slack bot | P0 |
| 6 | Signal integration | P1 |
| 7 | iMessage (BlueBubbles) | P2 |
| 8 | Microsoft Teams | P1 |
| 9 | Google Chat | P1 |
| 10 | Matrix | P2 |
| 11 | WebChat (browser) | P0 |
| 12 | Remaining channels (IRC, Feishu, LINE, etc.) | P2 |
| 13 | Media handling across channels | P0 |
| 14 | Group chat + activation modes | P1 |
| 15 | DM pairing/security | P0 |
| 16 | Email integration (Gmail, Outlook) | P0 |
| 17 | Calendar integration (Google, Apple) | P0 |
| 18 | Notes integration (Obsidian, Notion) | P1 |
| 19 | Task manager integration (Todoist, Linear) | P2 |
| 20 | Flutter channel manager UI | P0 |
| 21 | Flutter integration setup wizard | P1 |

**Deliverable:** Agent accessible from 20+ channels with productivity integrations.

---

### Phase 6: Automation & Multi-Agent (Weeks 21-24)
**Goal:** Workflows, scheduling, and parallel agents.

| # | Task | Priority |
|---|------|----------|
| 1 | Cron jobs (APScheduler) | P0 |
| 2 | Webhook receiver/processor | P0 |
| 3 | Natural language workflow builder | P0 |
| 4 | IFTTT-style triggers | P1 |
| 5 | Batch processing (parallel) | P1 |
| 6 | Morning/Evening briefings | P0 |
| 7 | Report generation | P1 |
| 8 | Web scraping engine | P1 |
| 9 | Form filling | P2 |
| 10 | Agent cloning (parallel instances) | P0 |
| 11 | Sub-agent spawning | P0 |
| 12 | A2A Protocol implementation | P1 |
| 13 | Role-based agents | P1 |
| 14 | Shared/isolated memory config | P1 |
| 15 | MCP Client | P0 |
| 16 | MCP Server | P0 |
| 17 | MCP marketplace | P2 |
| 18 | Flutter workflow builder UI | P1 |
| 19 | Flutter cron manager | P1 |
| 20 | Flutter multi-agent dashboard | P1 |

**Deliverable:** Self-automating agent with multi-agent collaboration.

---

### Phase 7: Full Feature Set (Weeks 25-32)
**Goal:** All remaining features across 8 categories.

| Category | Key Tasks | Priority |
|----------|----------|----------|
| **Media/Creative** | Image gen, video gen, music gen, presentations | P1 |
| **Finance** | Expense tracking, budgets, crypto, stocks, bills | P1 |
| **Health** | Health data, medications, meals, exercise, sleep | P2 |
| **Social Media** | Multi-platform posting, engagement, auto-reply | P1 |
| **Smart Home** | Home Assistant, Google Home, Alexa, automation | P1 |
| **Education** | AI tutor, flashcards, language practice, exam prep | P2 |
| **Travel** | Flights, hotels, itineraries, airport reminders | P2 |
| **SysAdmin** | System monitor, processes, network, backups, DBs, logs | P1 |
| **Security Tools** | Dark web monitoring, password manager, VPN | P2 |
| **Self-Improvement** | Feedback loops, skill auto-creation, A/B routing | P1 |
| **Proactive Intelligence** | Pattern learning, smart alerts, recommendations | P1 |
| **Flutter Dashboards** | Finance, health, social, smart home, system | P1 |

**Deliverable:** Complete super agent with 100+ capabilities.

---

## 16. Competitive Analysis

### How Nobla Fixes Industry Failures

| Problem (Competitor) | Nobla's Solution |
|---------------------|------------------|
| OpenClaw CVE-2026-25253 (RCE via WebSocket) | TLS WebSocket + JWT auth + rate limiting |
| OpenClaw ClawJacked (malicious site hijack) | Origin validation + CORS + session tokens |
| OpenClaw 1,000+ malicious marketplace skills | VirusTotal scan + code review + community flagging |
| OpenClaw $200+/day runaway costs | Token budgets + daily limits + auto-shutoff |
| OpenClaw 430K-line complex setup | One-command Docker install + Flutter setup wizard |
| CoPaw's poor built-in skills | Thoroughly tested + community-reviewed skill library |
| CoPaw's memory exhaustion | Data truncation + streaming + resource limits |
| Open Interpreter's no sandbox | All code in Docker/gVisor containers |
| Auto-GPT's infinite loops | Max iterations + loop detection + kill switch |
| No mobile-first experience anywhere | Flutter app as primary interface |
| Weak voice support industry-wide | PersonaPlex + Faster-Whisper + open-source TTS |
| Basic memory in most agents | 4-type memory + Knowledge Graph + RAG + self-improvement |
| No cost controls anywhere | Built-in budgets, alerts, and automatic shutoffs |
| Fragmented capabilities | 100+ tools across 12 categories in ONE agent |

---

## 17. Success Metrics

### Launch Metrics (3 months post-launch)
- GitHub stars: 10,000+
- Active users: 1,000+
- Community skills contributed: 50+
- Security incidents: 0

### Growth Metrics (12 months post-launch)
- GitHub stars: 50,000+
- Active users: 10,000+
- Community skills: 500+
- Messaging channels supported: 20+
- Average user retention: 60%+

### Quality Metrics (Ongoing)
- Task success rate: >90%
- Average response time: <3 seconds (text), <500ms (voice)
- User satisfaction score: >4.5/5
- Security audit: pass (quarterly)
- Zero runaway cost incidents

---

## 18. Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Security vulnerability discovered | Medium | Critical | Quarterly security audits, bug bounty program, responsible disclosure |
| Runaway costs for users | Medium | High | Built-in budgets, alerts, auto-shutoff (learn from OpenClaw) |
| LLM API provider changes pricing | Medium | Medium | Multi-provider support, local LLM fallback |
| PersonaPlex GPU costs too high | High | Medium | CPU offload mode, on-demand pricing, free TTS fallback |
| Scope creep (too many features) | High | High | Strict phase-gating, MVP-first approach, community voting on priorities |
| Marketplace abuse (malicious skills) | Medium | High | VirusTotal scanning, code review, sandboxed execution, community flagging |
| Competition from OpenClaw/CoPaw | High | Medium | Better security, mobile-first, voice-first differentiation |
| Complex setup despite Docker | Medium | Medium | Setup wizard in Flutter app, video tutorials, community support |
| Agent hallucinations | High | Medium | RAG grounding, source citations, confidence scoring, user verification |
| Prompt injection attacks | High | High | Input sanitization, structured outputs, security tier enforcement |

---

## Appendix A: Research Sources

### OpenClaw Research
- Unite.AI Review, CyberNews Review, Wikipedia, Northeastern "Privacy Nightmare"
- O'Reilly Analysis, Malwarebytes Safety Analysis, XDA "Stop Using OpenClaw"
- The Hacker News: ClawJacked Flaw, Prompt Injection & Data Exfil
- GitHub Issues: #35077, #46109 — 60+ sources total

### CoPaw Research
- MarkTechPost, Open Source For You, GitHub Issues: #52, #153, #578, #995, #388, #448, #479

### Competitor Research
- 35 projects analyzed across 7 tiers (see Section 3.1)
- OWASP Top 10 for Agentic Applications (Dec 2025)
- Gartner: 1,445% surge in multi-agent system inquiries
- LangChain State of Agent Engineering report

### Voice/AI Research
- PersonaPlex paper (ArXiv 2602.06053)
- Brave Search API documentation
- Fish Speech, CosyVoice2, IndexTTS-2 releases
- Hume AI emotion detection documentation

---

*End of PRD — Version 1.0*
