# Continuation Prompt — After Phase 6 Templates + Import/Export

**Paste this into a new Claude Code session to continue development.**

---

## Context

Nobla Agent is on `main`. **1062 tests passing (217 Flutter + 845 backend).**

### What was just completed:

**Phase 6 — Templates + Import/Export (12 tasks, all complete):**

**Backend Template Models (86 tests):**
1. **Template models** (`automation/workflows/templates.py`): TemplateCategory enum (8 categories), TemplateStep (portable, ref_id-based), TemplateTrigger (portable), WorkflowTemplate (versioned, with metadata), WorkflowExportData (envelope with `$nobla_version` schema versioning, JSON serialization). Conversion helpers: `workflow_step_to_template_step()` (UUID→ref_id mapping with dedup), `workflow_trigger_to_template_trigger()`.
2. **Template registry** (`automation/workflows/template_registry.py`): TemplateRegistry with CRUD, search by query/category/tags (AND logic), `list_categories()` with counts. 5 bundled templates: GitHub CI Notifier (CI/CD), Scheduled Backup (DevOps), Webhook Relay (Integration), Approval Chain (Approval), Data Pipeline (Data Pipeline).
3. **Export service** (`automation/workflows/service.py`): `export_workflow()` — builds UUID→ref_id map with dedup, strips runtime IDs, includes optional metadata. `import_workflow()` — validates, assigns fresh UUIDs, remaps depends_on, hydrates triggers with ConditionOperator parsing. `instantiate_template()` — convenience wrapper.
4. **REST API** (`gateway/template_handlers.py`): 6 routes — `GET /api/templates` (search/filter), `GET /api/templates/categories`, `GET /api/templates/{id}`, `POST /api/templates/{id}/instantiate`, `GET /api/workflows/{id}/export`, `POST /api/workflows/import`.
5. **Gateway wiring** (`gateway/lifespan.py`): TemplateRegistry + router registered after workflow system, bundled templates auto-loaded.

**Flutter UI (50 tests):**
6. **Dart models** (`models/template_models.dart`): TemplateCategory (with value/label/icon), TemplateStep, TemplateTrigger, WorkflowTemplate, WorkflowTemplateDetail, WorkflowExportData, CategoryInfo — all with `fromJson()`.
7. **Providers** (`providers/template_providers.dart`): templateListProvider (family with TemplateFilter), templateDetailProvider, templateCategoriesProvider, workflowExportProvider, TemplateOperationsNotifier (instantiate, importFromJson).
8. **Template gallery** (`screens/template_gallery_screen.dart`): Search bar, category filter chips, template cards (icon, name, description, tags, step/trigger counts, Built-in badge, Use button), instantiate dialog, detail bottom sheet.
9. **Import/Export UI** (`screens/workflow_import_screen.dart`): WorkflowImportScreen (paste JSON, live preview, validation errors, name override, import button), WorkflowExportSheet (formatted JSON display, copy to clipboard).

### Architecture decisions to preserve:
- **Portable format**: TemplateStep uses `ref_id` (short, human-readable) instead of UUIDs — converted on export/import
- **Schema versioning**: `$nobla_version` field in export envelope — major version check on import for forward compatibility
- **Bundled templates**: Fixed IDs (`bundled-*`), cannot be deleted, loaded on registry init
- **Ref_id dedup**: Export handles duplicate step names by appending `_2`, `_3`, etc.
- **Enum parsing helpers**: Module-level `_parse_step_type()`, `_parse_error_handling()`, `_parse_condition_operator()` with graceful fallbacks
- **TemplateFilter equality**: Used as Riverpod family key for proper caching

### Module structure (new files):
```
backend/nobla/automation/workflows/
├── templates.py           # TemplateCategory, TemplateStep, TemplateTrigger, WorkflowTemplate, WorkflowExportData
└── template_registry.py   # TemplateRegistry — CRUD, search, 5 bundled templates

backend/nobla/gateway/
└── template_handlers.py   # 6 REST routes + schemas

backend/tests/
└── test_templates.py      # 86 tests

app/lib/features/automation/
├── models/
│   └── template_models.dart  # Dart models + enums
├── providers/
│   └── template_providers.dart  # Riverpod providers + StateNotifier
└── screens/
    ├── template_gallery_screen.dart  # Gallery + detail sheet
    └── workflow_import_screen.dart   # Import screen + export sheet

app/test/features/automation/
├── template_models_test.dart   # 28 tests
└── template_screens_test.dart  # 22 tests
```

### What to do next — choose one:

**Option A: Phase 5 — Remaining channel adapters (WhatsApp, Slack, Signal, Teams, etc.)**
- 15 platform adapters following the Telegram/Discord pattern

**Option B: Phase 7 — Full Feature Set**
- Media, finance, health, social, smart home tools

**Option C: MCP marketplace**
- Discover and install MCP servers
- Community MCP server registry

**Option D: Template marketplace / community sharing**
- User-submitted templates with ratings
- Template versioning and updates
- Template categories expansion

### Test commands:
```bash
# Run all Flutter tests (217 tests)
cd app && flutter test

# Run all backend tests (845 tests)
cd backend && pytest tests/ -v --ignore=tests/test_chat_flow.py --ignore=tests/test_consolidation.py --ignore=tests/test_extraction.py --ignore=tests/test_orchestrator.py --ignore=tests/test_routes.py --ignore=tests/test_security_integration.py --ignore=tests/test_websocket.py

# Run template tests only (86 tests)
cd backend && pytest tests/test_templates.py -v

# Run workflow + template tests (234 tests)
cd backend && pytest tests/test_workflows.py tests/test_workflows_service.py tests/test_templates.py -v

# Run Flutter automation tests (132 tests)
cd app && flutter test test/features/automation/

# Verify line counts (750-line limit)
find backend/nobla/automation/workflows -name "*.py" -exec wc -l {} + | sort -rn
```

### Key files to read first:
- `CLAUDE.md` — Full project guide with all phase status
- `backend/nobla/automation/workflows/templates.py` — Template models + export format
- `backend/nobla/automation/workflows/template_registry.py` — Registry + bundled templates
- `backend/nobla/automation/workflows/service.py` — Export/import/instantiate methods
- `backend/nobla/gateway/template_handlers.py` — REST API
- `app/lib/features/automation/screens/template_gallery_screen.dart` — Gallery UI
- `app/lib/features/automation/screens/workflow_import_screen.dart` — Import/export UI
