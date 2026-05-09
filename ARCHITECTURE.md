# Nobla Agent — Architecture

> Mission: a privacy-first, locally-first, mobile-first AI super agent that unifies 35+ AI agent projects while fixing their security vulnerabilities.

This document describes the implemented architecture as of Phases 1-4E + 5A + 5-Channels (WhatsApp/Slack/Signal/Teams) + 6 (NL Scheduler / Multi-Agent v2 / Webhooks / Workflows / Templates) + 5B.1 (Learning) + 5B.2 (Marketplace). See [CLAUDE.md](CLAUDE.md) for the developer-facing guide and [PRD.md](PRD.md) for product requirements.

---

## 1. System Overview

```
┌──────────────────────────┐                ┌──────────────────────────────────────┐
│  Flutter Client (Dart)   │                │  Python Gateway (FastAPI / asyncio)  │
│  ──────────────────────  │   WebSocket    │  ──────────────────────────────────  │
│  Riverpod state          │  + REST/HTTPS  │  Routers + lifespan + handlers       │
│  go_router navigation    │ ◄────TLS────►  │  Brain · Memory · Voice · Tools      │
│  just_audio / record     │                │  Channels · Skills · Learning        │
│  rive / lottie           │                │  Agents · Automation · Marketplace   │
│  flutter_secure_storage  │                │  Security · Events · Persona         │
└──────────────────────────┘                └────────────────┬─────────────────────┘
                                                              │
                                          ┌───────────────────┼────────────────────┐
                                          │                   │                    │
                                     ┌────▼─────┐       ┌─────▼─────┐       ┌──────▼─────┐
                                     │ Postgres │       │   Redis   │       │  ChromaDB  │
                                     │  JSONB   │       │ sessions  │       │  vectors   │
                                     │  GIN/[]  │       │ rate-lim  │       │ sent.-tx.  │
                                     └──────────┘       └───────────┘       └────────────┘
                                          │                                        │
                                     ┌────▼─────┐                            ┌─────▼──────┐
                                     │ NetworkX │                            │  Whisper   │
                                     │   KG     │                            │ Levantine  │
                                     └──────────┘                            └────────────┘
```

**Two codebases, one product:**

- **Backend** (`backend/nobla/`, Python 3.12+ / FastAPI) — async gateway, LLM router, 5-layer memory, voice pipeline, tool platform, multi-agent orchestrator, channel adapters, sandbox execution.
- **Frontend** (`app/lib/`, Flutter 3.x / Dart) — mobile-first app with Riverpod state, real-time WebSocket chat, voice UI with avatar, security dashboard with kill switch.

---

## 2. Communication Layer

| Channel | Protocol | Purpose |
|---------|----------|---------|
| Flutter ↔ Gateway (real-time) | WebSocket over TLS | Chat streaming, voice frames, tool mirror, live workflow execution, agent intelligence updates |
| Flutter ↔ Gateway (CRUD) | REST/HTTPS | Auth, settings, marketplace browse, workflow/webhook CRUD, scheduler, persona management |
| Backend ↔ External LLMs | HTTPS + provider SDKs | Gemini, Groq, DeepSeek, OpenAI, Anthropic, Ollama (local fallback) |
| Backend ↔ Channels | Each adapter's native transport | Telegram polling/webhook · Discord WebSocket gateway · WhatsApp/Slack/Teams webhook · Slack Socket Mode WebSocket · Signal JSON-RPC daemon |
| Backend ↔ MCP | stdio + SSE (JSON-RPC 2.0) | MCP client (consume external servers) and MCP server (expose tools to other agents) |

All inbound webhooks use pluggable signature verification (HMAC-SHA256 / SHA1 / custom registries) per [`backend/nobla/automation/webhooks/`](backend/nobla/automation/webhooks/).

---

## 3. Data Layer

| Store | Role | Why |
|-------|------|-----|
| **PostgreSQL** | Structured rows, audit trail, workflow definitions, scheduled tasks, marketplace registry, channel links | JSONB + GIN indexes + array types + concurrent writes (upgraded from SQLite for the 5-layer memory writes) |
| **Redis** | Session cache, channel rate-limit state (Slack `RateLimitQueue`), webhook DLQ, transient agent workspace state | In-memory, low-latency primitives |
| **ChromaDB** | Semantic memory vectors (sentence-transformers embeddings) | Vector similarity for episodic recall + semantic search |
| **NetworkX** | In-memory knowledge graph layer | Entity/relation traversal without external graph DB |
| **APScheduler** | Time-driven jobs (NL Scheduler) | In-process cron without ops overhead |

---

## 4. Backend Module Boundaries (`backend/nobla/`)

