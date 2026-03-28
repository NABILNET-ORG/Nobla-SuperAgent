# Phase 6: Webhooks & Workflows Design Spec

**Date:** 2026-03-28
**Status:** Approved
**Approach:** Thin layer on existing infrastructure (Approach 2)
**Scope:** Backend webhooks + workflow engine + Flutter UI (Option D)

---

## Overview

Build an automation layer that receives external events via webhooks and executes multi-step workflows triggered by events, schedules, or manual input. Reuses the proven AgentOrchestrator DAG execution, NoblaEventBus event routing, and TaskDecomposer NL parsing.

**Key decisions:**
- DAG execution model (reuses topological_sort_tasks + asyncio.gather)
- Pluggable signature verification (ABC + HMAC-SHA256 default)
- PostgreSQL persistence for workflows and execution history
- Interactive DAG visualization in Flutter (tappable nodes, inline editing, quick actions, live WebSocket status)
- Pattern matching + payload conditions for triggers (NL-parseable via TaskDecomposer)
- Multi-trigger per workflow
- Workflow versioning

---

## Section 1: Webhook System

### Models

```python
class Webhook(BaseModel):
    webhook_id: str  # UUID
    user_id: str
    name: str
    direction: str  # "inbound" | "outbound"
    url: str  # Inbound: our endpoint URL; Outbound: target URL
    event_type_prefix: str  # e.g., "github.push", "stripe.payment"
    secret: str  # Signing key
    signature_scheme: str  # "hmac-sha256" (default), extensible
    active: bool
    created_at: datetime
    updated_at: datetime

class WebhookEvent(BaseModel):
    event_id: str  # UUID
    webhook_id: str
    headers: dict
    payload: dict
    signature_valid: bool
    status: str  # "received", "processed", "failed"
    retry_count: int
    processed_at: datetime | None
    created_at: datetime

class DeadLetterEvent(BaseModel):
    id: str  # UUID
    webhook_id: str
    event_id: str
    payload: dict
    error: str
    max_retries_reached: bool
    user_notified: bool
    created_at: datetime
```

### Signature Verification

```python
class SignatureVerifier(ABC):
    @abstractmethod
    def verify(self, payload: bytes, signature: str, secret: str) -> bool: ...

class HmacSha256Verifier(SignatureVerifier):
    def verify(self, payload, signature, secret) -> bool:
        expected = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, signature)

class VerifierRegistry:
    _verifiers: dict[str, SignatureVerifier]
    def register(self, scheme: str, verifier: SignatureVerifier): ...
    def get(self, scheme: str) -> SignatureVerifier: ...
```

### Inbound Flow

```
POST /webhooks/inbound/{webhook_id}
  → Lookup webhook from DB
  → Verify signature via VerifierRegistry.get(webhook.signature_scheme)
  → Log to webhook_events table
  → Emit NoblaEvent("webhook.{event_type_prefix}.received", payload=...)
  → Return 200 (or 401 if signature fails)
```

### Outbound Webhooks

- Signs outgoing payloads with configured scheme
- Subscribes to event bus pattern
- Retry with exponential backoff (3 retries: 2s, 8s, 32s)
- Failed after max retries → dead_letter_events table + user notification

### Health Endpoint

```
GET /api/webhooks/{id}/health
→ {
    event_count: int,
    failure_rate: float,  # percentage
    last_received: datetime | null,
    dead_letter_count: int,
    status: "healthy" | "degraded" | "failing"
  }
```

### Gateway Routes

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/webhooks` | Register webhook (inbound or outbound) |
| GET | `/api/webhooks` | List user's webhooks |
| DELETE | `/api/webhooks/{id}` | Deactivate webhook |
| GET | `/api/webhooks/{id}/events` | Event history |
| GET | `/api/webhooks/{id}/health` | Health summary |
| POST | `/api/webhooks/{id}/test` | Send test event |
| POST | `/webhooks/inbound/{webhook_id}` | Inbound webhook receiver |

---

## Section 2: Workflow Engine

### Models

```python
class Workflow(BaseModel):
    workflow_id: str  # UUID
    user_id: str
    name: str
    description: str
    version: int  # Increments on every edit
    status: str  # "active", "paused", "archived"
    created_at: datetime
    updated_at: datetime

