# Phase 5B.2: Universal Skills Marketplace — Design Spec

**Date:** 2026-03-29
**Status:** Approved
**Author:** Nobla Agent Team
**Depends on:** Phase 5-Foundation (Skill Runtime, Universal Adapter, Security Scanner), Phase 5B.1 (Learning — PatternDetector for recommendations)

---

## 1. Overview

The Universal Skills Marketplace adds discovery, publishing, versioning, ratings, and a Flutter browse UI on top of the existing skill runtime. It is embedded in the gateway (same pattern as learning/webhooks/workflows) — no separate service.

### Goals

- Publish skills in dual format: `.nobla` archive packages (Nobla-native) and manifest-pointers (MCP, OpenClaw, Claude, LangChain)
- Tiered trust: auto-approve community skills after security scan, manual review for verified badge
- Discover skills via category/keyword (PostgreSQL) and natural-language semantic search (ChromaDB)
- Recommend skills based on user patterns (Phase 5B.1) and semantic similarity to installed skills
- SemVer versioning with update notifications (user approves before upgrade)
- Star ratings + usage stats + security scan badge
- Flutter marketplace screen under Tools tab

### Non-Goals

- Payment/revenue model (deferred)
- Hosted marketplace service (everything runs local in gateway)
- Skill sandboxing beyond existing `SkillSecurityScanner` + `SkillRuntime` pipeline
- Cross-instance skill sharing (no federation)

---

## 2. Architecture

```
Gateway (FastAPI)
    │
    ├── MarketplaceRegistry ──→ PostgreSQL (marketplace_* tables)
    │   ├── Publish pipeline (validate → scan → auto-approve / queue verified)
    │   ├── Versioning (SemVer + update checks)
    │   └── Ratings + reviews
    │
    ├── SkillDiscovery ───→ PostgreSQL (keyword/category FTS) + ChromaDB (semantic)
    │   ├── Structured search (category, tags, tier, format, sort)
    │   ├── Semantic NL search ("find a skill that manages Docker")
    │   ├── Pattern-based recommendations (from Phase 5B.1 PatternDetector)
    │   └── Similar-to-installed recommendations (ChromaDB cosine similarity)
    │
    ├── SkillPackager ────→ .nobla zip archives + manifest-pointer validation
    │
    ├── UsageTracker ─────→ Event bus (tool.executed/failed → success rates)
    │
    └── MarketplaceService (orchestrator) → REST API (14 routes)
         └── Flutter Tools tab → "Browse Marketplace" sub-screen
```

### Integration Points

