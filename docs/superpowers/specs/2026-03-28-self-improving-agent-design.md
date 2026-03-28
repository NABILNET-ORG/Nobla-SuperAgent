# Phase 5B.1: Self-Improving Agent — Design Spec

**Date:** 2026-03-28
**Status:** Approved
**Author:** Nobla Agent Team
**Depends on:** Phase 2 (Memory), Phase 5-Foundation (Event Bus, Skill Runtime), Phase 6 (Multi-Agent, Workflows)

---

## 1. Overview

The Self-Improving Agent (SIA) is a learning layer that observes all agent activity via the event bus, collects user feedback, detects behavioral patterns, generates reusable skills from repeated workflows, A/B tests LLM models and prompt templates, and proactively suggests optimizations. All learning data stays local in procedural memory.

### Goals

- Collect structured feedback (thumbs + stars + comments) on every agent response
- Detect repeated tool sequences (cheap hash matching) and similar intents (LLM clustering)
- Auto-generate workflow macros from confirmed patterns, with promotion path to full skills
- Compare LLM models + prompt templates via epsilon-greedy A/B experiments
- Proactively suggest improvements at a user-configurable aggressiveness level
- Prepare auto-generated skills for future marketplace publishing (Phase 5B.2)

### Non-Goals

- Skills Marketplace backend/UI (Phase 5B.2)
- Model fine-tuning or retraining
- Cross-user learning or federated data sharing
- Real-time streaming analytics dashboard

---

## 2. Architecture

```
Event Bus (tool.executed, agent.*, scheduler.*)
    │
    ├── FeedbackCollector ──→ Procedural Memory (feedback records)
    │                              │
    ├── PatternDetector ───→ Procedural Memory (pattern candidates)
    │       │                      │
    │       └── SkillGenerator ──→ Workflow Engine (macros) → Skill Runtime (promoted)
    │
    ├── ABTestManager ─────→ LLM Router (variant assignment) → Procedural Memory (results)
    │
    └── ProactiveEngine ───→ WebSocket → Flutter (suggestion cards)
```

Five backend modules, one gateway handler, one Flutter feature.

### Storage Strategy

The existing `ProceduralMemory` stores only `Procedure` records (Bayesian-scored workflows). Rather than force-fitting learning data into that schema, the learning module uses its **own SQLAlchemy models** in `backend/nobla/learning/models.py` with dedicated tables:

| Table | Purpose |
|-------|---------|
| `learning_feedback` | ResponseFeedback records |
| `learning_patterns` | PatternCandidate records |
| `learning_macros` | WorkflowMacro records |
| `learning_experiments` | ABExperiment + ABVariant records |
| `learning_suggestions` | ProactiveSuggestion records |

These tables use the same PostgreSQL database and SQLAlchemy engine as the existing memory tables. The `ProceduralMemory` module is used read-only for querying existing workflow history (to seed pattern detection), but learning-specific data gets its own schema. This avoids polluting the existing Procedure table while sharing the database connection pool.

### Tool Chain Tracking

To populate `FeedbackContext.tool_chain`, the `LearningService` subscribes to `tool.executed` events and collects tool names by `correlation_id` within a conversation turn. When feedback is submitted, the service resolves the tool chain for that message's correlation ID.

### Integration Points

| Component | Integration |
|-----------|-------------|
| Event Bus | Subscribe to tool/agent/scheduler events; emit learning.* events |
| SQLAlchemy Engine | New learning_* tables in existing PostgreSQL database |
| Procedural Memory | Read-only: query workflow history for pattern seeding |
| LLM Router | A/B variant assignment hook (see Section 6.2); winner promotion |
| Workflow Engine | Macro creation reuses WorkflowStep(type=TOOL) |
| Skill Runtime | Promoted skills installed via SkillRuntime.install() |
| Security Scanner | All auto-generated skills validated before install |
| Kill Switch | learning.enabled flag, respects global kill switch |
| ToolExecutor | Must emit `tool.failed` events (new) alongside existing `tool.executed` |

---

## 3. Feedback Collection

### 3.1 Two-Tier Feedback

**Quick feedback:** Thumbs up/down buttons on each agent response in chat. One tap, zero friction.