class WorkflowStep(BaseModel):
    step_id: str  # UUID
    workflow_id: str
    workflow_version: int
    name: str
    type: str  # "tool", "agent", "condition", "webhook", "delay", "approval"
    config: dict  # Type-specific configuration
    depends_on: list[str]  # Step IDs (DAG edges)
    error_handling: str  # "fail", "retry", "continue", "skip"
    max_retries: int  # Default 0
    timeout_seconds: int | None
    nl_source: str | None  # Original NL text fragment that generated this step

class WorkflowTrigger(BaseModel):
    trigger_id: str  # UUID
    workflow_id: str
    event_pattern: str  # fnmatch pattern, e.g. "webhook.github.*"
    conditions: list[TriggerCondition]  # AND logic
    active: bool

class TriggerCondition(BaseModel):
    field_path: str  # Dot-notation into payload, e.g. "payload.branch"
    operator: str  # "eq", "neq", "gt", "lt", "contains", "exists"
    value: Any  # Comparison value

class WorkflowExecution(BaseModel):
    execution_id: str  # UUID
    workflow_id: str
    workflow_version: int  # Which version was executed
    user_id: str
    trigger_event: dict | None  # The event that triggered this
    status: str  # "pending", "running", "paused", "completed", "failed"
    started_at: datetime
    completed_at: datetime | None

class StepExecution(BaseModel):
    id: str  # UUID
    execution_id: str
    step_id: str
    status: str  # "pending", "running", "completed", "failed", "skipped"
    result: dict | None
    error: str | None
    started_at: datetime | None
    completed_at: datetime | None
```

### Condition Steps — Named Branches

Condition steps support multiple named branches with if/else logic:

```python
# Condition step config
{
    "type": "condition",
    "config": {
        "branches": [
            {
                "name": "tests_passed",
                "condition": {"field": "step_1.result.exit_code", "op": "eq", "value": 0},
                "next_steps": ["step_deploy"]
            },
            {
                "name": "tests_failed",
                "condition": {"field": "step_1.result.exit_code", "op": "neq", "value": 0},
                "next_steps": ["step_notify_failure"]
            }
        ],
        "default_branch": "tests_failed"
    }
}
```

Branch evaluation: first matching branch wins. `default_branch` is fallback. Steps in non-taken branches are marked "skipped".

### Workflow Versioning

- Every edit to a workflow increments `workflow.version`
- `WorkflowStep` rows include `workflow_version` — old versions preserved
- `WorkflowExecution` records `workflow_version` it ran against
- Active triggers always point to latest version
- Previous versions are queryable for audit/rollback

### NL Workflow Creation

```
User: "When GitHub pushes to main, run tests, if they pass deploy to staging, then notify on Slack"
  → TaskDecomposer parses into:
    Triggers: [
        {event_pattern: "webhook.github.push", conditions: [{field: "payload.branch", op: "eq", value: "main"}]}
    ]
    Steps: [
        {id: "s1", name: "Run tests", type: "tool", config: {tool: "code.run", command: "pytest"}, nl_source: "run tests"},
        {id: "s2", name: "Check results", type: "condition", config: {branches: [...]}, depends_on: ["s1"], nl_source: "if they pass"},
        {id: "s3", name: "Deploy staging", type: "tool", config: {...}, depends_on: ["s2"], nl_source: "deploy to staging"},
        {id: "s4", name: "Notify Slack", type: "webhook", config: {...}, depends_on: ["s3"], nl_source: "notify on Slack"}
    ]