| Component | Integration |
|-----------|-------------|
| SkillRuntime | Install/upgrade/uninstall (existing Phase 5-Foundation) |
| UniversalSkillAdapter | Multi-format detection at install (MCP, OpenClaw, Claude, LangChain, Nobla) |
| SkillSecurityScanner | Automated scan on every publish/version |
| Event Bus | Emit marketplace.* events; consume tool.executed/failed + skill.* for stats |
| ChromaDB | Semantic embeddings for NL search + similar-skill recommendations |
| PatternDetector (5B.1) | Pattern-based recommendations (user's repeated tool sequences → matching skills) |
| PostgreSQL | Dedicated marketplace_* tables (same DB, shared engine) |
| ToolExecutor | Extended to include `skill_id` in tool.executed/failed payloads for SkillToolBridge tools |

### Prerequisite Fix: Event Bus Subscription API

The existing `NoblaEventBus.subscribe()` returns `None` and `unsubscribe()` takes `(event_type, handler)` — not a subscription ID. The `LearningService` and `UsageTracker` both need to store `(event_type, handler)` tuples for cleanup rather than subscription IDs. All new services in this phase use `(event_type, handler)` tuple storage for unsubscription.

### Prerequisite Fix: ToolExecutor Payload

The existing `ToolExecutor._emit_tool_event()` payload lacks `skill_id`. For `SkillToolBridge` instances, the payload must include `skill_id = tool.manifest.id` so `UsageTracker` can correlate tool executions to marketplace skills. This is a one-line change: add `"skill_id": getattr(tool, 'skill_id', None)` to the payload dict.

---

## 3. Skill Package Format (Dual Mode)

### 3.1 Archive Packages (`.nobla` zip)

For Nobla-native skills:

```
my-skill.nobla (zip archive)
├── nobla-skill.json          # manifest
├── skill.py                  # NoblaSkill implementation
├── requirements.txt          # optional Python dependencies
├── README.md                 # optional documentation
└── assets/                   # optional static assets
```

### 3.2 Manifest-Pointer

For external skills (MCP servers, OpenClaw, etc.):

```json
{
  "name": "github-mcp",
  "version": "1.0.0",
  "source": "mcp",
  "source_url": "npx @modelcontextprotocol/server-github",
  "transport": "stdio",
  "description": "GitHub integration via MCP",
  "category": "productivity",
  "tags": ["github", "git", "code-review"]
}
```

### 3.3 SkillPackager

```python
class SkillPackager:
    def __init__(self): ...
    def validate_archive(self, archive_path: Path) -> PackageValidation: ...
    def validate_manifest(self, manifest: dict) -> PackageValidation: ...
    def extract_manifest(self, archive_path: Path) -> dict: ...
    def compute_hash(self, data: bytes) -> str: ...  # SHA-256
    def pack(self, skill_dir: Path) -> Path: ...      # create .nobla zip
    def unpack(self, archive_path: Path, dest: Path) -> Path: ...
```

### 3.4 Data Model

```python
class PackageType(str, Enum):
    ARCHIVE = "archive"              # .nobla zip
    POINTER = "pointer"              # manifest-pointer to external source

class TrustTier(str, Enum):
    COMMUNITY = "community"          # auto-approved after scan
    VERIFIED = "verified"            # manual review passed
    OFFICIAL = "official"            # Nobla team authored

class VerificationStatus(str, Enum):
    NONE = "none"                    # not requested
    PENDING = "pending"              # awaiting review
    APPROVED = "approved"            # verified
    REJECTED = "rejected"            # review failed

@dataclass
class SkillVersion:
    version: str                     # SemVer "1.2.3"
    changelog: str
    package_hash: str                # SHA-256 of archive or manifest JSON
    min_nobla_version: str | None    # compatibility constraint
    published_at: datetime
    scan_passed: bool

@dataclass
class MarketplaceSkill:
    id: str                          # UUID
    name: str                        # unique slug (e.g., "github-mcp")
    display_name: str                # human-readable
    description: str
    author_id: str
    author_name: str
    category: SkillCategory          # reuse from skills/models.py (16 categories)
    tags: list[str]
    source_format: SkillSource       # NOBLA, MCP, OPENCLAW, CLAUDE, LANGCHAIN
    package_type: PackageType        # ARCHIVE or POINTER
    source_url: str | None           # for POINTER type
    current_version: str             # SemVer
    versions: list[SkillVersion]
    trust_tier: TrustTier
    verification_status: VerificationStatus
    security_scan_passed: bool
    install_count: int
    active_users: int
    avg_rating: float                # 0.0-5.0
    rating_count: int
    success_rate: float              # 0.0-1.0 from execution data
    created_at: datetime
    updated_at: datetime

@dataclass
class SkillRating:
    id: str
    skill_id: str
    user_id: str
    stars: int                       # 1-5
    review: str | None
    created_at: datetime
    updated_at: datetime

@dataclass
class UpdateNotification:
    skill_id: str
    skill_name: str
    installed_version: str
    latest_version: str
    changelog: str
    published_at: datetime
```

---

## 4. Publishing Pipeline (Tiered)

### 4.1 Flow

```
Author submits skill (archive or manifest)
    │
    ├── SkillPackager.validate() — manifest completeness, archive integrity
    │       │
    │       ├── INVALID → 400 error with validation issues
    │       │
    │       └── VALID → SkillSecurityScanner.scan()
    │               │
    │               ├── PASS → TrustTier.COMMUNITY, listed immediately
    │               │           emit marketplace.skill.published
    │               │           index in ChromaDB for semantic search
    │               │
    │               └── FAIL → rejected, author gets scan issues
    │
    └── Author requests verified badge (separate step)
            │
            └── verification_status → PENDING
                    │
                    └── Admin reviews
                            │
                            ├── APPROVED → TrustTier.VERIFIED
                            └── REJECTED → stays COMMUNITY, reason provided
```

### 4.2 Version Publishing

1. `POST /api/marketplace/skills/{id}/versions` with new archive/manifest
2. Same validation + scan pipeline
3. New `SkillVersion` appended, `current_version` updated
4. Emit `marketplace.skill.updated`
5. Users with this skill installed → `marketplace.update.available` event

### 4.3 MarketplaceRegistry

```python
class MarketplaceRegistry:
    def __init__(self, event_bus, packager, security_scanner): ...
    async def publish(self, author_id: str, author_name: str,
                      manifest: dict, archive_data: bytes | None) -> MarketplaceSkill: ...
    async def publish_version(self, skill_id: str, manifest: dict,
                              archive_data: bytes | None) -> SkillVersion: ...
    async def get_skill(self, skill_id: str) -> MarketplaceSkill | None: ...
    async def request_verification(self, skill_id: str) -> None: ...
    async def admin_review(self, skill_id: str, approved: bool, reason: str | None) -> None: ...
    async def submit_rating(self, skill_id: str, user_id: str, stars: int,
                            review: str | None) -> SkillRating: ...
    async def get_ratings(self, skill_id: str) -> list[SkillRating]: ...
    async def check_updates(self, installed: dict[str, str]) -> list[UpdateNotification]: ...
```

---

## 5. Discovery & Search (Dual Mode + Recommendations)

### 5.1 Structured Search (PostgreSQL)

- Filter by: `category`, `tags`, `trust_tier`, `source_format`
- Sort by: `relevance`, `install_count`, `avg_rating`, `created_at`
- Keyword: PostgreSQL `tsvector` full-text index on `display_name || ' ' || description || ' ' || tags`
- Pagination: `page` + `page_size` (default 20)

### 5.2 Semantic Search (ChromaDB)

- On publish: embed `display_name + " " + description + " " + " ".join(tags)` into `marketplace_skills` collection
- NL query → ChromaDB vector similarity → ranked results with distance scores
- Merged with structured results: semantic matches get a relevance boost

### 5.3 Pattern-Based Recommendations

Leverages Phase 5B.1 `PatternDetector`:
1. Query user's detected patterns (tool sequences)
2. For each pattern's `tool_sequence`, find marketplace skills whose category/tags match those tools
3. Rank by pattern confidence + skill rating
4. Return top 5

### 5.4 Similar-to-Installed Recommendations

Passive discovery based on semantic similarity to already-installed skills:
1. For each installed skill, get its ChromaDB embedding
2. Query ChromaDB for nearest neighbors (exclude already-installed)
3. Deduplicate across all installed skills
4. Rank by average cosine similarity + install count
5. Return top 5

This means if a user has "GitHub MCP" installed, they'll see "GitLab MCP", "Bitbucket MCP", "Code Review Tool" etc. without explicitly searching.

### 5.5 SkillDiscovery

```python
@dataclass
class SearchResults:
    items: list[MarketplaceSkill]
    total: int
    page: int
    page_size: int

class SkillDiscovery:
    def __init__(self, registry: MarketplaceRegistry, pattern_detector=None,
                 skill_runtime=None): ...
    async def search(self, query: str | None = None,
                     category: SkillCategory | None = None,
                     tags: list[str] | None = None,
                     trust_tier: TrustTier | None = None,
                     source_format: SkillSource | None = None,
                     sort_by: str = "relevance",
                     page: int = 1, page_size: int = 20) -> SearchResults: ...
    async def get_pattern_recommendations(self, user_id: str) -> list[MarketplaceSkill]: ...
    async def get_similar_recommendations(self, user_id: str) -> list[MarketplaceSkill]: ...
    async def get_recommendations(self, user_id: str) -> dict[str, list[MarketplaceSkill]]: ...
```

`get_recommendations()` returns:
```python
{
    "based_on_patterns": [...],      # from PatternDetector
    "similar_to_installed": [...],   # from ChromaDB similarity
}
```

---

## 6. Versioning & Update Notifications

### 6.1 SemVer Enforcement

- Version strings validated as `major.minor.patch` on publish
- New versions must be strictly greater than current_version
- `min_nobla_version` is optional compatibility constraint (not enforced yet, informational)

### 6.2 Update Checking

- `MarketplaceRegistry.check_updates(installed)` takes `{skill_name: installed_version}` dict
- Compares against registry `current_version` for each
- Returns list of `UpdateNotification` for skills with newer versions

### 6.3 Archive/Manifest Storage

Published archives and manifests are stored on the local filesystem under `data/marketplace/skills/{skill_id}/{version}/`:
- Archive: `skill.nobla` (the original zip)
- Manifest-pointer: `manifest.json`

This path is passed to `SkillRuntime.upgrade(skill_id, source=archive_path)` during updates. The `data/marketplace/` directory is configurable via `MarketplaceSettings.storage_dir`.

### 6.4 Update Flow

1. Flutter calls `GET /api/marketplace/updates` on marketplace screen open (client-driven polling, no backend timer)
2. Backend returns list of available updates
3. User sees badge on installed skills with "Update available"
4. User taps → sees changelog → confirms
5. `MarketplaceService` resolves archive path → calls `SkillRuntime.upgrade(skill_id, source=path)`
6. New version scanned before install (same security pipeline)
7. Emit `marketplace.skill.updated` on success

---

## 7. Ratings & Usage Stats

### 7.1 Star Ratings

- 1-5 stars + optional text review
- One rating per user per skill (upsert — update replaces previous)
- Stored in `marketplace_ratings` table
- `avg_rating` and `rating_count` denormalized on `MarketplaceSkill` for fast query

### 7.2 Usage Stats (Automatic)

Tracked by `UsageTracker` subscribing to events:

| Stat | Source |
|------|--------|
| `install_count` | `skill.installed` event from SkillRuntime (fires for ALL installs — UsageTracker filters by checking `skill_id` payload against known marketplace skills) |
| `active_users` | Count of users with skill enabled (decremented on `skill.uninstalled`) |
| `success_rate` | `tool.executed` / (`tool.executed` + `tool.failed`) filtered by `skill_id` in payload |

**Event deduplication:** `marketplace.skill.installed` is a wrapper event emitted by `MarketplaceService` AFTER the underlying `skill.installed` fires from `SkillRuntime`. The `UsageTracker` subscribes only to `skill.installed` (from runtime) to count installs — it checks `event.payload.get("skill_id")` to filter marketplace-tracked skills. The `marketplace.skill.installed` event exists for Flutter UI notifications, not for stat tracking.

### 7.3 Security Badge

- Displayed if latest version's `scan_passed == True`
- Re-scanned on every version publish
- Badge shows "Security Verified" with checkmark

### 7.4 UsageTracker

```python
class UsageTracker:
    def __init__(self, event_bus, registry): ...
    async def on_skill_installed(self, event) -> None: ...
    async def on_skill_uninstalled(self, event) -> None: ...
    async def on_tool_executed(self, event) -> None: ...
    async def on_tool_failed(self, event) -> None: ...
    async def get_stats(self, skill_id: str) -> dict: ...
```

### 7.5 MarketplaceService (Orchestrator)

```python
class MarketplaceService:
    def __init__(self, event_bus, registry: MarketplaceRegistry,
                 discovery: SkillDiscovery, usage_tracker: UsageTracker,
                 skill_runtime, settings): ...
    async def start(self) -> None: ...       # register event subscriptions (store as (type, handler) tuples)
    async def stop(self) -> None: ...        # unsubscribe all
    async def install_skill(self, skill_id: str, user_id: str) -> None: ...
        # 1. Get skill from registry
        # 2. Resolve archive path or manifest-pointer source
        # 3. Call skill_runtime.install(source)
        # 4. Emit marketplace.skill.installed
    async def uninstall_skill(self, skill_id: str, user_id: str) -> None: ...
        # 1. Call skill_runtime.uninstall(skill_id)
        # 2. Emit marketplace.skill.uninstalled
    async def upgrade_skill(self, skill_id: str, version: str) -> None: ...
        # 1. Resolve new version archive path
        # 2. Call skill_runtime.upgrade(skill_id, source=path)
    # Delegates to registry/discovery for all other operations
    async def publish(self, author_id, author_name, manifest, archive_data): ...
    async def search(self, **kwargs) -> SearchResults: ...
    async def get_recommendations(self, user_id: str) -> dict: ...
    async def submit_rating(self, skill_id, user_id, stars, review): ...
    async def check_updates(self, installed: dict) -> list[UpdateNotification]: ...
```

### 7.6 Storage Model Note

All marketplace models use **in-memory storage** for this phase (dict-based stores), consistent with Phase 5B.1. The spec describes PostgreSQL table schemas for future persistence — the dataclass models map 1:1 to future SQLAlchemy ORM models. The existing 16 `SkillCategory` values are sufficient for the marketplace; no new categories are needed.

For archive storage, `.nobla` zip files and manifest JSON files are persisted to `data/marketplace/skills/{skill_id}/{version}/` on the local filesystem.

---

## 8. Event Contract

### 8.1 Events Emitted

| Event | Payload | Source |
|-------|---------|--------|
| `marketplace.skill.published` | MarketplaceSkill summary | MarketplaceRegistry |
| `marketplace.skill.updated` | skill_id, new_version | MarketplaceRegistry |
| `marketplace.skill.installed` | skill_id, user_id, version | MarketplaceService |
| `marketplace.skill.uninstalled` | skill_id, user_id | MarketplaceService |
| `marketplace.skill.rated` | skill_id, user_id, stars | MarketplaceRegistry |
| `marketplace.update.available` | UpdateNotification | MarketplaceRegistry |
| `marketplace.verification.requested` | skill_id | MarketplaceRegistry |
| `marketplace.verification.approved` | skill_id | MarketplaceRegistry |
| `marketplace.verification.rejected` | skill_id, reason | MarketplaceRegistry |

### 8.2 Events Consumed

| Event | Consumer | Purpose |
|-------|----------|---------|
| `tool.executed` | UsageTracker | Track success count per skill |
| `tool.failed` | UsageTracker | Track failure count per skill |
| `skill.installed` | UsageTracker | Increment install_count, active_users |
| `skill.uninstalled` | UsageTracker | Decrement active_users |

---

## 9. REST API

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/marketplace/search` | Search/browse (query, category, tags, tier, format, sort, page) |
| GET | `/api/marketplace/skills/{id}` | Skill detail with versions + stats |
| GET | `/api/marketplace/skills/{id}/versions` | Version history |
| GET | `/api/marketplace/skills/{id}/ratings` | Ratings list |
| POST | `/api/marketplace/publish` | Publish new skill (multipart archive or JSON manifest) |
| POST | `/api/marketplace/skills/{id}/versions` | Publish new version |
| POST | `/api/marketplace/skills/{id}/rate` | Submit/update rating (body: stars, review?) |
| POST | `/api/marketplace/skills/{id}/install` | Install skill → delegates to SkillRuntime |
| DELETE | `/api/marketplace/skills/{id}/install` | Uninstall skill |
| GET | `/api/marketplace/updates` | Check updates for installed skills |
| GET | `/api/marketplace/recommendations` | Pattern-based + similar-to-installed recommendations |
| POST | `/api/marketplace/skills/{id}/request-verification` | Request verified badge |
| GET | `/api/marketplace/categories` | List categories with skill counts |
| DELETE | `/api/marketplace/skills/{id}` | Unpublish/withdraw skill (author only) |
| POST | `/api/marketplace/admin/review/{id}` | Admin approve/reject verification (body: approved, reason?) |

15 routes total.

---

## 10. Flutter UI

### 10.1 Entry Point

"Browse Marketplace" button in the existing Tools tab (Browse section). Routes to `/home/tools/marketplace`.

### 10.2 MarketplaceScreen

| Section | Content |
|---------|---------|
| **Search bar** | TextField with search icon + category FilterChip row + trust tier filter (All/Community/Verified/Official) |
| **Results grid** | GridView of SkillCards — icon, name, author, rating stars, install count, trust badge, Install/Installed button |
| **Recommendations** | Two horizontal ScrollViews at top (before results): "Based on your patterns" and "Similar to installed" — only shown if items exist |

### 10.3 SkillDetailScreen

| Section | Content |
|---------|---------|
| **Header** | Display name, author, category Chip, trust badge, current version, Install/Update button |
| **Description** | Full text + tag Chips |
| **Stats row** | 4 stats: install count, active users, avg rating (stars), success rate % |
| **Versions** | ExpansionTile list with version number, date, changelog |
| **Ratings** | Star distribution bar chart + ListView of reviews |
| **Update banner** | Shown if newer version available — changelog + "Update" button |

### 10.4 Dart Models

Mirror all backend models: `MarketplaceSkill`, `SkillVersion`, `SkillRating`, `UpdateNotification`, `SearchResults`, enums (`PackageType`, `TrustTier`, `VerificationStatus`). `fromJson`/`toJson` on all.

### 10.5 Riverpod Providers

- `marketplaceSearchProvider` — FutureProvider.family for search queries
- `skillDetailProvider` — FutureProvider.family for skill ID
- `skillRatingsProvider` — FutureProvider.family for skill ID
- `updateListProvider` — FutureProvider for available updates
- `recommendationsProvider` — FutureProvider for combined recommendations
- `categoryListProvider` — FutureProvider for categories with counts

---

## 11. Gateway Integration

### 11.1 Lifespan Wiring

```python
# In lifespan(), after learning_service block:
marketplace_service = None
if settings.marketplace.enabled:
    from nobla.marketplace.packager import SkillPackager
    from nobla.marketplace.registry import MarketplaceRegistry
    from nobla.marketplace.discovery import SkillDiscovery
    from nobla.marketplace.stats import UsageTracker
    from nobla.marketplace.service import MarketplaceService
    from nobla.gateway.marketplace_handlers import marketplace_router

    packager = SkillPackager()
    mp_registry = MarketplaceRegistry(
        event_bus=event_bus,
        packager=packager,
        security_scanner=skill_scanner,
    )
    discovery = SkillDiscovery(
        registry=mp_registry,
        pattern_detector=pattern_detector if learning_service else None,
        skill_runtime=skill_runtime,
    )
    usage_tracker = UsageTracker(event_bus=event_bus, registry=mp_registry)
    marketplace_service = MarketplaceService(
        event_bus=event_bus,
        registry=mp_registry,
        discovery=discovery,
        usage_tracker=usage_tracker,
        skill_runtime=skill_runtime,
        settings=settings.marketplace,
    )
    app.state.marketplace_service = marketplace_service
    app.include_router(marketplace_router)
    await marketplace_service.start()
    logger.info("marketplace_service_started")
```

### 11.2 MarketplaceSettings

```python
class MarketplaceSettings(BaseModel):
    enabled: bool = True
    max_skills_per_author: int = 50
    max_archive_size_mb: int = 10
    storage_dir: str = "data/marketplace"    # local filesystem for archives
```

### 11.3 Required Changes to Existing Modules

| Module | Change |
|--------|--------|
| `config/settings.py` | Add `MarketplaceSettings` + `marketplace` field on `Settings` |
| `gateway/lifespan.py` | Wire marketplace service (after learning, before multi-agent) |
| `tools/executor.py` | Add `skill_id` to event payload for `SkillToolBridge` tools |
| `app/lib/core/routing/app_router.dart` | Add `/home/tools/marketplace` and `/home/tools/marketplace/:id` routes |

---

## 12. Security & Privacy

- All published skills scanned by `SkillSecurityScanner` before listing
- Archive packages validated: SHA-256 integrity check, manifest completeness
- Install goes through existing `SkillRuntime` pipeline (permission check, approval, audit)
- Admin verification is separate from security — scan is automated, trust badge is manual
- No skill code or metadata leaves the device (local marketplace only)
- Rating data is local (no external aggregation)
- `max_archive_size_mb` prevents oversized uploads (default 10MB)

---

## 13. Module Structure

```
backend/nobla/marketplace/
├── __init__.py
├── models.py              # MarketplaceSkill, SkillVersion, SkillRating, enums (~200 lines)
├── registry.py            # MarketplaceRegistry — CRUD, publish, verify, rate (~300 lines)
├── discovery.py           # SkillDiscovery — keyword + semantic + recommendations (~250 lines)
├── packager.py            # SkillPackager — archive/manifest validate, hash (~200 lines)
├── stats.py               # UsageTracker — event listeners, stat aggregation (~150 lines)
└── service.py             # MarketplaceService — orchestrator, wiring (~180 lines)

backend/nobla/gateway/
└── marketplace_handlers.py  # REST API (14 routes) (~300 lines)

app/lib/features/marketplace/
├── models/marketplace_models.dart       # Dart models + enums (~250 lines)
├── providers/marketplace_providers.dart  # Riverpod providers (~150 lines)
├── screens/
│   ├── marketplace_screen.dart          # search + grid + recommendations (~250 lines)
│   └── skill_detail_screen.dart         # detail with versions + ratings (~250 lines)
└── widgets/
    ├── skill_card.dart                  # grid card with stats + install button (~120 lines)
    ├── rating_widget.dart               # star display + submit form (~100 lines)
    └── version_list_widget.dart         # expandable version history (~80 lines)
```

All files under 750 lines. Estimated ~1,580 backend + ~1,200 Flutter = ~2,780 lines total.

---

## 14. Testing Strategy

- **Unit tests**: Each module independently (packager, registry, discovery, stats, service)
- **Integration tests**: Publish → search → install → rate → check updates flow
- **Security tests**: Scanner rejection blocks publishing, archive integrity validation
- **Target**: ~150-180 backend tests + ~50-70 Flutter tests
- **Security-critical paths** (publish pipeline, archive validation): 90%+ coverage

---

## 15. Dependencies

### Backend (new)
None — uses existing (FastAPI, ChromaDB, PostgreSQL, Pydantic).

### Flutter (new)
None — uses existing (flutter_riverpod, dio, go_router).

### Internal
- `nobla.skills.runtime` — install/upgrade/uninstall
- `nobla.skills.adapter` — UniversalSkillAdapter (format detection)
- `nobla.skills.security` — SkillSecurityScanner
- `nobla.skills.models` — SkillCategory, SkillSource enums
- `nobla.events.bus` — event pub/sub
- `nobla.learning.patterns` — PatternDetector (optional, for recommendations)
- `nobla.config.settings` — MarketplaceSettings