**Expanded feedback:** Tap thumb to expand → 1-5 star rating + optional text comment. Stars and comment are optional — user can leave just the thumb.

### 3.2 Data Model

```python
@dataclass(frozen=True)
class ResponseFeedback:
    id: str                          # UUID
    conversation_id: str
    message_id: str
    user_id: str
    quick_rating: int                # -1 (down), 0 (none), 1 (up)
    star_rating: int | None          # 1-5, optional
    comment: str | None
    context: FeedbackContext
    timestamp: datetime

@dataclass(frozen=True)
class FeedbackContext:
    llm_model: str                   # which model produced the response
    prompt_template: str | None      # template ID if applicable
    tool_chain: list[str]            # ordered tool names executed
    intent_category: str | None      # easy/medium/hard from router
    ab_variant_id: str | None        # if part of A/B experiment
```

### 3.3 FeedbackCollector

```python
class FeedbackCollector:
    def __init__(self, memory: ProceduralMemory, event_bus: NoblaEventBus): ...
    async def submit_feedback(self, feedback: ResponseFeedback) -> None: ...
    async def get_feedback_for_conversation(self, conversation_id: str) -> list[ResponseFeedback]: ...
    async def get_feedback_stats(self, user_id: str) -> FeedbackStats: ...
```

### 3.4 Events

- `learning.feedback.submitted` — payload: full ResponseFeedback
- `learning.feedback.positive` — quick_rating=1 or star_rating >= 4
- `learning.feedback.negative` — quick_rating=-1 or star_rating <= 2

---

## 4. Pattern Detection

### 4.1 Two-Stage Detection

**Stage 1 — Sequence Matching (always-on, cheap):**
- Subscribes to `tool.executed` events
- Maintains sliding window of tool sequences per user (configurable, default 7 days)
- Hashes tool chains: `sha256(tool1.name + ":" + sorted_param_keys + "|" + tool2.name + ...)`
- When fingerprint appears 3x within window → `PatternCandidate(status=DETECTED)`

**Stage 2 — Intent Clustering (LLM-powered, opt-in):**
- Runs when proactive level >= MODERATE or user explicitly triggers
- Queries ChromaDB for semantically similar user instructions
- LLM groups clusters: "these interactions are all 'deploy to staging'"
- Merges with sequence matches → boosts confidence → `CONFIRMED`

### 4.2 Data Model

```python
class PatternStatus(Enum):
    DETECTED = "detected"            # sequence matcher found 3+ occurrences
    CONFIRMED = "confirmed"          # intent clustering validated
    SKILL_CREATED = "skill_created"  # macro generated
    DISMISSED = "dismissed"          # user rejected

@dataclass
class PatternOccurrence:
    timestamp: datetime
    conversation_id: str
    params: dict                     # actual parameters used

@dataclass
class PatternCandidate:
    id: str                          # UUID
    user_id: str
    fingerprint: str                 # hash of tool sequence
    description: str                 # placeholder at DETECTED (joined tool names), LLM-generated at CONFIRMED
    occurrences: list[PatternOccurrence]
    tool_sequence: list[str]         # ordered tool names
    variable_params: dict[str, list] # params that changed across occurrences
    status: PatternStatus
    confidence: float                # 0.0-1.0
    detection_method: str            # "sequence" | "intent" | "merged"
    created_at: datetime
```

### 4.3 PatternDetector

```python
class PatternDetector:
    def __init__(self, memory: ProceduralMemory, event_bus: NoblaEventBus,
                 vector_store: ChromaDB | None = None): ...
    async def on_tool_executed(self, event: NoblaEvent) -> None: ...
    async def check_sequences(self, user_id: str) -> list[PatternCandidate]: ...
    async def cluster_intents(self, user_id: str) -> list[PatternCandidate]: ...
    async def dismiss_pattern(self, pattern_id: str) -> None: ...
    async def get_patterns(self, user_id: str, status: PatternStatus | None = None) -> list[PatternCandidate]: ...
```

### 4.4 Configuration

```python
@dataclass
class PatternConfig:
    sequence_window_days: int = 7        # sliding window for sequence matching
    min_occurrences: int = 3             # threshold before DETECTED
    intent_clustering_enabled: bool = False  # enabled when proactive >= MODERATE
    max_patterns_per_user: int = 50      # cap to avoid unbounded growth
```

