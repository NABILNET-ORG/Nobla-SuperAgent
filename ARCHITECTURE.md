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
  n231["channel_webhook_dispatcher.py"]
  n227 --> n231
  n232["code_handlers.py"]
  n227 --> n232
  n233["learning_handlers.py"]
  n227 --> n233
  n234["lifespan.py"]
  n227 --> n234
  n235["marketplace_handlers.py"]
  n227 --> n235
  n236["memory_handlers.py"]
  n227 --> n236
  n237["mirror_handlers.py"]
  n227 --> n237
  n238["persona_routes.py"]
  n227 --> n238
  n239["protocol.py"]
  n227 --> n239
  n240["provider_handlers.py"]
  n227 --> n240
  n241["routes.py"]
  n227 --> n241
  n242["search_handlers.py"]
  n227 --> n242
  n243["template_handlers.py"]
  n227 --> n243
  n244["tool_handlers.py"]
  n227 --> n244
  n245["voice_handlers.py"]
  n227 --> n245
  n246["webhook_handlers.py"]
  n227 --> n246
  n247["websocket.py"]
  n227 --> n247
  n248["workflow_handlers.py"]
  n227 --> n248
  n249["learning/"]
  n164 --> n249
  n250["__init__.py"]
  n249 --> n250
  n251["ab_testing.py"]
  n249 --> n251
  n252["feedback.py"]
  n249 --> n252
  n253["generator.py"]
  n249 --> n253
  n254["models.py"]
  n249 --> n254
  n255["patterns.py"]
  n249 --> n255
  n256["proactive.py"]
  n249 --> n256
  n257["service.py"]
  n249 --> n257
  n258["marketplace/"]
  n164 --> n258
  n259["__init__.py"]
  n258 --> n259
  n260["discovery.py"]
  n258 --> n260
  n261["models.py"]
  n258 --> n261
  n262["packager.py"]
  n258 --> n262
  n263["registry.py"]
  n258 --> n263
  n264["service.py"]
  n258 --> n264
  n265["stats.py"]
  n258 --> n265
  n266["memory/"]
  n164 --> n266
  n267["__init__.py"]
  n266 --> n267
  n268["consolidation.py"]
  n266 --> n268
  n269["episodic.py"]
  n266 --> n269
  n270["extraction.py"]
  n266 --> n270
  n271["graph_builder.py"]
  n266 --> n271
  n272["graph_persistence.py"]
  n266 --> n272
  n273["graph_queries.py"]
  n266 --> n273
  n274["maintenance.py"]
  n266 --> n274
  n275["orchestrator.py"]
  n266 --> n275
  n276["procedural.py"]
  n266 --> n276
  n277["retrieval_sources.py"]
  n266 --> n277
  n278["retrieval.py"]
  n266 --> n278
  n279["semantic.py"]
  n266 --> n279
  n280["working.py"]
  n266 --> n280
  n281["persona/"]
  n164 --> n281
  n282["__init__.py"]
  n281 --> n282
  n283["manager.py"]
  n281 --> n283
  n284["models.py"]
  n281 --> n284
  n285["presets.py"]
  n281 --> n285
  n286["prompt.py"]
  n281 --> n286
  n287["repository.py"]
  n281 --> n287
  n288["service.py"]
  n281 --> n288
  n289["security/"]
  n164 --> n289
  n290["__init__.py"]
  n289 --> n290
  n291["audit.py"]
  n289 --> n291
  n292["auth.py"]
  n289 --> n292
  n293["costs.py"]
  n289 --> n293
  n294["killswitch.py"]
  n289 --> n294
  n295["permissions.py"]
  n289 --> n295
  n296["sandbox.py"]
  n289 --> n296
  n297["skills/"]
  n164 --> n297
  n298["adapters/"]
  n297 --> n298
  n299["store/"]
  n297 --> n299
  n300["__init__.py"]
  n297 --> n300
  n301["adapter.py"]
  n297 --> n301
  n302["bridge.py"]
  n297 --> n302
  n303["models.py"]
  n297 --> n303
  n304["runtime.py"]
  n297 --> n304
  n305["security.py"]
  n297 --> n305
  n306["tools/"]
  n164 --> n306
  n307["code/"]
  n306 --> n307
  n308["control/"]
  n306 --> n308
  n309["remote/"]
  n306 --> n309
  n310["search/"]
  n306 --> n310
  n311["vision/"]
  n306 --> n311
  n312["__init__.py"]
  n306 --> n312
  n313["approval.py"]
  n306 --> n313
  n314["base.py"]
  n306 --> n314
  n315["executor.py"]
  n306 --> n315
  n316["models.py"]
  n306 --> n316
  n317["registry.py"]
  n306 --> n317
  n318["voice/"]
  n164 --> n318
  n319["emotion/"]
  n318 --> n319
  n320["stt/"]
  n318 --> n320
  n321["tts/"]
  n318 --> n321
  n322["__init__.py"]
  n318 --> n322
  n323["models.py"]
  n318 --> n323
  n324["pipeline.py"]
  n318 --> n324
  n325["vad.py"]
  n318 --> n325
  n326["__init__.py"]
  n164 --> n326
  n327["main.py"]
  n164 --> n327
  n328["nobla_agent.egg-info/"]
  n163 --> n328
  n329["dependency_links.txt"]
  n328 --> n329
  n330["PKG-INFO"]
  n328 --> n330
  n331["requires.txt"]
  n328 --> n331
  n332["SOURCES.txt"]
  n328 --> n332
  n333["top_level.txt"]
  n328 --> n333
  n334["test/"]
  n163 --> n334
  n335["chroma.sqlite3"]
  n334 --> n335
  n336["test_chromadb/"]
  n163 --> n336
  n337["bf372e00-db18-46d7-8b87-00e6237453d2/"]
  n336 --> n337
  n338["data_level0.bin"]
  n337 --> n338
  n339["header.bin"]
  n337 --> n339
  n340["length.bin"]
  n337 --> n340
  n341["link_lists.bin"]
  n337 --> n341
  n342["chroma.sqlite3"]
  n336 --> n342
  n343["tests/"]
  n163 --> n343
  n344["gateway/"]
  n343 --> n344
  n345["__init__.py"]
  n344 --> n345
  n346["test_mirror_handlers.py"]
  n344 --> n346
  n347["integration/"]
  n343 --> n347
  n348["__init__.py"]
  n347 --> n348
  n349["conftest.py"]
  n347 --> n349
  n350["test_auth_flow.py"]
  n347 --> n350
  n351["test_chat_flow.py"]
  n347 --> n351
  n352["test_chat_send_memory.py"]
  n347 --> n352
  n353["test_code_flow.py"]
  n347 --> n353
  n354["test_concurrent.py"]
  n347 --> n354
  n355["test_persona_flow.py"]
  n347 --> n355
  n356["test_phase5_foundation.py"]
  n347 --> n356
  n357["test_security_flow.py"]
  n347 --> n357
  n358["test_tool_flow.py"]
  n347 --> n358
  n359["test_vision_flow.py"]
  n347 --> n359
  n360["tools/"]
  n343 --> n360
  n361["control/"]
  n360 --> n361
  n362["remote/"]
  n360 --> n362
  n363["__init__.py"]
  n360 --> n363
  n364["test_executor_mirror.py"]
  n360 --> n364
  n365["voice/"]
  n343 --> n365
  n366["__init__.py"]
  n365 --> n366
  n367["conftest.py"]
  n365 --> n367
  n368["test_cosyvoice.py"]
  n365 --> n368
  n369["test_detector.py"]
  n365 --> n369
  n370["test_fish_speech.py"]
  n365 --> n370
  n371["test_integration.py"]
  n365 --> n371
  n372["test_levantine.py"]
  n365 --> n372
  n373["test_models.py"]
  n365 --> n373
  n374["test_pipeline.py"]
  n365 --> n374
  n375["test_stt_base.py"]
  n365 --> n375
  n376["test_tts_base.py"]
  n365 --> n376
  n377["test_vad.py"]
  n365 --> n377
  n378["test_voice_handlers.py"]
  n365 --> n378
  n379["test_whisper.py"]
  n365 --> n379
  n380["__init__.py"]
  n343 --> n380
  n381["_slack_grid_helpers.py"]
  n343 --> n381
  n382["test_academic.py"]
  n343 --> n382
  n383["test_agents_advanced.py"]
  n343 --> n383
  n384["test_agents_phase6v2.py"]
  n343 --> n384
  n385["test_agents.py"]
  n343 --> n385
  n386["test_audit.py"]
  n343 --> n386
  n387["test_auth_api_key.py"]
  n343 --> n387
  n388["test_auth_local.py"]
  n343 --> n388
  n389["test_auth_oauth.py"]
  n343 --> n389
  n390["test_auth.py"]
  n343 --> n390
  n391["test_brave.py"]
  n343 --> n391
  n392["test_channel_webhook_dispatcher.py"]
  n343 --> n392
  n393["test_channel_webhook_per_adapter.py"]
  n343 --> n393
  n394["test_channels.py"]
  n343 --> n394
  n395["test_chat_flow.py"]
  n343 --> n395
  n396["test_circuit_breaker.py"]
  n343 --> n396
  n397["test_code_codegen.py"]
  n343 --> n397
  n398["test_code_debug.py"]
  n343 --> n398
  n399["test_code_git.py"]
  n343 --> n399
  n400["test_code_packages.py"]
  n343 --> n400
  n401["… (96 more)"]
  n343 --> n401
  n402["venv/"]
  n163 --> n402
  n403["Include/"]
  n402 --> n403
  n404["site/"]
  n403 --> n404
  n405["Lib/"]
  n402 --> n405
  n406["site-packages/"]
  n405 --> n406
  n407["Scripts/"]
  n402 --> n407
  n408["activate"]
  n407 --> n408
  n409["activate.bat"]
  n407 --> n409
  n410["Activate.ps1"]
  n407 --> n410
  n411["alembic.exe"]
  n407 --> n411
  n412["chroma.exe"]
  n407 --> n412
  n413["coverage-3.12.exe"]
  n407 --> n413
  n414["coverage.exe"]
  n407 --> n414
  n415["coverage3.exe"]
  n407 --> n415
  n416["deactivate.bat"]
  n407 --> n416
  n417["distro.exe"]
  n407 --> n417
  n418["dmypy.exe"]
  n407 --> n418
  n419["dotenv.exe"]
  n407 --> n419
  n420["f2py.exe"]
  n407 --> n420
  n421["fastapi.exe"]
  n407 --> n421
  n422["hf.exe"]
  n407 --> n422
  n423["httpx.exe"]
  n407 --> n423
  n424["isympy.exe"]
  n407 --> n424
  n425["jsonschema.exe"]
  n407 --> n425
  n426["mako-render.exe"]
  n407 --> n426
  n427["markdown-it.exe"]
  n407 --> n427
  n428["mypy.exe"]
  n407 --> n428
  n429["mypyc.exe"]
  n407 --> n429
  n430["normalizer.exe"]
  n407 --> n430
  n431["numpy-config.exe"]
  n407 --> n431
  n432["onnxruntime_test.exe"]
  n407 --> n432
  n433["… (29 more)"]
  n407 --> n433
  n434["share/"]
  n402 --> n434
  n435["man/"]
  n434 --> n435
  n436["pyvenv.cfg"]
  n402 --> n436
  n437[".env.example"]
  n163 --> n437
  n438["alembic.ini"]
  n163 --> n438
  n439["config.yaml"]
  n163 --> n439
  n440["Dockerfile"]
  n163 --> n440
  n441["pyproject.toml"]
  n163 --> n441
  n442["README.md"]
  n163 --> n442
  n443["docker/"]
  n0 --> n443
  n444["personaplex/"]
  n443 --> n444
  n445["docker-compose.yml"]
  n444 --> n445
  n446["docs/"]
  n0 --> n446
  n447["scm-memory/"]
  n446 --> n447
  n448["legacy_claude.md"]
  n447 --> n448
  n449["legacy_memory.md"]
  n447 --> n449
  n450["session-reports/"]
  n446 --> n450
  n451["SESSION-1-REPORT.md"]
  n450 --> n451
  n452["SESSION-2-REPORT.md"]
  n450 --> n452
  n453["SESSION-3-REPORT.md"]
  n450 --> n453
  n454["superpowers/"]
  n446 --> n454
  n455["plans/"]
  n454 --> n455
  n456["2026-03-17-phase1a-backend-foundation.md"]
  n455 --> n456
  n457["2026-03-17-phase1b-security-auth.md"]
  n455 --> n457
  n458["2026-03-17-phase1c-flutter-app.md"]
  n455 --> n458
  n459["2026-03-17-phase1d-integration-deployment.md"]
  n455 --> n459
  n460["2026-03-19-phase2a-memory-implementation.md"]
  n455 --> n460
  n461["2026-03-20-phase2b1-streaming-auth-circuit-breaker.md"]
  n455 --> n461
  n462["2026-03-20-phase2b2-search-polish.md"]
  n455 --> n462
  n463["2026-03-21-phase3a-voice-pipeline.md"]
  n455 --> n463
  n464["2026-03-21-phase3b1-persona-engine.md"]
  n455 --> n464
  n465["2026-03-21-phase3b2-personaplex-integration.md"]
  n455 --> n465
  n466["2026-03-23-phase3b3a-persona-management-ui.md"]
  n455 --> n466
  n467["2026-03-23-phase4-pre-tool-platform.md"]
  n455 --> n467
  n468["2026-03-24-phase4a-screen-vision.md"]
  n455 --> n468
  n469["2026-03-24-phase4c-code-execution.md"]
  n455 --> n469
  n470["2026-03-25-phase4b-computer-control.md"]
  n455 --> n470
  n471["2026-03-25-phase4d-remote-control.md"]
  n455 --> n471
  n472["2026-03-25-phase4e-flutter-tool-ui.md"]
  n455 --> n472
  n473["2026-03-27-multi-agent-system.md"]
  n455 --> n473
  n474["2026-03-28-self-improving-agent.md"]
  n455 --> n474
  n475["2026-03-28-webhooks-workflows.md"]
  n455 --> n475
  n476["2026-03-29-skills-marketplace.md"]
  n455 --> n476
  n477["2026-03-29-slack-signal-adapters.md"]
  n455 --> n477
  n478["2026-03-29-teams-adapter.md"]
  n455 --> n478
  n479["prompts/"]
  n454 --> n479
  n480["research/"]
  n479 --> n480
  n481["continue-after-multiagent-design.md"]
  n479 --> n481
  n482["continue-after-multiagent-implementation.md"]
  n479 --> n482
  n483["continue-after-phase4e-implementation.md"]
  n479 --> n483
  n484["continue-after-phase5-slack-signal.md"]
  n479 --> n484
  n485["continue-after-phase5-teams.md"]
  n479 --> n485
  n486["continue-after-phase5-whatsapp.md"]
  n479 --> n486
  n487["continue-after-phase5a-6-scheduler.md"]
  n479 --> n487
  n488["continue-after-phase5b1-learning.md"]
  n479 --> n488
  n489["continue-after-phase5b2-marketplace.md"]
  n479 --> n489
  n490["continue-after-phase6-templates.md"]
  n479 --> n490
  n491["continue-after-phase6-webhooks-workflows.md"]
  n479 --> n491
  n492["continue-after-phase6v2-implementation.md"]
  n479 --> n492
  n493["phase4a-continuation-prompt.md"]
  n479 --> n493
  n494["phase4b-continuation-prompt.md"]
  n479 --> n494
  n495["phase4c-continuation-prompt.md"]
  n479 --> n495
  n496["phase4c-implementation-prompt.md"]
  n479 --> n496
  n497["phase4d-continuation-prompt.md"]
  n479 --> n497
  n498["phase4d-implementation-prompt.md"]
  n479 --> n498
  n499["phase4e-continuation-prompt.md"]
  n479 --> n499
  n500["phase5-channels-continuation-prompt.md"]
  n479 --> n500
  n501["specs/"]
  n454 --> n501
  n502["2026-03-17-phase1a-backend-foundation-design.md"]
  n501 --> n502
  n503["2026-03-17-phase1b-security-auth-design.md"]
  n501 --> n503
  n504["2026-03-17-phase1c-flutter-app-design.md"]
  n501 --> n504
  n505["2026-03-19-phase2a-memory-conversation-design.md"]
  n501 --> n505
  n506["2026-03-19-phase2b-router-search-design.md"]
  n501 --> n506
  n507["2026-03-21-phase3-voice-persona-design.md"]
  n501 --> n507
  n508["2026-03-21-phase3b-persona-engine-design.md"]
  n501 --> n508
  n509["2026-03-21-phase3b2-personaplex-integration-design.md"]
  n501 --> n509
  n510["2026-03-23-phase3b3a-persona-management-ui-design.md"]
  n501 --> n510
  n511["2026-03-23-phase4-computer-control-vision-design.md"]
  n501 --> n511
  n512["2026-03-24-phase4a-screen-vision-design.md"]
  n501 --> n512
  n513["2026-03-24-phase4c-code-execution-design.md"]
  n501 --> n513
  n514["2026-03-25-phase4b-computer-control-design.md"]
  n501 --> n514
  n515["2026-03-25-phase4d-remote-control-design.md"]
  n501 --> n515
  n516["2026-03-25-phase4e-flutter-tool-ui-design.md"]
  n501 --> n516
  n517["2026-03-26-phase5-redesign-design.md"]
  n501 --> n517
  n518["2026-03-27-multi-agent-system-design.md"]
  n501 --> n518
  n519["2026-03-28-self-improving-agent-design.md"]
  n501 --> n519
  n520["2026-03-28-webhooks-workflows-design.md"]
  n501 --> n520
  n521["2026-03-29-skills-marketplace-design.md"]
  n501 --> n521
  n522["2026-03-29-slack-signal-adapters-design.md"]
  n501 --> n522
  n523["2026-03-29-teams-adapter-design.md"]
  n501 --> n523
  n524["NEXT-SESSION-PROMPT.md"]
  n446 --> n524
  n525[".env.example"]
  n0 --> n525
  n526[".gitignore"]
  n0 --> n526
  n527["Architecture-Prompt-Template.md"]
  n0 --> n527
  n528["ARCHITECTURE.md"]
  n0 --> n528
  n529["CHANGELOG.md"]
  n0 --> n529
  n530["CLAUDE.md"]
  n0 --> n530
  n531["docker-compose.yml"]
  n0 --> n531
  n532["ggml-levantine-large-v3.bin"]
  n0 --> n532
  n533["Nobla-Agent-Architecture.html"]
  n0 --> n533
  n534["Nobla-Agent-Architecture.pdf"]
  n0 --> n534
  n535["Plan.md"]
  n0 --> n535
  n536["PRD.md"]
  n0 --> n536
  n537["project_file_architecture.md"]
  n0 --> n537
  n538["README.md"]
  n0 --> n538
```

<!-- MEMORY:ARCH:END -->
