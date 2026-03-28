# Continuation Prompt — After Phase 6 Webhooks & Workflows

**Paste this into a new Claude Code session to continue development.**

---

## Context

Nobla Agent is on `main`. **926 tests passing (167 Flutter + 759 backend).**

### What was just completed:

**Phase 6 — Webhooks & Workflows (13 tasks, all complete):**

**Webhook System (110 backend tests):**
1. **Models + verification** (`automation/webhooks/models.py`, `verification.py`): Webhook, WebhookEvent, DeadLetterEvent, WebhookHealth models. SignatureVerifier ABC + HmacSha256Verifier + HmacSha1Verifier + NoneVerifier + VerifierRegistry. WebhookSettings + WorkflowSettings in config.
2. **WebhookManager** (`automation/webhooks/manager.py`): CRUD, inbound processing (signature verify → event log → emit on bus), health computation, dead letter queue with user notifications, test event support.
3. **Outbound handler** (`automation/webhooks/outbound.py`): Event bus subscription, HMAC signing, exponential retry (configurable backoff), dead letter on exhaustion, success/failure event emission.
4. **Gateway routes** (`gateway/webhook_handlers.py`): 9 REST endpoints — register, list, delete, status update, events, health, dead-letters, test, inbound receiver. Signature extraction from common headers.

**Workflow Engine (148 backend tests):**
5. **Models + versioning** (`automation/workflows/models.py`): Workflow (versioned with bump/history/rollback), WorkflowStep (6 types), WorkflowTrigger, TriggerCondition (8 operators), ConditionBranch + ConditionConfig (named branches with if/else), WorkflowExecution, StepExecution. evaluate_conditions() + resolve_field_path() helpers.
6. **Trigger matcher** (`automation/workflows/trigger_matcher.py`): Event bus subscription, fnmatch pattern matching, payload condition evaluation (AND logic), deduplication window, stats tracking, callback dispatch.
7. **Workflow executor** (`automation/workflows/executor.py`): topological_sort_steps() via Kahn's algorithm, tier-based asyncio.gather parallel execution, 6 step type handlers (tool/agent/condition/webhook/delay/approval), condition branch evaluation (enable/disable downstream steps), 4 error handling strategies (fail cascade/retry/continue/skip), lifecycle event emission.
8. **NL interpreter** (`automation/workflows/interpreter.py`): LLM prompt → JSON parsing with two-pass id resolution (LLM short ids → UUIDs), condition ref resolution in branches, heuristic fallback (trigger extraction, clause splitting, keyword-based step type detection), nl_source fragment extraction.
9. **Workflow service** (`automation/workflows/service.py`): CRUD orchestrator, NL creation, versioning (auto-bump on edit), trigger registration/unregistration, manual trigger, concurrent execution limits, execution history.
10. **Gateway routes** (`gateway/workflow_handlers.py`): 9 REST endpoints — create from NL, list, get detail, update, status, delete, trigger, executions, execution detail.

**Flutter UI (82 Flutter tests):**
11. **Models + providers**: Dart models matching all backend types, Riverpod providers (workflowList, workflowDetail, workflowExecution StateNotifier, dagLayout, webhookList, webhookHealth, webhookEvents).
12. **Screens**: AutomationScreen (2-tab: Workflows/Webhooks), WorkflowListScreen (cards, filter chips, FAB, create sheet), WebhookScreen (cards with health, register form), 7th nav destination in app_router.
13. **DAG visualization**: StepNodeWidget (type coloring, status animations — pulsing/dimmed/solid borders), StepBottomSheet (NL source attribution, config summary, execution result, quick actions — retry/skip/pause), WorkflowDagView (InteractiveViewer, CustomPaint curved edges with arrowheads, tap-to-sheet), NlSourceChip.
14. **Creator + detail**: WorkflowCreatorScreen (NL input → parse → preview DAG with source chips → edit/confirm flow), WorkflowDetailScreen (header + version badge + status toggle, triggers list, DAG with live execution states, execution history).

**Gateway wiring** (`gateway/lifespan.py`): WebhookManager + OutboundWebhookHandler + WorkflowService initialized in lifespan, kill switch integration, cleanup on shutdown.

### Architecture decisions to preserve:
- **Pluggable verification**: SignatureVerifier ABC + VerifierRegistry — users register custom verifiers by scheme name
- **Dead letter pattern**: Failed events after max retries → dead_letter table + `webhook.dead_letter` event (priority 5) for user notification
- **Health computation**: failure_rate thresholds — <10% healthy, 10-50% degraded, >50% failing
- **Workflow versioning**: bump_version() snapshots current state, increments version, old versions queryable via get_version()
- **Condition branches**: Named branches with first-match-wins logic, default_branch fallback, non-taken branches disable downstream steps
- **Trigger dedup**: (trigger_id, correlation_id) pairs cached for configurable window (default 5s)
- **Executor reuse**: topological_sort_steps() is workflow-specific Kahn's algorithm (same pattern as agents/models.py topological_sort_tasks)
- **NL two-pass parsing**: First pass creates steps (maps LLM short ids to UUIDs), second pass resolves depends_on refs + condition branch next_steps
- **Heuristic fallback**: Keyword-based step type detection + trigger extraction when LLM unavailable
- **Flutter DAG**: computeDagLayout() in Dart mirrors backend Kahn's algorithm, InteractiveViewer for pan/zoom, CustomPaint for edges