### 4.5 Events

- `learning.pattern.detected` — sequence matcher found candidate
- `learning.pattern.confirmed` — intent clustering validated
- `learning.pattern.dismissed` — user rejected pattern

---

## 5. Auto-Skill Generation

### 5.1 Three-Tier Lifecycle

**Tier 1 — Workflow Macro (automatic):**
When a pattern reaches CONFIRMED status:
1. Extract tool sequence as `WorkflowStep(type=TOOL)` nodes
2. Identify variable parameters → macro inputs
3. LLM generates name + description
4. Create via Phase 6 Workflow engine
5. Notify user: "I noticed you do X frequently. [Review] [Dismiss]"

**Tier 2 — Promoted Skill (user-initiated):**
1. User taps "Promote to Skill" in UI
2. LLM generates `NoblaSkill` implementation from macro
3. `SkillSecurityScanner` validates generated code
4. Sandbox dry-run (10s timeout)
5. Installed via `SkillRuntime.install()` with `source=NOBLA`

**Tier 3 — Publishable (user-initiated):**
1. User marks promoted skill as "Publish-ready"
2. Adds metadata: tags, description, example usage, category
3. Packaged locally, ready for Phase 5B.2 marketplace upload

### 5.2 Data Model

```python
class MacroTier(Enum):
    MACRO = "macro"                  # workflow recording
    SKILL = "skill"                  # promoted to NoblaSkill code
    PUBLISHABLE = "publishable"      # ready for marketplace

@dataclass
class MacroParameter:
    name: str
    description: str
    type: str                        # "string" | "int" | "float" | "bool" | "path"
    default: Any | None
    examples: list[Any]              # sampled from pattern occurrences

@dataclass
class WorkflowMacro:
    id: str                          # UUID
    name: str                        # LLM-generated
    description: str                 # LLM-generated
    pattern_id: str                  # links to PatternCandidate
    workflow_id: str                 # references Phase 6 Workflow
    skill_id: str | None             # set after promotion
    parameters: list[MacroParameter]
    tier: MacroTier
    usage_count: int
    user_id: str
    created_at: datetime
    promoted_at: datetime | None
```

### 5.3 SkillGenerator

```python
class SkillGenerator:
    def __init__(self, memory: ProceduralMemory, event_bus: NoblaEventBus,
                 workflow_service: WorkflowService, skill_runtime: SkillRuntime,
                 security_scanner: SkillSecurityScanner, llm_router: LLMRouter): ...
    async def create_macro(self, pattern: PatternCandidate) -> WorkflowMacro: ...
    async def promote_to_skill(self, macro_id: str) -> SkillManifest: ...
    async def mark_publishable(self, macro_id: str, metadata: dict) -> WorkflowMacro: ...
    async def get_macros(self, user_id: str, tier: MacroTier | None = None) -> list[WorkflowMacro]: ...
    async def delete_macro(self, macro_id: str) -> None: ...
```

### 5.4 Events

- `learning.macro.created` — workflow macro auto-generated from pattern
- `learning.skill.promoted` — macro promoted to NoblaSkill
- `learning.skill.publishable` — skill marked for marketplace

---

## 6. A/B Model + Prompt Testing

### 6.1 Experiment Model

```python
class ExperimentStatus(Enum):
    RUNNING = "running"
    CONCLUDED = "concluded"
    PAUSED = "paused"

@dataclass
class ABVariant:
    id: str                          # UUID
    model: str                       # e.g., "gemini-pro", "claude-3-sonnet"
    prompt_template: str | None      # template ID, None = default
    feedback_scores: list[float]     # normalized 0.0-1.0
    sample_count: int
    win_rate: float                  # vs other variants

@dataclass
class ABExperiment:
    id: str                          # UUID
    task_category: str               # "easy" | "medium" | "hard"
    variants: list[ABVariant]
    status: ExperimentStatus
    min_samples: int                 # minimum per variant before conclusion (default 20)
    epsilon: float                   # exploration rate (default 0.2)
    created_at: datetime
    concluded_at: datetime | None
    winner_variant_id: str | None
```

### 6.2 Integration with LLM Router