| Module | Responsibility | Key components |
|--------|---------------|----------------|
| `gateway/` | FastAPI app, WebSocket + REST routers, lifespan, per-feature handler modules | `main.py`, `handlers/`, `routes/` |
| `brain/` | LLM router with smart routing (easy→cheap, hard→strong) | Circuit breaker, streaming, token counter, compression, fallback chain (primary→secondary→tertiary→Ollama) |
| `memory/` | 5-layer memory engine | Episodic (PG), semantic (Chroma), procedural, knowledge graph (NetworkX), working — orchestrator + retrieval + consolidation + extraction |
| `voice/` | Voice pipeline | Faster-Whisper (+ Levantine custom model), Fish Speech / CosyVoice TTS, VAD, language detection, PersonaPlex |
| `tools/` | Tool platform | `BaseTool` ABC + registry + executor + approval + 5 sub-domains: `vision/` (screenshot/OCR/UI), `control/` (mouse/keyboard/file/app/clipboard), `code/` (run/install/generate/debug/git), `remote/` (SSH/SFTP), `search/` (AI search) |
| `events/` | Async event bus | Pub/sub, wildcard subscriptions, priority dispatch, backpressure |
| `channels/` | Channel abstraction + 6 adapters | `base.py` + `manager.py` + `linking.py` + `bridge.py`; `telegram/` `discord/` `whatsapp/` `slack/` `signal/` `teams/` |
| `automation/` | Time + event-driven automation | `parser.py` (NL time), `interpreter.py` (LLM), `scheduler.py` (APScheduler), `webhooks/` (in/out + DLQ), `workflows/` (DAG executor + 6 step types + templates + NL interpreter) |
| `skills/` | Skill runtime | Universal adapter, security scanner, tool bridge |
| `learning/` | Self-improving agent | FeedbackCollector, PatternDetector, SkillGenerator, ABTestManager (epsilon-greedy), ProactiveEngine, LearningService orchestrator |
| `marketplace/` | Universal Skills Marketplace | MarketplaceRegistry (publish + SemVer + tiered trust), SkillPackager (`.nobla` archive), SkillDiscovery, UsageTracker, MarketplaceService |
| `agents/` | Multi-Agent System v2 | `BaseAgent` ABC + registry + parallel orchestrator (asyncio.gather tiers) + A2A protocol + MCP client/server + TaskDecomposer + AgentToolBridge + workspace + cloning + researcher/coder agents |
| `security/` | Cross-cutting security | Auth (JWT/OAuth/API-Key), sandbox (Docker/gVisor), audit (OpenTelemetry), kill switch, permissions, encryption (AES-256), cost ledger |
| `persona/` | Persona engine | Persona definitions + voice/style mapping (PersonaPlex) |

---

## 5. Frontend Module Boundaries (`app/lib/`)

| Layer | Contents |
|-------|----------|
| `core/` | Theme, routing (`go_router`), DI (`flutter_riverpod`), network (`dio` + `web_socket_channel`), secure storage |
| `features/` | `auth`, `chat`, `dashboard`, `voice`, `persona`, `memory`, `automation` (workflows + webhooks + templates), `security` (kill switch + audit), `settings`, `tools` (mirror + activity + browser), `marketplace`, `agents` (intelligence) |
| `shared/` | Reusable widgets, utils, models |

Mirrors the backend module map — every backend feature has a corresponding Flutter feature folder.

---

## 6. Cross-Cutting Concerns

### 6.1 Security

- **4-tier permission model** — `SAFE` / `STANDARD` / `ELEVATED` / `ADMIN`. Every tool declares its tier; the executor consults `approval.py` before invocation.
- **Global kill switch** — wired into gateway lifespan, learning service, marketplace publish, multi-agent orchestrator, workflow engine, and all channel adapters. One toggle stops every autonomous action.
- **Sandbox** — Docker/gVisor containers for code/tool execution. Tools that touch the host file system or shell run only inside the sandbox.
- **Audit trail** — OpenTelemetry-backed structured logging of every tool invocation, channel message, agent delegation, workflow step, and marketplace install.
- **Cost ledger** — per-provider token + dollar accounting with budget caps and auto-shutoff.
- **Encryption at rest** — AES-256 for credentials, channel tokens, OAuth refresh tokens, and persona voice files.
- **Auth** — JWT for the Flutter client, OAuth2 client_credentials for Teams, API-Key for webhooks, signature verification (HMAC-SHA256/SHA1) for inbound webhooks.

### 6.2 Reliability & Degradation

- **Graceful degradation** paths: GPU unavailable → CPU mode; cloud LLMs unavailable → local Ollama; PersonaPlex unavailable → default TTS; channel disconnect → exponential backoff reconnect (Signal, Slack Socket Mode).
- **Circuit breaker** in the LLM router prevents repeated failures from cascading.
- **Webhook DLQ** with exponential retry + user notification + health monitoring endpoint.
- **Workflow engine** uses topological sort + `asyncio.gather` per dependency tier with cascade-failure semantics.

### 6.3 The Event Bus as Spine

The async event bus (`events/`) connects independent subsystems without tight coupling:

```
tools  ──emit──►  events  ──fanout──►  channels (notify)
                                  ──►  learning (collect feedback + detect patterns)
                                  ──►  workflows (trigger matchers)
                                  ──►  agents (delegation cues)
                                  ──►  marketplace (usage tracking)
```

This is what lets the learning system observe tool chains across channels, the marketplace track install/active-user/success-rate stats, and workflows trigger on arbitrary signals.

### 6.4 Design Constraints

- **750-line hard limit per source file** (`.py`, `.dart`, any source). No exceptions — split into smaller modules when approached.
- **Privacy by default** — all data stays on the user's machine unless explicitly opted out.
- **Cost-conscious defaults** — Gemini free + Groq free + Ollama local for the cheap tier; DeepSeek balanced; GPT-4 / Claude only for the strong tier; budget caps with auto-shutoff.
- **Mobile-first** — APIs designed with mobile UX in mind; Flutter is the primary interface, not an afterthought.
- **No backwards-compat hacks** — features are added cleanly; abandoned code is deleted, not commented out.

---

## 7. Deployment View

```yaml
# docker-compose.yml (target shape)
services:
  backend:    # FastAPI gateway
  postgres:   # 5-layer memory + audit + workflows + marketplace
  redis:      # sessions + rate-limit + DLQ
  chromadb:   # vector embeddings
  ollama:     # optional local LLM fallback
```

