# Session 3 — Plan

**Generated:** end of Session 2 (2026-05-08)
**Predecessor branch:** `docs/add-architecture-md` — needs to land on `main` before Session 3 mission work
**Mission family:** Phase 5 — Channels (Tier 1 adapters)

## Boot

Run the standard boot string (already in CLAUDE.md Session Handoff Protocol):

```text
init_project()
check_system_health()
search_memory({ query: "Active Backlog", project_id: "nobla-agent", k: 10 })
# Then read docs/NEXT-SESSION-PROMPT.md for the full Session 3 plan.
```

## Pre-Mission Hygiene (5-10 min)

1. **Branch state.** Verify `docs/add-architecture-md` was merged into `main`. If not, finish the merge before starting any new work — Session 3 mission belongs on a fresh feature branch.
2. **Start clean branch.** From `main`: `git switch -c feat/5-channels-messenger` (or `feat/5-channels-slack-grid` depending on pick below).
3. **Constitution check.** Confirm CLAUDE.md is at v2.1.5 with both `### The Execution Imperatives (v2.1.4)` and `### The Lean Logic (v2.1.5)` sections present. If `init_project` reports drift, abort and re-sync.

## Mission — Pick One Tier 1 Adapter

| Option | Cost | Pattern reference | Notes |
|---|---|---|---|
| **(A) Facebook Messenger** | ~3-5 hrs | `backend/nobla/channels/whatsapp/` (HMAC + webhook-only) | Greenfield. Send/Receive API, X-Hub-Signature-256, message templates, quick replies, persistent menu. ~75-100 tests target. |
| **(B) Slack Enterprise Grid** | ~2-3 hrs | `backend/nobla/channels/slack/` (extension, not greenfield) | Smaller surface. Org-level features: Enterprise Grid API, cross-workspace messaging. |

**Recommended: (A) Messenger** — closes a Tier 1 platform with broader reach; greenfield gives a clean reference for the Tier 2 adapters that follow.

If session token budget is tight at start, pick **(B)** instead.

## Adapter Contract (6 files per channel)

Under `backend/nobla/channels/<name>/`:

| File | Purpose |
|------|---------|
| `__init__.py` | Lazy import wrapper (`__getattr__`) |
| `models.py` | `<Name>UserContext` dataclass + API constants |
| `formatter.py` | Platform formatting → `format_response()` returning `list[FormattedMessage]` |
| `media.py` | Platform media upload/download → unified `Attachment` |
| `handlers.py` | `<Name>Handlers` — `set_send_fn()` wiring, message routing, commands, linking, event bus emission |
| `adapter.py` | `<Name>Adapter(BaseChannelAdapter)` — 7 ABC methods: name, start, stop, send, send_notification, parse_callback, health_check |

Plus:
- Add `<Name>Settings` to `backend/nobla/config/settings.py` (with `@model_validator` for required fields when enabled)
- Add init block to `backend/nobla/gateway/lifespan.py` → `_init_channels()` (with `try/except` for graceful failure)
- Create `backend/tests/test_<name>_adapter.py` (~75-100 tests)

## Constraints (from refreshed constitution)

- **750-line ceiling per file.** Hook-blocked.
- **Production-Ready Only (v2.1.4).** ZERO placeholders. ZERO `// TODO`s. Code complete + error-handled + logged from the start.
- **Active Impact Analysis (v2.1.4).** Before any non-trivial edit: `search_memory` first to understand SYSTEM_FLOW impact.
- **Self-Verification (v2.1.4).** Do NOT request `confirm_verification` release until tests are written, run, and green.
- **Efficiency Imperative (v2.1.5).** 10k context HARD CEILING; target 2-3k. Delegate read-heavy work via `delegate_task` per Strategic Context Policy.

## Carryover Risks (from Sessions 1-2)

Low priority — pick up if the housekeeping window opens at session end:
- README test-count totals don't sum cleanly across phase rows (likely double-counting in the Webhooks row).
- ARCHITECTURE.md Mermaid diagrams auto-synced but not visually verified.
- `docs/superpowers/specs/` and `docs/superpowers/plans/` referenced in README but not audited for currency.
- No automated detection of constitution-version drift between local CLAUDE.md and latest GLOBAL `SCM-S<N>` DECISION rows. Worth proposing as an `init_project` enhancement.

## Decision Memos to Reference

- `SCM-S1-D1..D4` (Session 1) — Sovereign Purge + README sync + .gitignore for archives
- `SCM-S2-D1` (id 11481) — v2.1.5 Lean Logic sync
- `SCM-S2-D2` (id 11482) — v2.1.4 Execution Imperatives backfill
- `SCM-S14-D1` (id 11321, GLOBAL) — Execution Imperatives source
- `SCM-S15-D1` (id 11468, GLOBAL) — Lean Logic source

## Branding

[NABILNET.AI](https://nabilnet.ai)