The existing `LLMRouter.route()` builds candidates from a static `_PREFERENCE` dict with no per-user or per-experiment hooks. The following changes are required:

**Changes to `LLMRouter` (`backend/nobla/brain/router.py`):**
1. Add optional `ab_manager: ABTestManager | None` dependency (injected at init, defaults to None)
2. In `route()` and `stream_route()`, before building candidates: call `ab_manager.get_variant(task_category, user_id)` if ab_manager is set and an experiment is active
3. If a variant is returned, override the primary model selection with the variant's model (and prompt template if specified)
4. Tag the response metadata with `ab_variant_id` so `FeedbackContext` can capture it
5. When an experiment concludes, `ABTestManager` calls `LLMRouter.update_preference(task_category, model)` to promote the winner — a new method that updates the `_PREFERENCE` dict entry for that category

**Epsilon per category:** Use lower epsilon for expensive categories to respect cost constraints:
- EASY: epsilon=0.2 (free models, low cost to explore)
- MEDIUM: epsilon=0.15
- HARD: epsilon=0.1 (expensive models, conservative exploration)

**Flow:**
1. Router calls `ab_manager.get_variant(task_category, user_id)` → returns variant or None
2. If variant: use variant.model as primary candidate, tag response with variant.id
3. If no variant (no active experiment): use default `_PREFERENCE` routing
4. Feedback flows back via `ABTestManager.record_feedback(variant_id, score)`
5. When all variants reach `min_samples` + win rate gap > 0.1 → conclude
6. Winner → `LLMRouter.update_preference(task_category, winner.model)`

### 6.3 ABTestManager

```python
class ABTestManager:
    def __init__(self, event_bus: NoblaEventBus, db_session: AsyncSession): ...
    async def create_experiment(self, task_category: str, variants: list[dict]) -> ABExperiment: ...
    async def get_variant(self, task_category: str, user_id: str) -> ABVariant | None: ...
    async def record_feedback(self, variant_id: str, score: float) -> None: ...
    async def check_conclusion(self, experiment_id: str) -> bool: ...
    async def get_experiments(self, status: ExperimentStatus | None = None) -> list[ABExperiment]: ...
    async def pause_experiment(self, experiment_id: str) -> None: ...
```

### 6.4 Events

- `learning.ab.started` — new experiment created
- `learning.ab.concluded` — experiment concluded, winner in payload

---

## 7. Proactive Intelligence

### 7.1 Configurable Aggressiveness

```python
class ProactiveLevel(Enum):
    OFF = "off"                      # no observation, no suggestions
    CONSERVATIVE = "conservative"    # >90% confidence, max 1/day — DEFAULT
    MODERATE = "moderate"            # pattern suggestions, dismiss-to-learn, enables intent clustering
    AGGRESSIVE = "aggressive"        # briefings, anomaly alerts, routine automation offers
```

### 7.2 Suggestion Types by Level

| Level | Pattern | Optimization | Anomaly | Briefing |
|-------|---------|-------------|---------|----------|
| OFF | — | — | — | — |
| CONSERVATIVE | >90% confidence | A/B winners only | — | — |
| MODERATE | >70% confidence | A/B + tool chain | missed routines | — |
| AGGRESSIVE | >50% confidence | all optimizations | all anomalies | daily morning |

### 7.3 Data Model

```python
class SuggestionType(Enum):
    PATTERN = "pattern"              # "You do X frequently..."
    OPTIMIZATION = "optimization"    # "Switching to Model Y saves 30%..."
    ANOMALY = "anomaly"              # "Your usual backup didn't run..."
    BRIEFING = "briefing"            # "Morning summary: 3 tasks, 1 failing webhook..."

class SuggestionStatus(Enum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    DISMISSED = "dismissed"          # never show this specific suggestion again
    SNOOZED = "snoozed"             # remind after snooze_until
    EXPIRED = "expired"

@dataclass
class ProactiveSuggestion:
    id: str                          # UUID
    type: SuggestionType
    title: str
    description: str
    confidence: float                # 0.0-1.0
    action: dict | None              # executable action payload if user approves
    user_id: str
    status: SuggestionStatus
    snooze_until: datetime | None    # set when SNOOZED
    snooze_count: int                # incremented each snooze; auto-expire at 5
    expires_at: datetime | None
    created_at: datetime
    source_pattern_id: str | None    # links to PatternCandidate if type=PATTERN
```

