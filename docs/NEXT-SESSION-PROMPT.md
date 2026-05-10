# Session 4 — Plan

**Generated:** end of Session 3 (2026-05-09)
**Predecessor branch:** `feat/5-channels-messenger` — needs to land on `main` (PR #7) before Session 4 mission work
**Mission family:** Phase 5 — Channels (Tier 1 close-out OR cross-channel infrastructure)

## Boot

Run the standard boot string (already in CLAUDE.md Session Handoff Protocol):

```text
init_project()
check_system_health()
search_memory({ query: "Active Backlog", project_id: "nobla-agent", k: 10 })
# Then read docs/NEXT-SESSION-PROMPT.md for the full Session 4 plan.
```

## Pre-Mission Hygiene (5-10 min)

1. **Branch state.** Verify PR #7 (`feat/5-channels-messenger`) was merged into `main`. If not, finish the merge before starting any new work — Session 4 mission belongs on a fresh feature branch.
2. **Start clean branch.** From `main`: `git switch -c <branch-from-mission-pick>` (see Mission section below).
3. **Constitution check.** Confirm CLAUDE.md is at v2.1.5 with both `### The Execution Imperatives (v2.1.4)` and `### The Lean Logic (v2.1.5)` sections present. If `init_project` reports drift, abort and re-sync.

## Mission — Pick One

| Option | Cost | Branch | Notes |
|--------|------|--------|-------|
| **(A) Slack Enterprise Grid** ⭐ | ~2-3 hrs | `feat/5-channels-slack-grid` | Extension of existing `backend/nobla/channels/slack/`. Org-level features: Enterprise Grid API, cross-workspace messaging, multi-team OAuth. Closes Tier 1. |
| **(B) Cross-channel webhook dispatcher** | ~3-4 hrs | `refactor/5-channels-webhook-dispatcher` | Closes SCM-S3-D3 deferral. Single FastAPI route that resolves channel from URL slug and delegates to `channel_manager.get(slug).handle_webhook_payload(...)`. Unblocks live channel ingest end-to-end. |
| **(C) Phase 5 housekeeping** | ~1-2 hrs | `chore/5-channels-housekeeping` | Lifespan try/except graceful failure for all 7 channel inits + channel test file size audit (split slack/messenger if team agrees with SCM-S3-D2 follow-up). |

**Recommended: (A) Slack Enterprise Grid** — completes the Tier 1 channels sweep started in Session 3. Smallest surface, predictable cost, leaves Tier 2 work fully scoped.

If priorities shift toward making any channel actually receive webhooks live, pick (B). If the team wants stability before adding more channels, pick (C).

## Adapter Contract Reference (for Option A — Slack Grid extension)

The Slack base adapter already exists at `backend/nobla/channels/slack/`. Grid extension is mostly:

| Concern | Files to touch |
|---------|---------------|
| Org-level OAuth scope (`admin.users:read`, `admin.conversations:read`) | `slack/adapter.py` (token-validation block); `config/settings.py` (add `enterprise_grid: bool`, `org_token: str`, `team_ids: list[str]`) |
| Cross-workspace message routing | `slack/handlers.py` (resolve `team_id` per event, route to correct workspace) |
| Enterprise Grid `admin.*` API calls | `slack/api.py` (new helper module if needed — verify existing `slack/` shape first) |
| Tests | `backend/tests/test_slack_adapter.py` (extend) — target +30-50 tests for Grid paths |

## Constraints (from refreshed constitution)

- **750-line ceiling per file.** Hook-blocked on Writes. Existing over-ceiling files (slack=1,499 test) are grandfathered for Edits per SCM-S3-D2.
- **Production-Ready Only (v2.1.4).** ZERO placeholders. ZERO `// TODO`s. Code complete + error-handled + logged from the start.
- **Active Impact Analysis (v2.1.4).** Before any non-trivial edit: `search_memory` first to understand SYSTEM_FLOW impact. Specifically check SCM-S3-D1..D3 for Phase 5 channel context.
- **Self-Verification (v2.1.4).** Do NOT request `confirm_verification` release until tests are written, run, and green.
- **Efficiency Imperative (v2.1.5).** 10k context HARD CEILING; target 2-3k. Delegate read-heavy work via `delegate_task` per Strategic Context Policy.
- **Surgical Editing.** Match existing slack/ style exactly. No random refactoring of working channel code.

## Carryover Risks (from Sessions 1-3)

Documented but not acted on — pick up if the housekeeping window opens at session end:

- **Per-channel webhook routes** missing in `gateway/` for ALL channels (SCM-S3-D3). When picking Option (B), this is the mission.
- **Lifespan try/except graceful failure** missing for all 7 channel inits — would be a single-PR uniform refactor (Option C scope).
- **Channel test file size precedent** (SCM-S3-D2) — slack=1,499, messenger=1,583. Optional cleanup if team prefers strict 750 conformance.
- README test-count totals don't sum cleanly across phase rows (likely double-counting in the Webhooks row — flagged in Session 2 carryover).
- ARCHITECTURE.md Mermaid diagrams auto-synced but not visually verified.
- `docs/superpowers/specs/` and `docs/superpowers/plans/` referenced in README but not audited for currency.
- 6 backend tests blocked by missing `sklearn` dependency in venv (`nobla.memory.extraction`) — `pip install scikit-learn` resolves locally, but the requirements file may be missing it. Worth a 5-min audit.
- 3 pre-existing test failures unrelated to channels: `test_config.py::test_settings_provider_config` (provider chain drift), `test_tool_models.py::test_all_categories_exist` (enum drift). Worth fixing in a `chore/` PR.

## Decision Memos to Reference

- `SCM-S1-D1..D4` (Session 1) — Sovereign Purge + README sync + .gitignore for archives
- `SCM-S2-D1` (id 11481) — v2.1.5 Lean Logic sync
- `SCM-S2-D2` (id 11482) — v2.1.4 Execution Imperatives backfill
- `SCM-S3-D1` (id 11485) — Messenger Tier 1 adapter
- `SCM-S3-D2` (id 11486) — Channel test file size precedent
- `SCM-S3-D3` (id 11487) — Per-channel webhook route deferral
- `SCM-S14-D1` (id 11321, GLOBAL) — Execution Imperatives source
- `SCM-S15-D1` (id 11468, GLOBAL) — Lean Logic source

## Branding

[NABILNET.AI](https://nabilnet.ai)