### Module structure (new files):
```
backend/nobla/automation/webhooks/
├── __init__.py
├── models.py             # Webhook, WebhookEvent, DeadLetterEvent, WebhookHealth, enums
├── verification.py       # SignatureVerifier ABC, HmacSha256/Sha1/None, VerifierRegistry
├── manager.py            # WebhookManager — CRUD, inbound, health, dead letter
└── outbound.py           # OutboundWebhookHandler — subscribe, sign, retry, dead letter

backend/nobla/automation/workflows/
├── __init__.py
├── models.py             # Workflow, WorkflowStep, WorkflowTrigger, conditions, versioning
├── trigger_matcher.py    # TriggerMatcher — fnmatch + conditions + dedup
├── executor.py           # WorkflowExecutor — DAG tiers, 6 step types, error handling
├── interpreter.py        # WorkflowInterpreter — LLM + heuristic NL parsing
└── service.py            # WorkflowService — CRUD, versioning, triggers, execution

backend/nobla/gateway/
├── webhook_handlers.py   # 9 REST routes + schemas
└── workflow_handlers.py  # 9 REST routes + schemas

app/lib/features/automation/
├── models/
│   ├── workflow_models.dart  # Dart models + enums + computeDagLayout
│   └── webhook_models.dart   # Dart webhook models
├── providers/
│   ├── workflow_providers.dart  # Riverpod providers + StateNotifier
│   └── webhook_providers.dart   # Riverpod webhook providers
├── screens/
│   ├── automation_screen.dart        # 2-tab (Workflows/Webhooks)
│   ├── workflow_list_screen.dart     # Cards, filters, FAB, create sheet
│   ├── webhook_screen.dart           # Webhook list, register form
│   ├── workflow_creator_screen.dart  # NL input → preview → confirm
│   └── workflow_detail_screen.dart   # Header, triggers, DAG, history
└── widgets/
    ├── workflow_dag_view.dart   # InteractiveViewer + CustomPaint edges
    ├── step_node_widget.dart    # Tappable node with animations
    ├── step_bottom_sheet.dart   # Details + quick actions
    └── nl_source_chip.dart      # NL attribution chip

backend/tests/
├── test_webhooks.py          # 110 tests
├── test_workflows.py         # 121 tests
└── test_workflows_service.py # 27 tests

app/test/features/automation/
├── workflow_models_test.dart  # 24 tests
├── webhook_models_test.dart   # 12 tests
├── screens_test.dart          # 13 tests
├── widgets_test.dart          # 20 tests
└── creator_detail_test.dart   # 13 tests
```

### What to do next — choose one:

**Option A: Phase 5 — Remaining channel adapters (WhatsApp, Slack, Signal, Teams, etc.)**
- 15 platform adapters following the Telegram/Discord pattern

**Option B: Phase 7 — Full Feature Set**
- Media, finance, health, social, smart home tools

**Option C: MCP marketplace**
- Discover and install MCP servers
- Community MCP server registry

**Option D: Phase 6 — Remaining sub-phases**
- 6-Webhooks-Outbound: UI for outbound webhook management
- 6-Workflows: Visual workflow templates, workflow import/export

### Test commands:
```bash
# Run all Flutter tests (167 tests)
cd app && flutter test

# Run all backend tests (759 tests)
cd backend && pytest tests/ -v --ignore=tests/test_chat_flow.py --ignore=tests/test_consolidation.py --ignore=tests/test_extraction.py --ignore=tests/test_orchestrator.py --ignore=tests/test_routes.py --ignore=tests/test_security_integration.py --ignore=tests/test_websocket.py

# Run webhook tests only (110 tests)
cd backend && pytest tests/test_webhooks.py -v

# Run workflow tests only (148 tests)
cd backend && pytest tests/test_workflows.py tests/test_workflows_service.py -v

# Run Flutter automation tests only (82 tests)
cd app && flutter test test/features/automation/

# Verify line counts (750-line limit)
find backend/nobla/automation/webhooks backend/nobla/automation/workflows -name "*.py" -exec wc -l {} + | sort -rn
```

### Key files to read first:
- `CLAUDE.md` — Full project guide with all phase status
- `docs/superpowers/specs/2026-03-28-webhooks-workflows-design.md` — Design spec
- `docs/superpowers/plans/2026-03-28-webhooks-workflows.md` — Implementation plan
- `backend/nobla/automation/webhooks/manager.py` — Webhook CRUD + inbound processing
- `backend/nobla/automation/workflows/executor.py` — DAG execution engine
- `backend/nobla/automation/workflows/trigger_matcher.py` — Event pattern matching
- `backend/nobla/automation/workflows/interpreter.py` — NL parsing
- `backend/nobla/gateway/lifespan.py` — Service wiring
- `app/lib/features/automation/widgets/workflow_dag_view.dart` — Interactive DAG widget
