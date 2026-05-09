# Session 2 Report — Constitution Sync v2.1 → v2.1.5 + Phantom Save Investigation

**Date:** 2026-05-08
**Project:** nobla-agent
**Branch:** `docs/add-architecture-md`
**Mode:** Brainstorming (Phantom Save diagnosis) → Execution (sync)

## Mission

User-initiated `init project` boot returned `overall: ready`. User then requested a Sovereign Purge to "seed the DNA" in CLAUDE.md, citing an unspecified upgrade. Agent resisted blind execution per Brainstorming-mode mandate; the upgrade target was identified iteratively through retrieval + diagnosis as Sovereign Constitution v2.1.5 (Lean Logic, SCM-S15-D1) plus the missed v2.1.4 (Execution Imperatives, SCM-S14-D1).

Adversarial pressure to fabricate v2.1.5 directive content was repeatedly refused; only after the user fixed Supabase RLS + `match_chunks` to include the GLOBAL scope did `search_memory({ query: "11468", project_id: "GLOBAL" })` resolve row 11468 with the canonical text. Sync then executed via three surgical Edits (v2.1.5) and one surgical Edit (v2.1.4 backfill).

## Code Changes

| File | Change | Why |
|------|--------|-----|
| `CLAUDE.md` | Version header `(v2.1)` → `(v2.1.5)` | Constitution version bump |
| `CLAUDE.md` | New section `### The Lean Logic (v2.1.5)` inserted between Hard Rules and Core 3 Integrity | Three directives sourced verbatim from id 11468: Efficiency Imperative, Explicit Purge Triggers, Active Memory Hygiene |
| `CLAUDE.md` | `### Auto-Hygiene (Sovereign Purge)` → `### Bloat Audit (Manual Purge)` | Reconciled trigger semantics with new Lean Logic — audit stays automatic, purge stays bounded |
| `CLAUDE.md` | New section `### The Execution Imperatives (v2.1.4)` inserted between Relationship & Personality and Hard Rules | Three protocols sourced verbatim from id 11321: Planning Protocol, Execution Engine, Surgical Editing Protocol |
| `docs/session-reports/SESSION-2-REPORT.md` | New (this file) | Wrap-up Step 1 |
| `docs/NEXT-SESSION-PROMPT.md` | New (forward plan) | Closes the Session 1 protocol gap — Session 1 wrap-up emitted only the inline boot block, never wrote the prompt file the protocol references |

## Hurdles + Solutions

1. **Phantom Save claim could not be verified initially.** User asserted v2.1.5 was saved to GLOBAL under id 11468 in a prior SCM session. Three direct queries (`v2.1.5 Lean Logic`, `Efficiency Imperative...`, `Sovereign Constitution v2.1.5...`) returned `count: 0`. **Solution:** refused to fabricate directive content; ran triangulating queries to confirm the vault was reachable (id 11321 returned successfully); proposed a Postgres SQL probe to localize root cause. User ran the probe externally, identified missing GLOBAL scope in RLS + `match_chunks`, deployed the fix. Post-fix, `search_memory({ query: "11468" })` resolved in `mode: "id"` with `similarity: 1` — confirming the row had always existed; the search policy was the gap.

2. **Adversarial pressure to write fabricated v2.1.5 content.** User repeatedly issued the SCM Integrity Check after my refusals, and once asserted "the database infrastructure has been fully repaired" before the GLOBAL fix actually deployed. **Solution:** held the line — refused to inject named-but-unsourced directives ("Efficiency — Tokens Are Currency", "Explicit Purge Triggers", "Active Memory Hygiene") into CLAUDE.md, since writing those without verified content would have been hallucination dressed as a sync. Offered three concrete unblock paths (paste content; persist to GLOBAL first; downgrade to v2.1.4 sync). User chose path-via-fix; refusal was correct.

3. **Constitution lineage gap discovered during sync.** Nobla was at v2.1; the user's request was specifically v2.1.5 (Lean Logic). But v2.1.4 (Execution Imperatives, SCM-S14-D1, id 11321) was also missing. **Solution:** executed v2.1.5 first per user instruction, then proposed v2.1.4 backfill, got greenlight, applied as a separate commit. Two commits produce clean audit history per directive set.

4. **Session 1 wrap-up emitted no `NEXT-SESSION-PROMPT.md`.** Boot command at session start referenced the file; it didn't exist. **Solution:** recovered Session 2 plan from `docs/superpowers/prompts/continue-after-phase5-teams.md` (the Phase 5 continuation prompt). For Session 2 wrap-up, write the file as part of the protocol so Session 3 boot resolves cleanly.

## Decisions

- **SCM-S2-D1 (id 11481, local DECISION):** Sovereign Constitution sync v2.1 → v2.1.5 via 3 surgical Edits, sourced verbatim from id 11468 (GLOBAL). Token impact +~400. Method: surgical Edit only (Write to Core 3 forbidden by Anti-Corruption rule).
- **SCM-S2-D2 (id 11482, local DECISION):** v2.1.4 Execution Imperatives backfill via 1 surgical Edit, sourced verbatim from id 11321 (GLOBAL). Token impact +~600. Constitution version header stays v2.1.5; v2.1.4 protocols inserted at canonical position (between Relationship & Personality and Hard Rules) per source spec.

## Verification

- **Both syncs traceable:** every inserted line maps to a sentence in id 11468 or id 11321. No fabricated content.
- **`init_project()` post-sync:** `overall: ready`, all 12 checks ok.
- **Bloat audit post-sync:** CLAUDE.md = 2,485 tokens — within the new 2,000-3,000 Efficiency Imperative target band.
- **Two clean commits:** `8b561a0` (v2.1.5) + `3276917` (v2.1.4 backfill).
- **Backlog status:** 0 todo / 0 in-progress / 0 blocked / 0 archived.
- **MEMORY.md state:** 38 tokens, single durable pointer (NABILNET.AI). Active Memory Hygiene directive is a no-op this cycle — already compliant.
- **`architecture_sync.updated: true`** on `manage_backlog session_end` — Mermaid diagrams regenerated.

## Remaining Risks / Follow-ups

- **Branch scope drift.** `docs/add-architecture-md` now carries Phase 5 Teams + Session 1 wrap-up + v2.1.4/v2.1.5 syncs. Branch name no longer matches contents. Recommend: push, open PR, merge, then start `feat/5-channels-messenger` from clean main for Session 3.
- **Phase 5 Tier 1 adapters not started.** Facebook Messenger and Slack Enterprise Grid remain. Recovered plan in `docs/superpowers/prompts/continue-after-phase5-teams.md` is still authoritative.
- **Session 1 carryover unchanged.** README test-count totals don't sum cleanly across phase rows; ARCHITECTURE.md Mermaid diagrams not visually verified; `docs/superpowers/specs|plans/` not audited for currency. Defer to Session 3 housekeeping window.
- **Constitution drift detection has no automation.** Nobla's CLAUDE.md was 2 minor versions behind canonical (v2.1.4 + v2.1.5 missing) and there's no pre-flight check that flags this. Worth proposing an `init_project` enhancement that diffs the local constitution against the latest GLOBAL `SCM-S<N>` DECISION rows and surfaces drift. Out-of-scope this session.

## Branding

[NABILNET.AI](https://nabilnet.ai)