The Flutter client is shipped as a mobile app (Android/iOS) with desktop builds available via the standard `flutter build` toolchain.

---

## 8. Forward Path

The boundaries above are stable for the remaining roadmap. Without changing module shapes:

- **Phase 5-Channels** — 11 remaining adapters (Messenger, LINE, Viber, etc.) plug into `channels/` using the existing `base.py` + manager + linking + bridge.
- **Phase 7** — media, finance, health, social, smart-home tool packs all extend `tools/` with new sub-domains following the same `BaseTool` ABC + registry + executor + approval contract.
- **MCP ecosystem** — both directions (consume external MCP servers + expose Nobla tools as MCP) are already wired via `agents/`.

---

## 9. References

- [CLAUDE.md](CLAUDE.md) — developer guide, phase status, command cheatsheet
- [PRD.md](PRD.md) — full product requirements, competitive analysis
- [Plan.md](Plan.md) — 7-phase development roadmap
- [README.md](README.md) — project overview + quickstart
- [project_file_architecture.md](project_file_architecture.md) — auto-generated file tree

## File Architecture (auto-generated)

<!-- MEMORY:ARCH:START -->

```mermaid
%% Auto-generated. Do not edit between the MEMORY:ARCH markers.
flowchart TD
  n0["Nobla Agent/"]
  n1[".claude/"]
  n0 --> n1
  n2["worktrees/"]
  n1 --> n2
  n3[".github/"]
  n0 --> n3
  n4["workflows/"]
  n3 --> n4
  n5["ci.yml"]
  n4 --> n5
  n6["app/"]
  n0 --> n6
  n7["android/"]
  n6 --> n7
  n8["app/"]
  n7 --> n8
  n9["src/"]
  n8 --> n9
  n10["build.gradle.kts"]
  n8 --> n10
  n11["gradle/"]
  n7 --> n11
  n12["wrapper/"]
  n11 --> n12
  n13[".gitignore"]
  n7 --> n13
  n14["build.gradle.kts"]
  n7 --> n14
  n15["gradle.properties"]
  n7 --> n15
  n16["gradlew"]
  n7 --> n16
  n17["gradlew.bat"]
  n7 --> n17
  n18["local.properties"]
  n7 --> n18
  n19["nobla_agent_android.iml"]
  n7 --> n19
  n20["settings.gradle.kts"]
  n7 --> n20
  n21["ios/"]
  n6 --> n21
  n22["Flutter/"]
  n21 --> n22
  n23["ephemeral/"]
  n22 --> n23
  n24["AppFrameworkInfo.plist"]
  n22 --> n24
  n25["Debug.xcconfig"]
  n22 --> n25
  n26["flutter_export_environment.sh"]
  n22 --> n26
  n27["Generated.xcconfig"]
  n22 --> n27
  n28["Release.xcconfig"]
  n22 --> n28
  n29["Runner/"]
  n21 --> n29
  n30["Assets.xcassets/"]
  n29 --> n30
  n31["Base.lproj/"]
  n29 --> n31
  n32["AppDelegate.swift"]
  n29 --> n32
  n33["GeneratedPluginRegistrant.h"]
  n29 --> n33
  n34["GeneratedPluginRegistrant.m"]
  n29 --> n34
  n35["Info.plist"]
  n29 --> n35
  n36["Runner-Bridging-Header.h"]
  n29 --> n36
  n37["Runner.xcodeproj/"]
  n21 --> n37
  n38["project.xcworkspace/"]
  n37 --> n38
  n39["xcshareddata/"]
  n37 --> n39
  n40["project.pbxproj"]
  n37 --> n40
  n41["Runner.xcworkspace/"]
  n21 --> n41
  n42["xcshareddata/"]
  n41 --> n42
  n43["contents.xcworkspacedata"]
  n41 --> n43
  n44["RunnerTests/"]
  n21 --> n44
  n45["RunnerTests.swift"]
  n44 --> n45
  n46[".gitignore"]
  n21 --> n46
  n47["lib/"]
  n6 --> n47
  n48["core/"]
  n47 --> n48
  n49["network/"]
  n48 --> n49
  n50["providers/"]
  n48 --> n50
  n51["routing/"]
  n48 --> n51
  n52["theme/"]
  n48 --> n52
  n53["features/"]
  n47 --> n53
  n54["auth/"]
  n53 --> n54
  n55["automation/"]
  n53 --> n55
  n56["chat/"]
  n53 --> n56
  n57["conversations/"]
  n53 --> n57
  n58["dashboard/"]
  n53 --> n58
  n59["learning/"]
  n53 --> n59
  n60["marketplace/"]
  n53 --> n60
  n61["memory/"]
  n53 --> n61
  n62["persona/"]
  n53 --> n62
  n63["security/"]
  n53 --> n63
  n64["settings/"]
  n53 --> n64
  n65["tools/"]
  n53 --> n65
  n66["shared/"]
  n47 --> n66
  n67["models/"]
  n66 --> n67
  n68["providers/"]
  n66 --> n68
  n69["widgets/"]
  n66 --> n69
  n70["main.dart"]
  n47 --> n70
  n71["linux/"]
  n6 --> n71
  n72["flutter/"]
  n71 --> n72
  n73["ephemeral/"]
  n72 --> n73
  n74["CMakeLists.txt"]
  n72 --> n74
  n75["generated_plugin_registrant.cc"]
  n72 --> n75
  n76["generated_plugin_registrant.h"]
  n72 --> n76
  n77["generated_plugins.cmake"]
  n72 --> n77
  n78["runner/"]
  n71 --> n78
  n79["CMakeLists.txt"]
  n78 --> n79
  n80["main.cc"]
  n78 --> n80
  n81["my_application.cc"]
  n78 --> n81
  n82["my_application.h"]
  n78 --> n82
  n83[".gitignore"]
  n71 --> n83
  n84["CMakeLists.txt"]
  n71 --> n84
  n85["macos/"]
  n6 --> n85
  n86["Flutter/"]
  n85 --> n86
  n87["ephemeral/"]
  n86 --> n87
  n88["Flutter-Debug.xcconfig"]
  n86 --> n88
  n89["Flutter-Release.xcconfig"]
  n86 --> n89
  n90["GeneratedPluginRegistrant.swift"]
  n86 --> n90
  n91["Runner/"]
  n85 --> n91
  n92["Assets.xcassets/"]
  n91 --> n92
  n93["Base.lproj/"]
  n91 --> n93
  n94["Configs/"]
  n91 --> n94
  n95["AppDelegate.swift"]
  n91 --> n95
  n96["DebugProfile.entitlements"]
  n91 --> n96
  n97["Info.plist"]
  n91 --> n97
  n98["MainFlutterWindow.swift"]
  n91 --> n98
  n99["Release.entitlements"]
  n91 --> n99
  n100["Runner.xcodeproj/"]
  n85 --> n100
  n101["project.xcworkspace/"]
  n100 --> n101
  n102["xcshareddata/"]
  n100 --> n102
  n103["project.pbxproj"]
  n100 --> n103
  n104["Runner.xcworkspace/"]
  n85 --> n104
  n105["xcshareddata/"]
  n104 --> n105
  n106["contents.xcworkspacedata"]
  n104 --> n106
  n107["RunnerTests/"]
  n85 --> n107
  n108["RunnerTests.swift"]
  n107 --> n108
  n109[".gitignore"]
  n85 --> n109
  n110["test/"]
  n6 --> n110
  n111["core/"]
  n110 --> n111
  n112["network/"]
  n111 --> n112
  n113["providers/"]
  n111 --> n113
  n114["features/"]
  n110 --> n114
  n115["auth/"]
  n114 --> n115
  n116["automation/"]
  n114 --> n116
  n117["chat/"]
  n114 --> n117
  n118["dashboard/"]
  n114 --> n118
  n119["learning/"]
  n114 --> n119
  n120["marketplace/"]
  n114 --> n120
  n121["persona/"]
  n114 --> n121
  n122["tools/"]
  n114 --> n122
  n123["shared/"]
  n110 --> n123
  n124["models/"]
  n123 --> n124
  n125["providers/"]
  n123 --> n125
  n126["web/"]
  n6 --> n126
  n127["icons/"]
  n126 --> n127
  n128["Icon-192.png"]
  n127 --> n128
  n129["Icon-512.png"]
  n127 --> n129
  n130["Icon-maskable-192.png"]
  n127 --> n130
  n131["Icon-maskable-512.png"]
  n127 --> n131
  n132["favicon.png"]
  n126 --> n132
  n133["index.html"]
  n126 --> n133
  n134["manifest.json"]
  n126 --> n134
  n135["windows/"]
  n6 --> n135
  n136["flutter/"]
  n135 --> n136
  n137["ephemeral/"]
  n136 --> n137
  n138["CMakeLists.txt"]
  n136 --> n138
  n139["generated_plugin_registrant.cc"]
  n136 --> n139
  n140["generated_plugin_registrant.h"]
  n136 --> n140
  n141["generated_plugins.cmake"]
  n136 --> n141
  n142["runner/"]
  n135 --> n142
  n143["resources/"]
  n142 --> n143
  n144["CMakeLists.txt"]
  n142 --> n144
  n145["flutter_window.cpp"]
  n142 --> n145
  n146["flutter_window.h"]
  n142 --> n146
  n147["main.cpp"]
  n142 --> n147
  n148["resource.h"]
  n142 --> n148
  n149["runner.exe.manifest"]
  n142 --> n149
  n150["Runner.rc"]
  n142 --> n150
  n151["utils.cpp"]
  n142 --> n151
  n152["utils.h"]
  n142 --> n152
  n153["win32_window.cpp"]
  n142 --> n153
  n154["win32_window.h"]
  n142 --> n154
  n155[".gitignore"]
  n135 --> n155
  n156["CMakeLists.txt"]
  n135 --> n156
  n157[".gitignore"]
  n6 --> n157
  n158["analysis_options.yaml"]
  n6 --> n158
  n159["nobla_agent.iml"]
  n6 --> n159
  n160["pubspec.lock"]
  n6 --> n160
  n161["pubspec.yaml"]
  n6 --> n161
  n162["README.md"]
  n6 --> n162
  n163["backend/"]
  n0 --> n163
  n164["nobla/"]
  n163 --> n164
  n165["agents/"]
  n164 --> n165
  n166["builtins/"]
  n165 --> n166
  n167["__init__.py"]
  n165 --> n167
  n168["base.py"]
  n165 --> n168
  n169["bridge.py"]
  n165 --> n169
  n170["cloning.py"]
  n165 --> n170
  n171["communication.py"]
  n165 --> n171
  n172["decomposer.py"]
  n165 --> n172
  n173["executor.py"]
  n165 --> n173
  n174["mcp_client.py"]
  n165 --> n174
  n175["mcp_server.py"]
  n165 --> n175
  n176["models.py"]
  n165 --> n176
  n177["orchestrator.py"]
  n165 --> n177
  n178["registry.py"]
  n165 --> n178
  n179["workspace.py"]
  n165 --> n179
  n180["automation/"]
  n164 --> n180
  n181["webhooks/"]
  n180 --> n181
  n182["workflows/"]
  n180 --> n182
  n183["__init__.py"]
  n180 --> n183
  n184["confirmation.py"]
  n180 --> n184
  n185["interpreter.py"]
  n180 --> n185
  n186["models.py"]
  n180 --> n186
  n187["parser.py"]
  n180 --> n187
  n188["scheduler.py"]
  n180 --> n188
  n189["service.py"]
  n180 --> n189
  n190["brain/"]
  n164 --> n190
  n191["auth/"]
  n190 --> n191
  n192["providers/"]
  n190 --> n192
  n193["__init__.py"]
  n190 --> n193
  n194["base_provider.py"]
  n190 --> n194
  n195["circuit_breaker.py"]
  n190 --> n195
  n196["compression.py"]
  n190 --> n196
  n197["router.py"]
  n190 --> n197
  n198["streaming.py"]
  n190 --> n198
  n199["token_counter.py"]
  n190 --> n199
  n200["channels/"]
  n164 --> n200
  n201["discord/"]
  n200 --> n201
  n202["messenger/"]
  n200 --> n202
  n203["signal/"]
  n200 --> n203
  n204["slack/"]
  n200 --> n204
  n205["teams/"]
  n200 --> n205
  n206["telegram/"]
  n200 --> n206
  n207["whatsapp/"]
  n200 --> n207
  n208["__init__.py"]
  n200 --> n208
  n209["base.py"]
  n200 --> n209
  n210["bridge.py"]
  n200 --> n210
  n211["linking.py"]
  n200 --> n211
  n212["manager.py"]
  n200 --> n212
  n213["config/"]
  n164 --> n213
  n214["__init__.py"]
  n213 --> n214
  n215["loader.py"]
  n213 --> n215
  n216["settings.py"]
  n213 --> n216
  n217["db/"]
  n164 --> n217
  n218["migrations/"]
  n217 --> n218
  n219["models/"]
  n217 --> n219
  n220["repositories/"]
  n217 --> n220
  n221["__init__.py"]
  n217 --> n221
  n222["engine.py"]
  n217 --> n222
  n223["events/"]
  n164 --> n223
  n224["__init__.py"]
  n223 --> n224
  n225["bus.py"]
  n223 --> n225
  n226["models.py"]
  n223 --> n226
  n227["gateway/"]
  n164 --> n227
  n228["__init__.py"]
  n227 --> n228
  n229["app.py"]
  n227 --> n229
  n230["channel_handlers.py"]
  n227 --> n230
  n231["code_handlers.py"]
  n227 --> n231
  n232["learning_handlers.py"]
  n227 --> n232
  n233["lifespan.py"]
  n227 --> n233
  n234["marketplace_handlers.py"]
  n227 --> n234
  n235["memory_handlers.py"]
  n227 --> n235
  n236["mirror_handlers.py"]
  n227 --> n236
  n237["persona_routes.py"]
  n227 --> n237
  n238["protocol.py"]
  n227 --> n238
  n239["provider_handlers.py"]
  n227 --> n239
  n240["routes.py"]
  n227 --> n240
  n241["search_handlers.py"]
  n227 --> n241
  n242["template_handlers.py"]
  n227 --> n242
  n243["tool_handlers.py"]
  n227 --> n243
  n244["voice_handlers.py"]
  n227 --> n244
  n245["webhook_handlers.py"]
  n227 --> n245
  n246["websocket.py"]
  n227 --> n246
  n247["workflow_handlers.py"]
  n227 --> n247
  n248["learning/"]
  n164 --> n248
  n249["__init__.py"]
  n248 --> n249
  n250["ab_testing.py"]
  n248 --> n250
  n251["feedback.py"]
  n248 --> n251
  n252["generator.py"]
  n248 --> n252
  n253["models.py"]
  n248 --> n253
  n254["patterns.py"]
  n248 --> n254
  n255["proactive.py"]
  n248 --> n255
  n256["service.py"]
  n248 --> n256
  n257["marketplace/"]
  n164 --> n257
  n258["__init__.py"]
  n257 --> n258
  n259["discovery.py"]
  n257 --> n259
  n260["models.py"]
  n257 --> n260
  n261["packager.py"]
  n257 --> n261
  n262["registry.py"]
  n257 --> n262
  n263["service.py"]
  n257 --> n263
  n264["stats.py"]
  n257 --> n264
  n265["memory/"]
  n164 --> n265
  n266["__init__.py"]
  n265 --> n266
  n267["consolidation.py"]
  n265 --> n267
  n268["episodic.py"]
  n265 --> n268
  n269["extraction.py"]
  n265 --> n269
  n270["graph_builder.py"]
  n265 --> n270
  n271["graph_persistence.py"]
  n265 --> n271
  n272["graph_queries.py"]
  n265 --> n272
  n273["maintenance.py"]
  n265 --> n273
  n274["orchestrator.py"]
  n265 --> n274
  n275["procedural.py"]
  n265 --> n275
  n276["retrieval_sources.py"]
  n265 --> n276
  n277["retrieval.py"]
  n265 --> n277
  n278["semantic.py"]
  n265 --> n278
  n279["working.py"]
  n265 --> n279
  n280["persona/"]
  n164 --> n280
  n281["__init__.py"]
  n280 --> n281
  n282["manager.py"]
  n280 --> n282
  n283["models.py"]
  n280 --> n283
  n284["presets.py"]
  n280 --> n284
  n285["prompt.py"]
  n280 --> n285
  n286["repository.py"]
  n280 --> n286
  n287["service.py"]
  n280 --> n287
  n288["security/"]
  n164 --> n288
  n289["__init__.py"]
  n288 --> n289
  n290["audit.py"]
  n288 --> n290
  n291["auth.py"]
  n288 --> n291
  n292["costs.py"]
  n288 --> n292
  n293["killswitch.py"]
  n288 --> n293
  n294["permissions.py"]
  n288 --> n294
  n295["sandbox.py"]
  n288 --> n295
  n296["skills/"]
  n164 --> n296
  n297["adapters/"]
  n296 --> n297
  n298["store/"]
  n296 --> n298
  n299["__init__.py"]
  n296 --> n299
  n300["adapter.py"]
  n296 --> n300
  n301["bridge.py"]
  n296 --> n301
  n302["models.py"]
  n296 --> n302
  n303["runtime.py"]
  n296 --> n303
  n304["security.py"]
  n296 --> n304
  n305["tools/"]
  n164 --> n305
  n306["code/"]
  n305 --> n306
  n307["control/"]
  n305 --> n307
  n308["remote/"]
  n305 --> n308
  n309["search/"]
  n305 --> n309
  n310["vision/"]
  n305 --> n310
  n311["__init__.py"]
  n305 --> n311
  n312["approval.py"]
  n305 --> n312
  n313["base.py"]
  n305 --> n313
  n314["executor.py"]
  n305 --> n314
  n315["models.py"]
  n305 --> n315
  n316["registry.py"]
  n305 --> n316
  n317["voice/"]
  n164 --> n317
  n318["emotion/"]
  n317 --> n318
  n319["stt/"]
  n317 --> n319
  n320["tts/"]
  n317 --> n320
  n321["__init__.py"]
  n317 --> n321
  n322["models.py"]
  n317 --> n322
  n323["pipeline.py"]
  n317 --> n323
  n324["vad.py"]
  n317 --> n324
  n325["__init__.py"]
  n164 --> n325
  n326["main.py"]
  n164 --> n326
  n327["nobla_agent.egg-info/"]
  n163 --> n327
  n328["dependency_links.txt"]
  n327 --> n328
  n329["PKG-INFO"]
  n327 --> n329
  n330["requires.txt"]
  n327 --> n330
  n331["SOURCES.txt"]
  n327 --> n331
  n332["top_level.txt"]
  n327 --> n332
  n333["test/"]
  n163 --> n333
  n334["chroma.sqlite3"]
  n333 --> n334
  n335["test_chromadb/"]
  n163 --> n335
  n336["bf372e00-db18-46d7-8b87-00e6237453d2/"]
  n335 --> n336
  n337["data_level0.bin"]
  n336 --> n337
  n338["header.bin"]
  n336 --> n338
  n339["length.bin"]
  n336 --> n339
  n340["link_lists.bin"]
  n336 --> n340
  n341["chroma.sqlite3"]
  n335 --> n341
  n342["tests/"]
  n163 --> n342
  n343["gateway/"]
  n342 --> n343
  n344["__init__.py"]
  n343 --> n344
  n345["test_mirror_handlers.py"]
  n343 --> n345
  n346["integration/"]
  n342 --> n346
  n347["__init__.py"]
  n346 --> n347
  n348["conftest.py"]
  n346 --> n348
  n349["test_auth_flow.py"]
  n346 --> n349
  n350["test_chat_flow.py"]
  n346 --> n350
  n351["test_chat_send_memory.py"]
  n346 --> n351
  n352["test_code_flow.py"]
  n346 --> n352
  n353["test_concurrent.py"]
  n346 --> n353
  n354["test_persona_flow.py"]
  n346 --> n354
  n355["test_phase5_foundation.py"]
  n346 --> n355
  n356["test_security_flow.py"]
  n346 --> n356
  n357["test_tool_flow.py"]
  n346 --> n357
  n358["test_vision_flow.py"]
  n346 --> n358
  n359["tools/"]
  n342 --> n359
  n360["control/"]
  n359 --> n360
  n361["remote/"]
  n359 --> n361
  n362["__init__.py"]
  n359 --> n362
  n363["test_executor_mirror.py"]
  n359 --> n363
  n364["voice/"]
  n342 --> n364
  n365["__init__.py"]
  n364 --> n365
  n366["conftest.py"]
  n364 --> n366
  n367["test_cosyvoice.py"]
  n364 --> n367
  n368["test_detector.py"]
  n364 --> n368
  n369["test_fish_speech.py"]
  n364 --> n369
  n370["test_integration.py"]
  n364 --> n370
  n371["test_levantine.py"]
  n364 --> n371
  n372["test_models.py"]
  n364 --> n372
  n373["test_pipeline.py"]
  n364 --> n373
  n374["test_stt_base.py"]
  n364 --> n374
  n375["test_tts_base.py"]
  n364 --> n375
  n376["test_vad.py"]
  n364 --> n376
  n377["test_voice_handlers.py"]
  n364 --> n377
  n378["test_whisper.py"]
  n364 --> n378
  n379["test_academic.py"]
  n342 --> n379
  n380["test_agents_advanced.py"]
  n342 --> n380
  n381["test_agents_phase6v2.py"]
  n342 --> n381
  n382["test_agents.py"]
  n342 --> n382
  n383["test_audit.py"]
  n342 --> n383
  n384["test_auth_api_key.py"]
  n342 --> n384
  n385["test_auth_local.py"]
  n342 --> n385
  n386["test_auth_oauth.py"]
  n342 --> n386
  n387["test_auth.py"]
  n342 --> n387
  n388["test_brave.py"]
  n342 --> n388
  n389["test_channels.py"]
  n342 --> n389
  n390["test_chat_flow.py"]
  n342 --> n390
  n391["test_circuit_breaker.py"]
  n342 --> n391
  n392["test_code_codegen.py"]
  n342 --> n392
  n393["test_code_debug.py"]
  n342 --> n393
  n394["test_code_git.py"]
  n342 --> n394
  n395["test_code_packages.py"]
  n342 --> n395
  n396["test_code_runner.py"]
  n342 --> n396
  n397["test_code_settings.py"]
  n342 --> n397
  n398["test_compression.py"]
  n342 --> n398
  n399["test_config.py"]
  n342 --> n399
  n400["… (88 more)"]
  n342 --> n400
  n401["venv/"]
  n163 --> n401
  n402["Include/"]
  n401 --> n402
  n403["site/"]
  n402 --> n403
  n404["Lib/"]
  n401 --> n404
  n405["site-packages/"]
  n404 --> n405
  n406["Scripts/"]
  n401 --> n406
  n407["activate"]
  n406 --> n407
  n408["activate.bat"]
  n406 --> n408
  n409["Activate.ps1"]
  n406 --> n409
  n410["alembic.exe"]
  n406 --> n410
  n411["chroma.exe"]
  n406 --> n411
  n412["coverage-3.12.exe"]
  n406 --> n412
  n413["coverage.exe"]
  n406 --> n413
  n414["coverage3.exe"]
  n406 --> n414
  n415["deactivate.bat"]
  n406 --> n415
  n416["distro.exe"]
  n406 --> n416
  n417["dmypy.exe"]
  n406 --> n417
  n418["dotenv.exe"]
  n406 --> n418
  n419["f2py.exe"]
  n406 --> n419
  n420["fastapi.exe"]
  n406 --> n420
  n421["hf.exe"]
  n406 --> n421
  n422["httpx.exe"]
  n406 --> n422
  n423["isympy.exe"]
  n406 --> n423
  n424["jsonschema.exe"]
  n406 --> n424
  n425["mako-render.exe"]
  n406 --> n425
  n426["markdown-it.exe"]
  n406 --> n426
  n427["mypy.exe"]
  n406 --> n427
  n428["mypyc.exe"]
  n406 --> n428
  n429["normalizer.exe"]
  n406 --> n429
  n430["numpy-config.exe"]
  n406 --> n430
  n431["onnxruntime_test.exe"]
  n406 --> n431
  n432["… (29 more)"]
  n406 --> n432
  n433["share/"]
  n401 --> n433
  n434["man/"]
  n433 --> n434
  n435["pyvenv.cfg"]
  n401 --> n435
  n436[".env.example"]
  n163 --> n436
  n437["alembic.ini"]
  n163 --> n437
  n438["config.yaml"]
  n163 --> n438
  n439["Dockerfile"]
  n163 --> n439
  n440["pyproject.toml"]
  n163 --> n440
  n441["README.md"]
  n163 --> n441
  n442["docker/"]
  n0 --> n442
  n443["personaplex/"]
  n442 --> n443
  n444["docker-compose.yml"]
  n443 --> n444
  n445["docs/"]
  n0 --> n445
  n446["scm-memory/"]
  n445 --> n446
  n447["legacy_claude.md"]
  n446 --> n447
  n448["legacy_memory.md"]
  n446 --> n448
  n449["session-reports/"]
  n445 --> n449
  n450["SESSION-1-REPORT.md"]
  n449 --> n450
  n451["SESSION-2-REPORT.md"]
  n449 --> n451
  n452["SESSION-3-REPORT.md"]
  n449 --> n452
  n453["superpowers/"]
  n445 --> n453
  n454["plans/"]
  n453 --> n454
  n455["2026-03-17-phase1a-backend-foundation.md"]
  n454 --> n455
  n456["2026-03-17-phase1b-security-auth.md"]
  n454 --> n456
  n457["2026-03-17-phase1c-flutter-app.md"]
  n454 --> n457
  n458["2026-03-17-phase1d-integration-deployment.md"]
  n454 --> n458
  n459["2026-03-19-phase2a-memory-implementation.md"]
  n454 --> n459
  n460["2026-03-20-phase2b1-streaming-auth-circuit-breaker.md"]
  n454 --> n460
  n461["2026-03-20-phase2b2-search-polish.md"]
  n454 --> n461
  n462["2026-03-21-phase3a-voice-pipeline.md"]
  n454 --> n462
  n463["2026-03-21-phase3b1-persona-engine.md"]
  n454 --> n463
  n464["2026-03-21-phase3b2-personaplex-integration.md"]
  n454 --> n464
  n465["2026-03-23-phase3b3a-persona-management-ui.md"]
  n454 --> n465
  n466["2026-03-23-phase4-pre-tool-platform.md"]
  n454 --> n466
  n467["2026-03-24-phase4a-screen-vision.md"]
  n454 --> n467
  n468["2026-03-24-phase4c-code-execution.md"]
  n454 --> n468
  n469["2026-03-25-phase4b-computer-control.md"]
  n454 --> n469
  n470["2026-03-25-phase4d-remote-control.md"]
  n454 --> n470
  n471["2026-03-25-phase4e-flutter-tool-ui.md"]
  n454 --> n471
  n472["2026-03-27-multi-agent-system.md"]
  n454 --> n472
  n473["2026-03-28-self-improving-agent.md"]
  n454 --> n473
  n474["2026-03-28-webhooks-workflows.md"]
  n454 --> n474
  n475["2026-03-29-skills-marketplace.md"]
  n454 --> n475
  n476["2026-03-29-slack-signal-adapters.md"]
  n454 --> n476
  n477["2026-03-29-teams-adapter.md"]
  n454 --> n477
  n478["prompts/"]
  n453 --> n478
  n479["research/"]
  n478 --> n479
  n480["continue-after-multiagent-design.md"]
  n478 --> n480
  n481["continue-after-multiagent-implementation.md"]
  n478 --> n481
  n482["continue-after-phase4e-implementation.md"]
  n478 --> n482
  n483["continue-after-phase5-slack-signal.md"]
  n478 --> n483
  n484["continue-after-phase5-teams.md"]
  n478 --> n484
  n485["continue-after-phase5-whatsapp.md"]
  n478 --> n485
  n486["continue-after-phase5a-6-scheduler.md"]
  n478 --> n486
  n487["continue-after-phase5b1-learning.md"]
  n478 --> n487
  n488["continue-after-phase5b2-marketplace.md"]
  n478 --> n488
  n489["continue-after-phase6-templates.md"]
  n478 --> n489
  n490["continue-after-phase6-webhooks-workflows.md"]
  n478 --> n490
  n491["continue-after-phase6v2-implementation.md"]
  n478 --> n491
  n492["phase4a-continuation-prompt.md"]
  n478 --> n492
  n493["phase4b-continuation-prompt.md"]
  n478 --> n493
  n494["phase4c-continuation-prompt.md"]
  n478 --> n494
  n495["phase4c-implementation-prompt.md"]
  n478 --> n495
  n496["phase4d-continuation-prompt.md"]
  n478 --> n496
  n497["phase4d-implementation-prompt.md"]
  n478 --> n497
  n498["phase4e-continuation-prompt.md"]
  n478 --> n498
  n499["phase5-channels-continuation-prompt.md"]
  n478 --> n499
  n500["specs/"]
  n453 --> n500
  n501["2026-03-17-phase1a-backend-foundation-design.md"]
  n500 --> n501
  n502["2026-03-17-phase1b-security-auth-design.md"]
  n500 --> n502
  n503["2026-03-17-phase1c-flutter-app-design.md"]
  n500 --> n503
  n504["2026-03-19-phase2a-memory-conversation-design.md"]
  n500 --> n504
  n505["2026-03-19-phase2b-router-search-design.md"]
  n500 --> n505
  n506["2026-03-21-phase3-voice-persona-design.md"]
  n500 --> n506
  n507["2026-03-21-phase3b-persona-engine-design.md"]
  n500 --> n507
  n508["2026-03-21-phase3b2-personaplex-integration-design.md"]
  n500 --> n508
  n509["2026-03-23-phase3b3a-persona-management-ui-design.md"]
  n500 --> n509
  n510["2026-03-23-phase4-computer-control-vision-design.md"]
  n500 --> n510
  n511["2026-03-24-phase4a-screen-vision-design.md"]
  n500 --> n511
  n512["2026-03-24-phase4c-code-execution-design.md"]
  n500 --> n512
  n513["2026-03-25-phase4b-computer-control-design.md"]
  n500 --> n513
  n514["2026-03-25-phase4d-remote-control-design.md"]
  n500 --> n514
  n515["2026-03-25-phase4e-flutter-tool-ui-design.md"]
  n500 --> n515
  n516["2026-03-26-phase5-redesign-design.md"]
  n500 --> n516
  n517["2026-03-27-multi-agent-system-design.md"]
  n500 --> n517
  n518["2026-03-28-self-improving-agent-design.md"]
  n500 --> n518
  n519["2026-03-28-webhooks-workflows-design.md"]
  n500 --> n519
  n520["2026-03-29-skills-marketplace-design.md"]
  n500 --> n520
  n521["2026-03-29-slack-signal-adapters-design.md"]
  n500 --> n521
  n522["2026-03-29-teams-adapter-design.md"]
  n500 --> n522
  n523["NEXT-SESSION-PROMPT.md"]
  n445 --> n523
  n524[".env.example"]
  n0 --> n524
  n525[".gitignore"]
  n0 --> n525
  n526["Architecture-Prompt-Template.md"]
  n0 --> n526
  n527["ARCHITECTURE.md"]
  n0 --> n527
  n528["CHANGELOG.md"]
  n0 --> n528
  n529["CLAUDE.md"]
  n0 --> n529
  n530["docker-compose.yml"]
  n0 --> n530
  n531["ggml-levantine-large-v3.bin"]
  n0 --> n531
  n532["Nobla-Agent-Architecture.html"]
  n0 --> n532
  n533["Nobla-Agent-Architecture.pdf"]
  n0 --> n533
  n534["Plan.md"]
  n0 --> n534
  n535["PRD.md"]
  n0 --> n535
  n536["project_file_architecture.md"]
  n0 --> n536
  n537["README.md"]
  n0 --> n537
```

<!-- MEMORY:ARCH:END -->