### 7.4 Snooze vs Dismiss Semantics

**Dismiss** = "This is not useful. Never show this specific suggestion again."
- The engine records the dismissal reason category (irrelevant, wrong, annoying)
- Future suggestions of the same type with similar characteristics get a confidence penalty
- Dismissed suggestions are excluded from all future delivery

**Snooze** = "Not now, but remind me later."
- User picks snooze duration: 1 day, 3 days, 7 days, or custom
- Suggestion status → SNOOZED with `snooze_until` timestamp
- When `snooze_until` passes, suggestion re-enters PENDING and is re-delivered
- Snoozed suggestions carry **no negative signal** — the engine does not penalize the suggestion type
- If snoozed 3+ times, engine treats as soft-dismiss (reduces confidence but does not block)
- If snoozed 5+ times, suggestion auto-expires (status → EXPIRED) to prevent infinite snooze loops

**Learning impact:**

| Action | Confidence penalty for similar suggestions | Blocks future delivery | Re-delivery |
|--------|---------------------------------------------|----------------------|-------------|
| Accept | +0.1 boost | — | — |
| Dismiss | -0.2 penalty per type | Yes (this specific) | Never |
| Snooze (1-2x) | None | No | After snooze_until |
| Snooze (3-4x) | -0.05 soft penalty | No | After snooze_until |
| Snooze (5+x) | -0.05 soft penalty | Yes (auto-expired) | Never |

### 7.5 ProactiveEngine

```python
class ProactiveEngine:
    def __init__(self, memory: ProceduralMemory, event_bus: NoblaEventBus,
                 llm_router: LLMRouter, config: ProactiveConfig): ...
    async def evaluate_suggestions(self, user_id: str) -> list[ProactiveSuggestion]: ...
    async def accept_suggestion(self, suggestion_id: str) -> dict: ...
    async def dismiss_suggestion(self, suggestion_id: str, reason: str | None = None) -> None: ...
    async def snooze_suggestion(self, suggestion_id: str, days: int) -> None: ...
    async def check_snoozed(self) -> list[ProactiveSuggestion]: ...
    async def generate_briefing(self, user_id: str) -> ProactiveSuggestion | None: ...
    async def get_suggestions(self, user_id: str, status: SuggestionStatus | None = None) -> list[ProactiveSuggestion]: ...
```

### 7.6 Configuration

```python
@dataclass
class ProactiveConfig:
    level: ProactiveLevel = ProactiveLevel.CONSERVATIVE
    max_suggestions_per_day: int = 1  # conservative default
    snooze_options_days: list[int] = field(default_factory=lambda: [1, 3, 7])
    max_snooze_count: int = 3         # soft-dismiss threshold
    confidence_thresholds: dict[ProactiveLevel, float] = field(default_factory=lambda: {
        ProactiveLevel.CONSERVATIVE: 0.9,
        ProactiveLevel.MODERATE: 0.7,
        ProactiveLevel.AGGRESSIVE: 0.5,
    })
    briefing_time: str = "08:00"      # for AGGRESSIVE morning briefing
```

### 7.7 Events

- `learning.suggestion.created` — new suggestion generated
- `learning.suggestion.accepted` — user accepted
- `learning.suggestion.dismissed` — user dismissed (includes reason)
- `learning.suggestion.snoozed` — user snoozed (includes snooze_until)

---

## 8. Storage — Dedicated Learning Tables

As described in Section 2 (Storage Strategy), the existing `ProceduralMemory` stores only `Procedure` records with Bayesian scoring columns. Learning data uses **dedicated SQLAlchemy models** sharing the same PostgreSQL database and engine.

### 8.1 Database Tables

