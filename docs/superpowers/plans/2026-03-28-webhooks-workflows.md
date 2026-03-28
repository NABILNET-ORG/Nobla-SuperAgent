# Phase 6 Webhooks & Workflows Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build webhook receiver/sender system, multi-step workflow engine with DAG execution, trigger matching, NL creation, and interactive Flutter UI with live DAG visualization.

**Architecture:** Thin layer on existing infrastructure — webhooks emit events on NoblaEventBus, TriggerMatcher subscribes and launches WorkflowExecutor which reuses topological_sort_tasks + asyncio.gather for parallel DAG execution.

**Tech Stack:** Python 3.12, asyncio, Pydantic, FastAPI, PostgreSQL (SQLAlchemy), NoblaEventBus, TaskDecomposer, Flutter/Riverpod

**Spec:** `docs/superpowers/specs/2026-03-28-webhooks-workflows-design.md`

---

## File Map

### New files (create)
| File | Responsibility |
|------|---------------|
| `backend/nobla/automation/webhooks/__init__.py` | Package init + lazy imports |
| `backend/nobla/automation/webhooks/models.py` | Webhook, WebhookEvent, DeadLetterEvent |
| `backend/nobla/automation/webhooks/verification.py` | SignatureVerifier ABC, HmacSha256Verifier, VerifierRegistry |
| `backend/nobla/automation/webhooks/manager.py` | WebhookManager — CRUD, health, inbound processing |
| `backend/nobla/automation/webhooks/outbound.py` | OutboundWebhookHandler — event sub, retry, dead letter |
| `backend/nobla/automation/workflows/__init__.py` | Package init + lazy imports |
| `backend/nobla/automation/workflows/models.py` | Workflow, WorkflowStep, WorkflowTrigger, TriggerCondition, WorkflowExecution, StepExecution |
| `backend/nobla/automation/workflows/trigger_matcher.py` | TriggerMatcher — event pattern + condition evaluation |
| `backend/nobla/automation/workflows/executor.py` | WorkflowExecutor — DAG execution via topological tiers |
| `backend/nobla/automation/workflows/interpreter.py` | NL → Workflow parsing (extends TaskDecomposer pattern) |
| `backend/nobla/automation/workflows/service.py` | WorkflowService — orchestrates CRUD, versioning, execution |
| `backend/nobla/gateway/webhook_handlers.py` | REST routes for webhook management + inbound receiver |
| `backend/nobla/gateway/workflow_handlers.py` | REST routes for workflow CRUD + execution + triggers |
| `backend/tests/test_webhooks.py` | Webhook tests |
| `backend/tests/test_workflows.py` | Workflow tests |
| `app/lib/features/automation/models/workflow_models.dart` | Dart workflow models |
| `app/lib/features/automation/models/webhook_models.dart` | Dart webhook models |
| `app/lib/features/automation/providers/workflow_providers.dart` | Riverpod workflow providers |
| `app/lib/features/automation/providers/webhook_providers.dart` | Riverpod webhook providers |
| `app/lib/features/automation/screens/workflow_list_screen.dart` | Workflow list + filters |
| `app/lib/features/automation/screens/workflow_detail_screen.dart` | Detail + DAG + history |
| `app/lib/features/automation/screens/workflow_creator_screen.dart` | NL input + preview |
| `app/lib/features/automation/screens/webhook_screen.dart` | Webhook management |
| `app/lib/features/automation/widgets/workflow_dag_view.dart` | Interactive DAG visualization |
| `app/lib/features/automation/widgets/step_node_widget.dart` | Tappable step node |
| `app/lib/features/automation/widgets/nl_source_chip.dart` | NL attribution chip |
| `app/lib/features/automation/widgets/step_bottom_sheet.dart` | Inline edit + quick actions |

### Modified files
| File | Change |
|------|--------|
| `backend/nobla/config/settings.py` | Add WebhookSettings, WorkflowSettings |
| `backend/nobla/gateway/lifespan.py` | Wire webhook + workflow services |
| `backend/nobla/automation/__init__.py` | Re-export webhooks/workflows |
| `app/lib/features/automation/screens/automation_screen.dart` | Add Workflows tab |
| `app/lib/core/routing/app_router.dart` | Add workflow routes |

---

## Steps

