# Continuation Prompt — After Phase 5A + Phase 6 NL Scheduler

**Paste this into a new Claude Code session to continue development.**

---

## Context

Nobla Agent is at commit `765ee4f` on `main`. **344 tests passing.**

### What was just completed:

**Phase 5A — Telegram + Discord adapters (173 tests):**
- `backend/nobla/channels/telegram/` — Full Telegram bot: polling + webhook modes, MarkdownV2 formatter, media handler (upload/download), /start /link /unlink /status commands, group mention-only activation, inline keyboard for tool approvals, callback query handling, event bus integration. 95 tests.
- `backend/nobla/channels/discord/` — Full Discord bot: persistent WebSocket gateway via discord.py, discord.ui.Button views, media handler, !start !link !unlink !status prefix commands, guild mention-only activation, interaction handling, configurable command prefix. 78 tests.
- Both adapters implement `BaseChannelAdapter` (in `backend/nobla/channels/base.py`), integrate with `ChannelManager`, `UserLinkingService` (pairing codes), `ChannelConnectionState` bridge, and emit events on `NoblaEventBus`.
- Gateway wiring in `backend/nobla/gateway/app.py` — conditional initialization based on `settings.telegram.enabled` / `settings.discord.enabled`.

**Phase 6 — NL Scheduled Tasks (76 tests):**
- `backend/nobla/automation/` — Complete NL scheduling engine:
  - `models.py` — ScheduledTask, ParsedSchedule, TaskInterpretation, ConfirmationRequest, TaskStatus enum
  - `parser.py` — NLP time parser using dateparser (absolute times) + recurrent (recurring patterns), RRULE→cron conversion, human-readable descriptions, next-run preview
  - `interpreter.py` — LLM task interpreter that separates time from task via LLMRouter, with heuristic fallback when LLM unavailable
  - `scheduler.py` — APScheduler AsyncIOScheduler wrapper: add/remove/pause/resume tasks, job execution callback, event emission
  - `confirmation.py` — Async confirmation flow: builds ConfirmationRequest, emits event, waits for user approve/deny with timeout
  - `service.py` — Orchestrator: interpret → parse → confirm → schedule pipeline, task limits per user, ownership checks
- Gateway wiring in `app.py` — SchedulerService initialized with LLMRouter + ToolRegistry + EventBus, started/stopped in lifespan.

### Architecture decisions to preserve:
- Channel adapters use lazy `__init__.py` imports to avoid hard dependency on `python-telegram-bot` / `discord.py`
- APScheduler 3.x `shutdown()` doesn't reset `running` flag in asyncio — we track `_running` state manually in `NoblaScheduler`
- Confirmation flow uses `asyncio.Future` per task, resolved by `respond(task_id, approved)` — event-driven, not polling
- All scheduler events use `source="scheduler"` and `event_type="scheduler.*"` pattern

### What to build next (pick one):

1. **Phase 5 — More channel adapters** (WhatsApp, Slack, Signal, Teams, etc.)
   - Same pattern as Telegram/Discord: implement `BaseChannelAdapter`, create handlers, formatter, media handler
   - 15 platforms remaining in Plan.md

2. **Phase 6 — Webhooks** (receive and process external events)
   - REST endpoint for incoming webhooks
   - Event mapping: webhook → NoblaEvent on bus
   - User-configurable webhook routes

3. **Phase 6 — Workflow Builder** (multi-step workflows in natural language)
   - "When X happens, do Y then Z"
   - IFTTT-style trigger engine
   - Workflow persistence and execution

4. **Phase 4E — Flutter Tool UI** (design spec ready at `docs/superpowers/specs/`)
   - Screen mirror, activity feed, tool browser
   - 12-task implementation plan already written

5. **Phase 6 — Multi-Agent System** (agent cloning, A2A protocol, MCP)
   - Agent orchestrator
   - Sub-agent spawning
   - MCP client/server integration

### Test commands:
```bash
# Run all tests (344 should pass)
cd backend && pytest tests/test_telegram.py tests/test_discord_adapter.py tests/test_scheduler.py tests/test_channels.py tests/test_event_bus.py tests/test_skills.py -v

# Run specific component
pytest tests/test_telegram.py -v          # 95 tests
pytest tests/test_discord_adapter.py -v   # 78 tests
pytest tests/test_scheduler.py -v         # 76 tests
```

### Key files to read first:
- `CLAUDE.md` — Full project guide with all phase status
- `Plan.md` — Roadmap with checkmarks showing completed items
- `backend/nobla/channels/base.py` — BaseChannelAdapter interface
- `backend/nobla/automation/service.py` — Scheduler service orchestrator
- `backend/nobla/events/bus.py` — Event bus (central nervous system)