| Table | Primary Model | Key Columns |
|-------|--------------|-------------|
| `learning_feedback` | ResponseFeedback | id, user_id, conversation_id, message_id, quick_rating, star_rating, comment, context (JSONB), timestamp |
| `learning_patterns` | PatternCandidate | id, user_id, fingerprint, description, tool_sequence (ARRAY), variable_params (JSONB), status, confidence, detection_method, created_at |
| `learning_occurrences` | PatternOccurrence | id, pattern_id (FK), timestamp, conversation_id, params (JSONB) |
| `learning_macros` | WorkflowMacro | id, user_id, name, description, pattern_id, workflow_id, skill_id, parameters (JSONB), tier, usage_count, created_at, promoted_at |
| `learning_experiments` | ABExperiment | id, task_category, status, min_samples, epsilon, created_at, concluded_at, winner_variant_id |
| `learning_variants` | ABVariant | id, experiment_id (FK), model, prompt_template, feedback_scores (ARRAY), sample_count, win_rate |
| `learning_suggestions` | ProactiveSuggestion | id, user_id, type, title, description, confidence, action (JSONB), status, snooze_until, snooze_count, expires_at, created_at, source_pattern_id |

### 8.2 Migration

A single Alembic migration creates all `learning_*` tables. Indexes on: `user_id`, `status`, `fingerprint`, `created_at`. GIN index on `context` JSONB column in feedback table.

### 8.3 Procedural Memory Read-Only Usage

The `PatternDetector` queries existing `ProceduralMemory` for workflow history to seed initial pattern detection (identifying tool sequences that succeeded). This is read-only — no writes to the Procedure table.

ChromaDB is used for intent clustering (Stage 2) via the existing vector store connection.

### 8.4 LearningSettings

Added to `backend/nobla/config/settings.py`:

```python
class LearningSettings(BaseModel):
    enabled: bool = True                             # master switch, respects global kill switch
    feedback_enabled: bool = True                    # collect user feedback
    pattern_detection_enabled: bool = True           # sequence matching
    ab_testing_enabled: bool = True                  # A/B experiments
    proactive_level: str = "conservative"            # off/conservative/moderate/aggressive
    pattern_config: PatternConfig = PatternConfig()
    proactive_config: ProactiveConfig = ProactiveConfig()
```

Added as `learning: LearningSettings` field on the `Settings` class.

---

## 9. Event Contract

### 9.1 Events Emitted

| Event | Payload | Source Module |
|-------|---------|---------------|
| `learning.feedback.submitted` | ResponseFeedback | FeedbackCollector |
| `learning.feedback.positive` | ResponseFeedback | FeedbackCollector |
| `learning.feedback.negative` | ResponseFeedback | FeedbackCollector |
| `learning.pattern.detected` | PatternCandidate | PatternDetector |
| `learning.pattern.confirmed` | PatternCandidate | PatternDetector |
| `learning.pattern.dismissed` | pattern_id, user_id | PatternDetector |
| `learning.macro.created` | WorkflowMacro | SkillGenerator |
| `learning.skill.promoted` | macro_id, skill_id | SkillGenerator |
| `learning.skill.publishable` | macro_id, metadata | SkillGenerator |
| `learning.ab.started` | ABExperiment | ABTestManager |
| `learning.ab.concluded` | experiment_id, winner | ABTestManager |
| `learning.suggestion.created` | ProactiveSuggestion | ProactiveEngine |
| `learning.suggestion.accepted` | suggestion_id | ProactiveEngine |
| `learning.suggestion.dismissed` | suggestion_id, reason | ProactiveEngine |
| `learning.suggestion.snoozed` | suggestion_id, snooze_until | ProactiveEngine |

### 9.2 Events Consumed

| Event | Consumer | Purpose |
|-------|----------|---------|
| `tool.executed` | PatternDetector | Sequence matching |
| `tool.failed` | FeedbackCollector | Negative signal inference |
| `agent.a2a.task.result` | FeedbackCollector | Multi-agent feedback |
| `scheduler.task.executed` | ProactiveEngine | Routine detection / anomaly |

---

## 10. REST API

### 10.1 Feedback Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/learning/feedback` | Submit feedback |
| GET | `/api/learning/feedback?conversation_id=` | Get feedback for conversation |
| GET | `/api/learning/feedback/stats` | Get feedback statistics |

### 10.2 Pattern Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/learning/patterns` | List patterns (optional status filter) |
| GET | `/api/learning/patterns/{id}` | Get pattern detail |
| POST | `/api/learning/patterns/{id}/dismiss` | Dismiss a pattern |

