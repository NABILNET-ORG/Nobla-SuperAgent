# Session 5 — Plan

**Generated:** end of Session 4 (2026-05-11)
**Predecessor branches:**
  - `feat/5-channels-slack-grid` — MERGED to main as PR #8 (`f91e7be`)
  - `refactor/5-channels-webhook-dispatcher` — PR #9 OPEN, needs review/merge before Session 5 mission work
**Mission family:** Phase 5 — Channels (Tier 2 expansion OR foundation sweep OR housekeeping)

## Boot

Run the standard boot string:

```text
init_project()
check_system_health()
search_memory({ query: "Active Backlog", project_id: "nobla-agent", k: 10 })
# Then read docs/NEXT-SESSION-PROMPT.md for the full Session 5 plan.
```

## Pre-Mission Hygiene (5-10 min)

1. **Branch state.** Verify PR #9 (`refactor/5-channels-webhook-dispatcher`) was merged into `main`. If not, decide whether to merge first or branch from current main (slack-grid is already there, so any new work starts from a known-good base regardless).
2. **Start clean branch.** From `main`: `git switch -c <branch-from-mission-pick>` (see Mission section below).
3. **Constitution check.** Confirm `upgrade_constitution()` (NO force) returns `already_synced` — the canonical v2.1.6 byte-identical block landed at commit `e973641`. If drift, abort and resync (do NOT use `force: true` — that path is buggy per SCM-S17-D1).

## Mission — Pick One

| Option | Cost | Branch | Notes |
|--------|------|--------|-------|
| **(A) Foundation Sweep** ⭐ | ~1-2 hrs | `chore/foundation-venv-drift-sweep` | Install 4 declared-but-missing venv deps (Pillow, python-telegram-bot, openai, dateparser, faster_whisper) per Foundation First v2.1.6 isolated commits. Unblocks 38 collection errors documented in SCM-S16-D2. Enables `create_app()` to smoke-test cleanly + lets the Telegram carve-out test be replaced with a real-import assertion. Smallest path to a fully-collecting test suite. |
| **(B) Phase 5 housekeeping** | ~2-3 hrs | `chore/5-channels-housekeeping` | Lifespan try/except graceful failure for all 7 channel inits (today: any one channel failing at startup crashes the whole app). Plus optional split of the grandfathered `test_slack_adapter.py` (1,500 lines) into focused modules per the canonical 1000-Line Test Ceiling. |
| **(C) Tier 2 channel: Discord** | ~3-4 hrs | `feat/5-channels-discord` | Net-new webhook adapter implementing the v2.1.6 `dispatch_webhook` contract. Discord webhooks use Ed25519 signatures (X-Signature-Ed25519 + X-Signature-Timestamp). Smaller surface than Slack since Discord is interactions-API-only here. |

**Recommended: (A) Foundation Sweep** — closes a multi-session foundation gap with a small predictable PR, unblocks future missions, and validates the v2.1.6 Foundation First Protocol on a real instance (each install = one isolated commit). Pick (B) if the team wants production-safety hardening before any new feature. Pick (C) for Tier 2 channel growth.

## Adapter Contract Reference (for Option C — Discord)

If picking Discord, follow the dispatch_webhook contract established in SCM-S5-D1:

| Concern | Files to touch |
|---------|---------------|
| `webhook_signature_headers = ("X-Signature-Ed25519", "X-Signature-Timestamp")` + `async dispatch_webhook` | `backend/nobla/channels/discord/adapter.py` (new) |
| Settings | `backend/nobla/config/settings.py` (add `DiscordSettings` with `public_key`, `app_id`, etc.) |
| Lifespan wiring | `backend/nobla/gateway/lifespan.py` (Edit-only — file is grandfathered at 869 lines) |
| Tests | NEW `backend/tests/test_discord_adapter.py` + extend `test_channel_webhook_per_adapter.py::TestDiscordDispatchWebhook` (~9 tests) |

## Constraints (from canonical v2.1.6)

- **750-line ceiling per file.** Hook-blocked on Writes. Grandfathered files (`test_slack_adapter.py`, `lifespan.py`, `test_messenger_adapter.py`) → Edit only.
- **1000-Line Test Ceiling (Boy Scout).** New test files MUST split by behavior/component. Existing-codebase precedent is never an excuse for monolithic new tests.
- **Production-Ready Only.** ZERO placeholders. ZERO `// TODO`s.
- **Foundation First (v2.1.6).** Verification gate at mission start: do tests collect on the dependency you're extending? If no, HALT and fix in isolated commit FIRST.
- **Active Impact Analysis.** `search_memory` before non-trivial edits.
- **Efficiency.** 10k context HARD CEILING; target 2-3k.
- **No drive-by refactors.** Match existing style.
- **Surgical Editing.** Decompose substantial CLAUDE.md restructuring into Edit calls; never use Write on Core 3 files.

## Carryover Risks (from Sessions 1-4)

- **Pre-existing venv-drift (SCM-S16-D2):** Pillow, python-telegram-bot, openai, dateparser, faster_whisper missing. 38 collection errors. Mission Option A directly addresses this.
- **Channel test file size precedent (SCM-S3-D2 + canonical 1000-line ceiling):** `test_slack_adapter.py` (1,500) and `test_messenger_adapter.py` (1,583) still grandfathered. Cleanup is Option B scope.
- **`upgrade_constitution({ force: true })` is buggy** (SCM-S17-D1) — version-string match short-circuits the hash check. Use the no-force path for drift detection; for actual rewrites use surgical Edit OR live with the bug until SCM-side fix.
- **`create_app()` cannot smoke-test at module load** until Pillow is installed (Option A unblocks).
- **README + ARCHITECTURE.md auto-synced** by manage_backlog session_end but not visually verified this session.

## Decision Memos to Reference

- `SCM-S3-D1` (id 11485) — Messenger Tier 1 adapter
- `SCM-S3-D2` (id 11486) — Channel test file size precedent (grandfathering)
- `SCM-S3-D3` (id 11487) — Per-channel webhook route deferral (CLOSED in Mission B)
- `SCM-S4-D1-RETRACTED` (id 11500) — Constitutional warning (Boy Scout test ceiling principle)
- `SCM-S4-D2` (id 11501) — Mission A (Slack Enterprise Grid) post-mortem
- `SCM-S16-D1` (id 11492) — Initial v2.1.6 hand-built sync (superseded)
- `SCM-S16-D2` (id 11493) — Foundation Fixes + venv-drift carryover
- `SCM-S17-D1` (id 11502) — Canonical v2.1.6 block-hash sync + upgrade_constitution force-path bug
- `SCM-S5-D1` (id 11504) — Mission B (webhook dispatcher) post-mortem
- `SCM-S14-D1` (id 11321, GLOBAL) — Execution Imperatives source
- `SCM-S15-D1` (id 11468, GLOBAL) — Lean Logic source
- `PATTERN-FOUNDATION-FIRST-GLOBAL` (id 11491, GLOBAL) — Foundation First source

## Branding

[NABILNET.AI](https://nabilnet.ai)