### Step 1: Webhook Models + Signature Verification
- [ ] Create `backend/nobla/automation/webhooks/__init__.py`
- [ ] Create `backend/nobla/automation/webhooks/models.py` — Webhook, WebhookEvent, DeadLetterEvent, OutboundWebhook models with Pydantic
- [ ] Create `backend/nobla/automation/webhooks/verification.py` — SignatureVerifier ABC, HmacSha256Verifier, VerifierRegistry
- [ ] Add WebhookSettings to `backend/nobla/config/settings.py`
- [ ] Write tests for models + verification (target: 20+ tests)

### Step 2: Webhook Manager + Inbound Handler
- [ ] Create `backend/nobla/automation/webhooks/manager.py` — WebhookManager with CRUD, inbound processing, health computation, dead letter handling
- [ ] Create `backend/nobla/gateway/webhook_handlers.py` — REST routes: POST/GET/DELETE /api/webhooks, GET /health, POST /test, POST /webhooks/inbound/{id}
- [ ] Wire event bus integration — emit `webhook.{prefix}.received` on inbound
- [ ] Write tests for manager + handlers (target: 25+ tests)

### Step 3: Outbound Webhooks + Dead Letter
- [ ] Create `backend/nobla/automation/webhooks/outbound.py` — OutboundWebhookHandler with event subscription, HMAC signing, exponential retry, dead letter persistence
- [ ] Add user notification on dead letter (emit `webhook.dead_letter` event)
- [ ] Write tests for outbound + retry + dead letter (target: 15+ tests)

### Step 4: Workflow Models + Versioning
- [ ] Create `backend/nobla/automation/workflows/__init__.py`
- [ ] Create `backend/nobla/automation/workflows/models.py` — Workflow, WorkflowStep, WorkflowTrigger, TriggerCondition, WorkflowExecution, StepExecution with versioning
- [ ] Implement condition step with named branches (if/else, multiple branches, default_branch)
- [ ] Write tests for models + versioning + conditions (target: 20+ tests)

### Step 5: Trigger Matcher
- [ ] Create `backend/nobla/automation/workflows/trigger_matcher.py` — TriggerMatcher subscribes to event bus, fnmatch pattern matching, payload condition evaluation, deduplication (5s window)
- [ ] Support all operators: eq, neq, gt, lt, contains, exists
- [ ] Support dot-notation field paths into nested payloads
- [ ] Write tests for trigger matching + conditions + dedup (target: 20+ tests)

### Step 6: Workflow Executor (DAG Engine)
- [ ] Create `backend/nobla/automation/workflows/executor.py` — WorkflowExecutor converts steps to task list, topological sort into tiers, asyncio.gather per tier
- [ ] Implement all step types: tool, agent, condition, webhook, delay, approval
- [ ] Implement condition branch evaluation — enable/disable downstream steps dynamically
- [ ] Implement per-step error handling: fail (cascade), retry (backoff), continue, skip
- [ ] Emit lifecycle events: workflow.execution.started, workflow.step.*, workflow.execution.completed/failed
- [ ] Write tests for executor + all step types + error handling (target: 30+ tests)

### Step 7: NL Workflow Interpreter
- [ ] Create `backend/nobla/automation/workflows/interpreter.py` — WorkflowInterpreter extends TaskDecomposer pattern for workflow-specific parsing
- [ ] Parse triggers from NL ("when X happens", "every Monday at 9am")
- [ ] Parse conditions from NL ("if tests pass", "when branch is main")
- [ ] Extract nl_source fragments for UI attribution
- [ ] Heuristic fallback for when LLM is unavailable
- [ ] Write tests for NL interpretation (target: 15+ tests)

### Step 8: Workflow Service + Gateway Routes
- [ ] Create `backend/nobla/automation/workflows/service.py` — WorkflowService orchestrates CRUD, versioning, trigger registration, execution management
- [ ] Create `backend/nobla/gateway/workflow_handlers.py` — REST routes: POST/GET/PUT workflows, POST trigger, GET executions, POST step actions (pause/retry/skip)
- [ ] Wire into gateway lifespan (`backend/nobla/gateway/lifespan.py`)
- [ ] Update `backend/nobla/automation/__init__.py` with re-exports
- [ ] Write tests for service + handlers (target: 20+ tests)