### 10.3 Macro/Skill Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/learning/macros` | List macros (optional tier filter) |
| GET | `/api/learning/macros/{id}` | Get macro detail |
| POST | `/api/learning/macros/{id}/promote` | Promote macro to skill |
| POST | `/api/learning/macros/{id}/publish` | Mark skill as publishable |
| DELETE | `/api/learning/macros/{id}` | Delete a macro |

### 10.4 A/B Experiment Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/learning/experiments` | Create experiment |
| GET | `/api/learning/experiments` | List experiments |
| GET | `/api/learning/experiments/{id}` | Get experiment detail |
| POST | `/api/learning/experiments/{id}/pause` | Pause experiment |

### 10.5 Suggestion Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/learning/suggestions` | List suggestions (optional status filter) |
| POST | `/api/learning/suggestions/{id}/accept` | Accept suggestion |
| POST | `/api/learning/suggestions/{id}/dismiss` | Dismiss suggestion |
| POST | `/api/learning/suggestions/{id}/snooze` | Snooze suggestion (body: {days: int}) |

### 10.6 Settings Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/learning/settings` | Get learning settings |
| PUT | `/api/learning/settings` | Update learning settings |
| DELETE | `/api/learning/data` | Clear all learning data |

---

## 11. Flutter UI

### 11.1 Inline (Chat Screen)

- **Feedback widget**: Thumbs up/down on each response bubble. Tap to expand → 1-5 stars + optional text comment. Compact, doesn't disrupt chat flow.
- **Pattern card**: Dismissible notification card — "I noticed you do X frequently" → [Review] [Dismiss]
- **Suggestion card**: Proactive suggestion — [Accept] [Snooze ▾] [Dismiss]. Snooze shows dropdown: 1 day, 3 days, 7 days.

### 11.2 Agent Intelligence Screen

**Navigation:** The current app has 7 nav destinations. Adding an 8th would overflow Material 3's `NavigationBar` on mobile. Instead, Agent Intelligence is a **sub-route under Settings** (`/settings/intelligence`), accessible via a prominent "Agent Intelligence" list tile on the Settings screen. This avoids nav bar bloat while keeping the feature discoverable.

| Tab | Content |
|-----|---------|
| **Overview** | Feedback count (positive/negative), patterns detected, auto-skills active, A/B experiments running/concluded, proactive level badge |
| **Patterns** | Pattern list with status chips (detected/confirmed/skill_created/dismissed), tap → macro detail + promote button, swipe to dismiss |
| **Auto-Skills** | Macros + promoted skills with tier badges, usage count, publish toggle, delete action |
| **Settings** | Proactive level slider (OFF/CONSERVATIVE/MODERATE/AGGRESSIVE), A/B testing toggle, snooze defaults, clear learning data button, export data button |

### 11.3 Dart Models

Mirror all backend models: `ResponseFeedback`, `PatternCandidate`, `WorkflowMacro`, `ABExperiment`, `ProactiveSuggestion`, all enums. Riverpod providers for each data type + settings.

---

## 12. Gateway Integration

### 12.1 Lifespan Wiring (`backend/nobla/gateway/lifespan.py`)

```python
# In lifespan(), after skill_runtime init, before yield:
learning_service = LearningService(
    event_bus=event_bus,
    db_session=db_session,
    workflow_service=workflow_service,
    skill_runtime=skill_runtime,
    security_scanner=security_scanner,
    llm_router=llm_router,
    settings=settings.learning,
)
if settings.learning.enabled and not kill_switch.is_active:
    await learning_service.start()  # registers event bus subscriptions
app.state.learning_service = learning_service

# Include REST router
app.include_router(learning_router, prefix="/api/learning", tags=["learning"])

# In shutdown:
await learning_service.stop()  # unsubscribes from event bus
```

### 12.2 Kill Switch Integration

- Global kill switch active → `LearningService.start()` is skipped entirely
- `settings.learning.enabled = false` → same effect, all components disabled
- Kill switch activated at runtime → `LearningService.stop()` called, all subscriptions removed

### 12.3 Required Changes to Existing Modules