```

Each step's `nl_source` field stores the original text fragment for UI attribution.

### Execution Engine (WorkflowExecutor)

1. Receives trigger event from `TriggerMatcher`
2. Creates `WorkflowExecution` record (with current workflow version)
3. Loads `WorkflowStep` list for that version
4. Converts steps → task list, runs `topological_sort_tasks()` for tier grouping
5. Executes tiers sequentially, steps within tier via `asyncio.gather()`
6. Condition steps evaluate branches, dynamically enable/disable downstream steps
7. Each step updates `StepExecution` row + emits events on bus
8. Events: `workflow.execution.started`, `workflow.step.{started|completed|failed|skipped}`, `workflow.execution.{completed|failed}`

### Trigger Matching (TriggerMatcher)

- Subscribes to configurable event prefix set on NoblaEventBus
- For each event: match against all active triggers using `fnmatch`
- If pattern matches: evaluate all `TriggerCondition` against event payload (AND logic)
- All conditions pass → create WorkflowExecution
- Deduplication: same trigger_id + correlation_id within 5s window is dropped
- Conditions are NL-parseable: TaskDecomposer converts "when branch is main" → `{field: "payload.branch", op: "eq", value: "main"}`

### Per-Step Error Handling

| Strategy | Behavior |
|----------|----------|
| `fail` | Mark step + execution as failed, cascade to dependents |
| `retry` | Re-run up to max_retries with exponential backoff |
| `continue` | Mark step failed, dependents still proceed |
| `skip` | Skip step entirely, dependents proceed |

---

## Section 3: Flutter UI

### 3A: Workflow List Screen

- Tab in automation section (alongside scheduled tasks)
- Cards: workflow name, status badge (active/paused/archived), trigger count, last execution time + status
- FAB → NL Workflow Creator
- Swipe actions: pause/resume, archive, delete
- Filter chips: All / Active / Paused / Failed recently

### 3B: Workflow Detail Screen

- Header: name, description, version badge, status toggle
- Triggers section: list with event pattern + conditions, tap to edit, add button
- Interactive DAG visualization (WorkflowDagView)
- Execution history: scrollable list of past runs with status + duration

### 3C: Interactive DAG Widget (WorkflowDagView)

**Rendering:**
- Custom paint or graph library node-edge renderer
- Nodes colored by type: tool=blue, agent=purple, condition=amber, webhook=green, delay=gray, approval=orange
- Directed edge arrows showing dependencies
- Condition nodes show named branch labels on outgoing edges

**Interactivity (tappable nodes):**
- Tap opens inline bottom sheet:
  - Step name, type, config summary
  - Edit button → form to modify step config
  - Quick actions (contextual to execution state): Pause / Retry / Skip
  - Output preview (last execution result)

**Live execution mode (WebSocket):**
- Subscribe to `workflow.execution.*` events
- Node state animation: pending (outline) → running (pulsing) → completed (solid green) → failed (solid red) → skipped (dimmed)
- Current tier highlighted
- Auto-scroll to active tier

### 3D: Webhook Management Screen

- List of webhooks with health summary (event count, failure rate, last received)
- Tap for detail: event history, dead letter events, test button
- Register form: name, event prefix, signature scheme picker

### 3E: NL Workflow Creator

- Full-screen text input: "Describe your workflow in plain language"
- Submit → loading → preview of parsed workflow
- Preview shows DAG visualization with **NL source attribution chips** on each node — small label showing which part of the user's original text generated that step
- User reviews, taps nodes to adjust, confirms to save
- Edit mode: pre-populated with existing workflow description

### State Management (Riverpod)

| Provider | Purpose |
|----------|---------|
| `workflowListProvider` | Paginated workflow list from REST API |
| `workflowDetailProvider(id)` | Single workflow + version info |
| `workflowExecutionProvider(id)` | Live execution state via WebSocket |
| `webhookListProvider` | Webhook list with health summaries |
| `dagLayoutProvider(workflow)` | Computes node positions from step graph |

### WebSocket Integration

- Subscribe to `workflow.execution.*` events for active workflow
- Provider updates node states in real-time
- Optimistic UI for quick actions with server confirmation

---

## File Map

### Backend — New Files

| File | Responsibility |
|------|---------------|
| `backend/nobla/automation/webhooks/__init__.py` | Package init |
| `backend/nobla/automation/webhooks/models.py` | Webhook, WebhookEvent, DeadLetterEvent, OutboundWebhook |
| `backend/nobla/automation/webhooks/verification.py` | SignatureVerifier ABC, HmacSha256Verifier, VerifierRegistry |
| `backend/nobla/automation/webhooks/manager.py` | WebhookManager — CRUD, health, inbound processing |
| `backend/nobla/automation/webhooks/outbound.py` | OutboundWebhookHandler — event subscription, retry, dead letter |
| `backend/nobla/automation/workflows/__init__.py` | Package init |
| `backend/nobla/automation/workflows/models.py` | Workflow, WorkflowStep, WorkflowTrigger, TriggerCondition, WorkflowExecution, StepExecution |
| `backend/nobla/automation/workflows/trigger_matcher.py` | TriggerMatcher — event pattern + condition evaluation |
| `backend/nobla/automation/workflows/executor.py` | WorkflowExecutor — DAG execution via topological tiers |
| `backend/nobla/automation/workflows/interpreter.py` | NL → Workflow parsing (extends TaskDecomposer) |
| `backend/nobla/automation/workflows/service.py` | WorkflowService — orchestrates CRUD, versioning, execution |
| `backend/nobla/gateway/webhook_handlers.py` | REST routes for webhook management + inbound receiver |
| `backend/nobla/gateway/workflow_handlers.py` | REST routes for workflow CRUD + execution + triggers |

### Backend — Modified Files

| File | Change |
|------|--------|
| `backend/nobla/config/settings.py` | Add WebhookSettings, WorkflowSettings |
| `backend/nobla/gateway/lifespan.py` | Wire webhook manager + workflow service |
| `backend/nobla/automation/__init__.py` | Re-export new modules |

### Tests — New Files

| File | Coverage |
|------|----------|
| `backend/tests/test_webhooks.py` | Webhook models, verification, manager, inbound, outbound, health, dead letter |
| `backend/tests/test_workflows.py` | Workflow models, versioning, trigger matching, conditions, executor, NL parsing, service |

### Flutter — New Files

| File | Responsibility |
|------|---------------|
| `app/lib/features/automation/models/workflow_models.dart` | Dart models matching backend |
| `app/lib/features/automation/models/webhook_models.dart` | Dart webhook models |
| `app/lib/features/automation/providers/workflow_providers.dart` | Riverpod providers |
| `app/lib/features/automation/providers/webhook_providers.dart` | Riverpod providers |
| `app/lib/features/automation/screens/workflow_list_screen.dart` | Workflow list with filters |
| `app/lib/features/automation/screens/workflow_detail_screen.dart` | Detail + DAG + history |
| `app/lib/features/automation/screens/workflow_creator_screen.dart` | NL input + preview |
| `app/lib/features/automation/screens/webhook_screen.dart` | Webhook management |
| `app/lib/features/automation/widgets/workflow_dag_view.dart` | Interactive DAG visualization |
| `app/lib/features/automation/widgets/step_node_widget.dart` | Tappable step node |
| `app/lib/features/automation/widgets/nl_source_chip.dart` | NL attribution chip |
| `app/lib/features/automation/widgets/step_bottom_sheet.dart` | Inline edit + quick actions |

### Flutter — Modified Files

| File | Change |
|------|--------|
| `app/lib/features/automation/screens/automation_screen.dart` | Add Workflows tab |
| `app/lib/core/routing/app_router.dart` | Add workflow routes |

---

## Integration Points

### Reused Infrastructure

| Component | How It's Reused |
|-----------|----------------|
| `NoblaEventBus` | Trigger matching subscribes to events, workflow emits lifecycle events |
| `topological_sort_tasks()` | DAG execution of workflow steps |
| `asyncio.gather()` | Parallel step execution within tiers |
| `TaskDecomposer` | NL → workflow parsing (extended prompt) |
| `ToolExecutor` | Runs tool-type steps |
| `AgentOrchestrator` | Runs agent-type steps |
| `ConfirmationManager` | Approval-type steps |
| `ApprovalManager` | User confirmation for dangerous steps |
| `KillSwitch` | Emergency halt of workflow executions |

### Event Topics

| Topic | Emitter |
|-------|---------|
| `webhook.{prefix}.received` | Inbound webhook handler |
| `webhook.{prefix}.outbound.sent` | Outbound webhook handler |
| `webhook.{prefix}.outbound.failed` | Outbound webhook handler |
| `webhook.dead_letter` | Dead letter handler |
| `workflow.execution.started` | WorkflowExecutor |
| `workflow.step.started` | WorkflowExecutor |
| `workflow.step.completed` | WorkflowExecutor |
| `workflow.step.failed` | WorkflowExecutor |
| `workflow.step.skipped` | WorkflowExecutor |
| `workflow.execution.completed` | WorkflowExecutor |
| `workflow.execution.failed` | WorkflowExecutor |
| `workflow.execution.paused` | WorkflowExecutor |