### Step 9: Flutter Models + Providers
- [ ] Create `app/lib/features/automation/models/workflow_models.dart` — Dart models matching backend (Workflow, WorkflowStep, WorkflowTrigger, WorkflowExecution, StepExecution)
- [ ] Create `app/lib/features/automation/models/webhook_models.dart` — Dart webhook models
- [ ] Create `app/lib/features/automation/providers/workflow_providers.dart` — workflowListProvider, workflowDetailProvider, workflowExecutionProvider, dagLayoutProvider
- [ ] Create `app/lib/features/automation/providers/webhook_providers.dart` — webhookListProvider
- [ ] Write tests for models + providers (target: 20+ tests)

### Step 10: Workflow List + Webhook Screens
- [ ] Create `app/lib/features/automation/screens/workflow_list_screen.dart` — cards, FAB, swipe actions, filter chips
- [ ] Create `app/lib/features/automation/screens/webhook_screen.dart` — webhook list with health, detail, register form
- [ ] Add Workflows tab to `app/lib/features/automation/screens/automation_screen.dart`
- [ ] Update `app/lib/core/routing/app_router.dart` with workflow routes
- [ ] Write widget tests (target: 15+ tests)

### Step 11: Interactive DAG Visualization
- [ ] Create `app/lib/features/automation/widgets/workflow_dag_view.dart` — node-edge renderer with type-based coloring, directed arrows, branch labels
- [ ] Create `app/lib/features/automation/widgets/step_node_widget.dart` — tappable node with state-based styling (outline/pulsing/solid)
- [ ] Create `app/lib/features/automation/widgets/step_bottom_sheet.dart` — inline edit form, quick actions (pause/retry/skip), output preview
- [ ] Implement live execution mode — WebSocket subscription, node state animation, auto-scroll to active tier
- [ ] Write widget tests for DAG (target: 15+ tests)

### Step 12: NL Workflow Creator + Source Attribution
- [ ] Create `app/lib/features/automation/widgets/nl_source_chip.dart` — small label showing original NL text fragment
- [ ] Create `app/lib/features/automation/screens/workflow_creator_screen.dart` — full-screen NL input, submit → preview with DAG + attribution chips
- [ ] Create `app/lib/features/automation/screens/workflow_detail_screen.dart` — header, triggers, DAG view, execution history
- [ ] Implement edit mode with pre-populated NL description
- [ ] Write widget tests (target: 15+ tests)

### Step 13: Integration + Gateway Wiring + Docs
- [ ] Wire webhook manager + workflow service into gateway lifespan (kill switch gated)
- [ ] End-to-end integration: webhook received → trigger matched → workflow executed → events emitted → Flutter UI updated
- [ ] Update CLAUDE.md, Plan.md with Phase 6 Webhooks & Workflows completion status
- [ ] Run full test suite — target: 586 existing + ~195 new = ~780+ total tests
- [ ] Verify 750-line limit on all new files

---

## Dependencies Between Steps

```
Step 1 (webhook models) ──→ Step 2 (webhook manager) ──→ Step 3 (outbound + dead letter)
Step 4 (workflow models) ──→ Step 5 (trigger matcher) ──→ Step 6 (executor)
Step 6 (executor) + Step 7 (NL interpreter) ──→ Step 8 (service + routes)
Step 1-3 + Step 4-8 ──→ Step 13 (integration)

Step 9 (Flutter models) ──→ Step 10 (list screens) ──→ Step 11 (DAG widget)
Step 11 (DAG widget) ──→ Step 12 (creator + detail screens)
Step 9-12 ──→ Step 13 (integration)
```

**Parallelizable tiers:**
- Tier 0: Steps 1, 4, 9 (independent foundations)
- Tier 1: Steps 2, 5, 10 (depend on tier 0)
- Tier 2: Steps 3, 6, 7, 11 (depend on tier 1)
- Tier 3: Steps 8, 12 (depend on tier 2)
- Tier 4: Step 13 (integration, depends on all)

---

## Test Targets

| Step | Module | Target Tests |
|------|--------|-------------|
| 1 | Webhook models + verification | 20+ |
| 2 | Webhook manager + handlers | 25+ |
| 3 | Outbound + dead letter | 15+ |
| 4 | Workflow models + versioning | 20+ |
| 5 | Trigger matcher | 20+ |
| 6 | Workflow executor | 30+ |
| 7 | NL interpreter | 15+ |
| 8 | Workflow service + routes | 20+ |
| 9 | Flutter models + providers | 20+ |
| 10 | Workflow list + webhook screens | 15+ |
| 11 | DAG visualization | 15+ |
| 12 | NL creator + detail screens | 15+ |
| 13 | Integration verification | — |
| **Total** | | **~230+ new tests** |