| Module | Change |
|--------|--------|
| `ToolExecutor` | Emit `tool.failed` event on tool execution failure (alongside existing `tool.executed` on success) |
| `LLMRouter` | Accept optional `ABTestManager`, add `get_variant()` call in `route()`/`stream_route()`, add `update_preference()` method |
| `Settings` | Add `learning: LearningSettings` field |

---

## 13. Security & Privacy

- All learning data is user-scoped in dedicated `learning_*` tables
- **No data leaves device** unless user explicitly marks a skill as publishable
- Kill switch: `settings.learning.enabled` master switch, respects global kill switch (see Section 12.2)
- **Disable granularity** (three independent levels):
  - `settings.learning.enabled = false` → disables ALL learning (feedback, patterns, A/B, proactive)
  - `settings.learning.proactive_level = "off"` → disables ONLY ProactiveEngine suggestions; feedback collection, pattern detection, and A/B testing continue
  - Individual toggles: `feedback_enabled`, `pattern_detection_enabled`, `ab_testing_enabled` for fine-grained control
- Auto-generated skills → `SkillSecurityScanner` validation before install
- LLM-generated code (promotion) → sandbox dry-run with 10s timeout
- Feedback data never sent to LLM providers
- Clear all learning data available via settings UI + REST API (`DELETE /api/learning/data`)
- All learning REST endpoints require authentication (existing JWT middleware)
- Note: `learning.feedback.submitted` and `learning.feedback.positive`/`negative` are intentionally dual-emitted (submitted always fires; positive or negative fires additionally based on rating)

---

## 14. Module Structure

```
backend/nobla/learning/
├── __init__.py
├── models.py              # SQLAlchemy models + dataclasses + enums (~300 lines)
├── feedback.py            # FeedbackCollector (~180 lines)
├── patterns.py            # PatternDetector — sequence match + intent cluster (~300 lines)
├── generator.py           # SkillGenerator — macro, promote, publish-prep (~250 lines)
├── ab_testing.py          # ABTestManager — experiments, epsilon-greedy (~250 lines)
├── proactive.py           # ProactiveEngine — suggest, snooze, dismiss, briefing (~300 lines)
└── service.py             # LearningService — orchestrator, wiring, settings (~180 lines)

backend/nobla/gateway/
└── learning_handlers.py   # REST API routes + schemas (~300 lines)

app/lib/features/learning/
├── models/
│   └── learning_models.dart         # Dart models + enums (~250 lines)
├── providers/
│   └── learning_providers.dart      # Riverpod providers (~180 lines)
├── screens/
│   └── agent_intelligence_screen.dart  # TabBarView with 4 tabs (~250 lines)
└── widgets/
    ├── feedback_widget.dart         # Thumbs + expandable stars (~120 lines)
    ├── pattern_card.dart            # Pattern notification card (~100 lines)
    ├── suggestion_card.dart         # Suggestion with snooze/dismiss (~120 lines)
    └── learning_stats_widget.dart   # Overview dashboard stats (~100 lines)
```

All files well under the 750-line limit. Estimated ~2,880 lines total (backend ~1,760 + Flutter ~1,120).

---

## 15. Testing Strategy

- **Unit tests**: Each module independently (feedback, patterns, generator, ab_testing, proactive)
- **Integration tests**: Event bus wiring, procedural memory round-trip, workflow engine macro creation
- **Target**: ~180-220 backend tests + ~60-80 Flutter tests
- **Security-critical paths** (skill generation, security scanning): 90%+ coverage

---

## 16. Dependencies

### Backend (new)
- `alembic` — database migration for `learning_*` tables (already a project dependency)

### Flutter (new)
None — uses existing dependencies (flutter_riverpod, dio, go_router).

### Internal
- `nobla.db` — SQLAlchemy engine + session factory (shared database)
- `nobla.memory.procedural` — read-only: query workflow history for pattern seeding
- `nobla.events.bus` — event pub/sub
- `nobla.skills.runtime` — skill installation
- `nobla.skills.security` — security scanning
- `nobla.automation.workflows.service` — macro workflow creation
- `nobla.brain.router` — A/B variant assignment + `update_preference()` (new method)
- `nobla.tools.executor` — emit `tool.failed` events (new)
- `nobla.config.settings` — `LearningSettings` (new model)
- `nobla.agents.base` — agent task feedback
