# Continuation Prompt — After Phase 5B.1 Self-Improving Agent

**Paste this into a new Claude Code session to continue development.**

---

## Context

Nobla Agent is on `main`. **1,192 tests passing (241 Flutter + 951 backend).**

### What was just completed:

**Phase 5B.1 — Self-Improving Agent (12 tasks, all complete):**

**Backend (106 tests):**
1. **Models + enums** (`learning/models.py`): PatternStatus, MacroTier, ExperimentStatus, SuggestionType, SuggestionStatus, ProactiveLevel, FeedbackContext, ResponseFeedback (is_positive/is_negative), PatternCandidate, WorkflowMacro, ABExperiment, ProactiveSuggestion, PatternConfig, ProactiveConfig. LearningSettings added to config.
2. **FeedbackCollector** (`learning/feedback.py`): Two-tier feedback (thumbs + expandable stars/comments), tool chain tracking by correlation_id, event emission (submitted + positive/negative).
3. **PatternDetector** (`learning/patterns.py`): SHA-256 sequence fingerprinting, configurable threshold (3x), variable param extraction, max patterns per user cap, dismiss flow.
4. **SkillGenerator** (`learning/generator.py`): 3-tier lifecycle (macro → skill → publishable), workflow engine integration, security scanner gate on promotion, LLM code generation.
5. **ABTestManager** (`learning/ab_testing.py`): Epsilon-greedy variant assignment, per-category epsilon (hard=0.1, medium=0.15, easy=0.2), auto-conclusion on win rate gap > 0.1.
6. **LLM Router A/B hook** (`brain/router.py`): update_preference(), get_preference() methods, ab_manager optional dependency.
7. **ProactiveEngine** (`learning/proactive.py`): Configurable aggressiveness (OFF/CONSERVATIVE/MODERATE/AGGRESSIVE), snooze (1/3/7 days) vs dismiss, auto-expire at 5x, confidence penalties (+0.1 accept, -0.2 dismiss, -0.05 soft), daily limit, briefing generation.
8. **LearningService** (`learning/service.py`) + **REST API** (`gateway/learning_handlers.py`, 22 routes) + **Gateway wiring** (lifespan.py): Full orchestrator, event bus subscriptions, kill switch integration.

**Flutter (24 tests):**
9. **Models** (`learning/models/learning_models.dart`): Dart mirrors of all backend models with fromJson/toJson.
10. **Providers** (`learning/providers/learning_providers.dart`): 6 Riverpod providers (placeholder).
11. **Widgets**: FeedbackWidget (thumbs + stars), PatternCard (status chip + review/dismiss), SuggestionCard (accept/snooze dropdown/dismiss), LearningStatsWidget.
12. **AgentIntelligenceScreen**: 4-tab screen (Overview/Patterns/Auto-Skills/Settings), sub-route under Settings (/home/settings/intelligence).

### Architecture decisions to preserve:
- **In-memory storage** — All learning modules use dict-based stores (SQLAlchemy deferred to future task)
- **Dual event emission** — feedback.submitted always fires; positive/negative fires additionally based on rating
- **Subscription cleanup** — Store (event_type, handler) tuples, not subscription IDs (bus.subscribe returns None)
- **Snooze vs dismiss** — Distinct semantics: dismiss = permanent block + penalty; snooze = temporary + no penalty (until 3x)
- **ProactiveLevel.OFF** — Only disables ProactiveEngine; feedback/patterns/A/B continue
- **Agent Intelligence** — Sub-route under Settings (not 8th nav destination) to avoid NavigationBar overflow

### What to do next:

**Phase 5B.2: Universal Skills Marketplace**
- Spec: `docs/superpowers/specs/2026-03-29-skills-marketplace-design.md`
- Plan: `docs/superpowers/plans/2026-03-29-skills-marketplace.md`
- 10 tasks, ~124 new tests estimated

### Test commands:
```bash
# All backend learning tests (106 tests)
cd backend && pytest tests/test_learning_*.py -v

# All Flutter learning tests (24 tests)
cd app && flutter test test/features/learning/

# Full backend suite
cd backend && pytest tests/ -v --ignore=tests/test_chat_flow.py --ignore=tests/test_consolidation.py --ignore=tests/test_extraction.py --ignore=tests/test_orchestrator.py --ignore=tests/test_routes.py --ignore=tests/test_security_integration.py --ignore=tests/test_websocket.py

# Full Flutter suite
cd app && flutter test
```

### Key files to read first:
- `CLAUDE.md` — Full project guide
- `docs/superpowers/specs/2026-03-29-skills-marketplace-design.md` — Marketplace design spec
- `docs/superpowers/plans/2026-03-29-skills-marketplace.md` — Implementation plan
- `backend/nobla/learning/service.py` — LearningService (pattern for MarketplaceService)
- `backend/nobla/skills/runtime.py` — SkillRuntime (install/upgrade target)
- `backend/nobla/skills/security.py` — SkillSecurityScanner (publish pipeline gate)
- `backend/nobla/gateway/lifespan.py` — Service wiring pattern
