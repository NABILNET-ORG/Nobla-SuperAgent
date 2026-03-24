# Phase 4A Design Spec: Screen Vision

**Date:** 2026-03-24
**Author:** NABILNET.AI
**Status:** Draft
**Scope:** Vision tools — screenshot capture, OCR, UI element detection, NL element targeting
**Depends on:** Phase 4-Pre (Tool Platform Foundation)
**Parent spec:** `2026-03-23-phase4-computer-control-vision-design.md` (Section 6.2)

---

## 1. Overview

Phase 4A adds four vision tools to the tool platform, enabling Nobla Agent to see the screen. These tools form the perception layer that Phase 4B (Computer Control) will act upon. All tools are STANDARD tier, require no approval, and run entirely locally.

### Goals

- Capture screenshots across monitors and regions
- Extract text from images via OCR (Tesseract + EasyOCR fallback)
- Detect UI elements with heuristics (OCR-based) and optionally UI-TARS (progressive)
- Resolve natural language descriptions to screen coordinates

### Non-Goals

- UI-TARS model evaluation/selection (stub only — real integration deferred)
- Computer control actions (Phase 4B)
- Screen mirroring or streaming (Phase 4E)

---

## 2. Architecture Decisions

### 2.1 Inline Fallback (No Engine Abstraction)

Each tool handles its own fallback logic internally. OCRTool tries Tesseract, catches ImportError/failure, falls back to EasyOCR. UIDetectionTool checks settings for UI-TARS, falls back to OCR-based detection.

**Rationale:** We have exactly 2 OCR backends and 2 detection strategies. An engine ABC is warranted at 3+. Refactoring to an engine pattern later is a ~30-minute task. YAGNI wins.

### 2.2 Direct Internal Composition

Vision tools call each other's internal methods directly, bypassing the executor pipeline. ElementTargetingTool calls `screenshot_tool.capture()` and `detection_tool.detect()` without going through permission/approval/audit for each sub-step.

**Rationale:** The outer tool's execution is what gets audited as a single unit. Re-running permission checks and audit logging for internal sub-steps adds latency and noise without security benefit — all vision tools are the same tier (STANDARD) with no approval required.

### 2.3 Dual Interface Pattern

Every tool exposes two interfaces:

| Interface | Audience | Returns | Serialization |
|-----------|----------|---------|---------------|
| `execute(params: ToolParams) → ToolResult` | Tool platform (public) | JSON-safe base64 strings | Yes |
| Internal method (e.g., `capture()`, `extract()`) | Other vision tools | Raw Python objects (PIL.Image, dataclasses) | No |

**Rationale:** Prevents PIL.Image objects from entering ToolResult.data (which gets serialized to JSON-RPC and passed through audit/sanitize). Eliminates base64 encode→decode overhead at internal boundaries.

### 2.4 Shared Element Cache

A lightweight `ElementCache` in `vision/cache.py` stores recently detected elements keyed by screenshot thumbnail hash. Vision tools write to it; Phase 4B tools will read from it.

**Rationale:** Avoids re-running expensive detection when `ui.target_element` is immediately followed by `mouse.click` (Phase 4B). Single-entry cache — only the most recent screen state matters for rapid action sequences.

### 2.5 Async Threading for Blocking Calls

All CPU-heavy or I/O-blocking operations (`mss` capture, Tesseract, EasyOCR) are wrapped in `asyncio.to_thread()`.

**Rationale:** Prevents blocking the event loop. Individual calls are fast (<50ms for screenshots, ~200ms for OCR) but can lag on large regions or slow hardware.

---

## 3. Module Structure

```
backend/nobla/tools/vision/
├── __init__.py      # Trigger @register_tool + ElementCache singleton (~15 lines)
├── cache.py         # ElementCache — TTL cache for detected elements (~35 lines)
├── capture.py       # ScreenshotTool (~130 lines)
├── ocr.py           # OCRTool — Tesseract + EasyOCR fallback (~180 lines)
├── detection.py     # UIDetectionTool — UI-TARS stub + OCR-based (~200 lines)
└── targeting.py     # ElementTargetingTool — NL → coordinates (~150 lines)
```

**Estimated total:** ~710 lines across 6 files. All files well under the 750-line limit.

---

## 4. Configuration

**New addition** to `config/settings.py` (does not exist yet — must be created and wired into the `Settings` class). The parent spec defined a simpler `VisionSettings`; this version adds `screenshot_include_cursor`, `ocr_confidence_threshold`, and `detection_confidence_threshold` based on Phase 4A design refinement:

```python
class VisionSettings(BaseModel):
    enabled: bool = True
    screenshot_format: str = "png"
    screenshot_quality: int = 85
    screenshot_max_dimension: int = 1920
    screenshot_include_cursor: bool = False
    ocr_engine: str = "tesseract"
    ocr_languages: list[str] = ["en"]
    ocr_confidence_threshold: float = 0.5
    ui_tars_enabled: bool = False
    ui_tars_model_path: str = ""
    detection_confidence_threshold: float = 0.4
    element_cache_ttl: int = 5
```

Wired into `Settings` as: `vision: VisionSettings = Field(default_factory=VisionSettings)`

**Field details:**

| Field | Purpose |
|-------|---------|
| `screenshot_format` | "png" (lossless, better for OCR) or "jpeg" (smaller) |
| `screenshot_quality` | JPEG quality 1-100, ignored for PNG |
| `screenshot_max_dimension` | Downscale returned image only; internal processing uses native resolution |
| `screenshot_include_cursor` | Whether to capture mouse cursor. **Deferred implementation** — setting is defined but `mss` captures without cursor by default; platform-specific cursor overlay is a Phase 4B task. |
| `ocr_engine` | Preferred engine: "tesseract" or "easyocr". Falls back to other on failure. |
| `ocr_languages` | Tesseract language codes (e.g., ["en", "ara"] for English + Arabic) |
| `ocr_confidence_threshold` | Filter OCR results below this confidence (0.0-1.0) |
| `ui_tars_enabled` | Progressive: off by default. System works with OCR-based detection alone. |
| `ui_tars_model_path` | Path to UI-TARS model checkpoint. Required if `ui_tars_enabled=True`. |
| `detection_confidence_threshold` | Filter detected elements below this confidence (0.0-1.0) |
| `element_cache_ttl` | Seconds to cache detected elements before re-running detection |

---

## 5. Dependencies

Added to `pyproject.toml` as optional dependency groups:

```toml
[project.optional-dependencies]
vision = ["python-mss>=9.0", "Pillow>=10.0", "pytesseract>=0.3"]
vision-full = ["python-mss>=9.0", "Pillow>=10.0", "pytesseract>=0.3", "easyocr>=1.7"]
```

**Rationale:** EasyOCR pulls PyTorch (~2GB). Users who only need Tesseract shouldn't bear that cost. `pip install nobla[vision]` for the base stack, `pip install nobla[vision-full]` for EasyOCR fallback.

All four packages are optional at runtime. Each tool gracefully handles `ImportError` with a clear error message listing what to install.

| Package | Size | Purpose |
|---------|------|---------|
| python-mss >=9.0 | ~50KB | Fast cross-platform screenshot capture |
| Pillow >=10.0 | ~3MB | Image manipulation, resize, format conversion |
| pytesseract >=0.3 | ~20KB | Python wrapper for Tesseract OCR engine |
| easyocr >=1.7 | ~2GB (with PyTorch) | Neural network OCR fallback |

---

## 6. Tool Designs

### 6.1 ElementCache (`cache.py`)

Shared TTL cache for detected UI elements. Single-entry — only the most recent screen state is cached.

**Note:** `cache.py` is an addition not listed in the parent spec's `vision/` directory structure. Added to support the shared cache design decision (Section 2.4).

The `element_cache` module-level singleton lives in `cache.py` (not `__init__.py`) to avoid circular imports — `detection.py` and `targeting.py` import it directly from `cache.py`.

**Thread safety:** No locking. Python's GIL protects attribute assignment, and "last write wins" is acceptable for a single-entry cache. Concurrent detection calls racing on `put()` simply overwrite each other with equally valid results.

```python
@dataclass
class CachedElements:
    elements: list[dict]
    screenshot_hash: str
    timestamp: float

class ElementCache:
    def __init__(self, ttl: int = 5):
        self._ttl = ttl
        self._entry: CachedElements | None = None

    def get(self, screenshot_hash: str) -> list[dict] | None:
        """Return cached elements if hash matches and TTL not expired."""
        if (self._entry
            and self._entry.screenshot_hash == screenshot_hash
            and (time.monotonic() - self._entry.timestamp) < self._ttl):
            return self._entry.elements
        return None

    def put(self, screenshot_hash: str, elements: list[dict]) -> None:
        self._entry = CachedElements(elements, screenshot_hash, time.monotonic())

    def clear(self) -> None:
        self._entry = None

# Module-level singleton — imported by detection.py and targeting.py directly.
# Lives here (not in __init__.py) to avoid circular imports.
element_cache = ElementCache()
```

**Screenshot hashing:** Uses thumbnail hash for speed — resize image to 64x64, hash the bytes with MD5. This takes ~1ms vs ~50ms for hashing full 4K pixel data. Catches actual screen changes without pixel-perfect accuracy (not needed for cache invalidation).

```python
def hash_thumbnail(image: Image.Image) -> str:
    thumb = image.resize((64, 64)).tobytes()
    return hashlib.md5(thumb).hexdigest()
```

### 6.2 ScreenshotTool (`capture.py`)

Captures screenshots using `mss` (python-mss). Supports multi-monitor, region capture, and format selection.

**Registration:**

```python
@register_tool
class ScreenshotTool(BaseTool):
    name = "screenshot.capture"
    description = "Capture a screenshot of the current screen"
    category = ToolCategory.VISION
    tier = Tier.STANDARD
    requires_approval = False
```

**Parameters:**

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `monitor` | int | 0 | 0 = all monitors combined, 1+ = specific monitor |
| `region` | dict | None | `{x, y, width, height}` crop region in pixels |
| `format` | str | from settings | "png" or "jpeg" |
| `quality` | int | from settings | JPEG quality (ignored for PNG) |

**Internal data model:**

```python
@dataclass
class CaptureResult:
    image: Image.Image    # Full-resolution PIL.Image
    width: int
    height: int
    monitor: int
```

**Dual interface:**

- `capture(monitor, region) → CaptureResult` — internal API, returns raw PIL.Image at native resolution. Used by OCR, detection, and targeting tools.
- `execute(params) → ToolResult` — public API. Calls `capture()`, then downscales if any dimension exceeds `screenshot_max_dimension`, encodes to base64.

**Execution flow:**

1. Validate: region bounds positive integers, monitor index exists, format is "png" or "jpeg"
2. `await asyncio.to_thread(sct.grab, monitor_rect)` — mss capture
3. Raw pixels → `PIL.Image.frombytes()`
4. For `execute()` only: downscale → encode → base64
5. Return `CaptureResult` (internal) or `ToolResult` (public)

**Public ToolResult.data:**

```python
{
    "image_b64": "...",
    "width": 1920,            # returned image dimensions
    "height": 1080,
    "format": "png",
    "monitor": 0,
    "native_width": 3840,     # original capture dimensions
    "native_height": 2160,
}
```

**describe_action override:** `"Capture screenshot of monitor {n}"` or `"Capture region (x, y, w, h) on monitor {n}"`

### 6.3 OCRTool (`ocr.py`)

Extracts text from images using Tesseract (primary) or EasyOCR (fallback). Returns structured text blocks with bounding boxes and confidence scores.

**Registration:**

```python
@register_tool
class OCRTool(BaseTool):
    name = "ocr.extract"
    description = "Extract text from a screenshot using OCR"
    category = ToolCategory.VISION
    tier = Tier.STANDARD
    requires_approval = False
```

**Parameters:**

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `image_b64` | str | required | Base64-encoded image |
| `languages` | list[str] | from settings | Override OCR languages |
| `engine` | str | from settings | Force "tesseract" or "easyocr" |

**Internal data models:**

```python
@dataclass
class TextBlock:
    text: str
    confidence: float
    bbox: dict              # {x, y, width, height}

@dataclass
class OCRResult:
    blocks: list[TextBlock]
    full_text: str
    engine_used: str
```

**Dual interface:**

- `extract(image, languages, engine) → OCRResult` — internal API, accepts PIL.Image. Used by detection and targeting tools.
- `execute(params) → ToolResult` — public API. Decodes base64, calls `extract()`, serializes result.

**Validate:** `image_b64` must be present and decodable to a valid image. Fail fast with clear message rather than deep Pillow errors.

**Tesseract path:**

```python
async def _tesseract_extract(self, image, languages) -> OCRResult:
    lang_str = "+".join(languages)
    data = await asyncio.to_thread(
        pytesseract.image_to_data, image,
        output_type=pytesseract.Output.DICT, lang=lang_str
    )
    blocks = []
    for i, text in enumerate(data["text"]):
        if not text.strip():
            continue
        conf = float(data["conf"][i])
        if conf < settings.vision.ocr_confidence_threshold * 100:  # Tesseract uses 0-100
            continue
        blocks.append(TextBlock(
            text=text.strip(),
            confidence=conf / 100.0,
            bbox={"x": data["left"][i], "y": data["top"][i],
                  "width": data["width"][i], "height": data["height"][i]},
        ))
    full_text = " ".join(b.text for b in blocks)
    return OCRResult(blocks=blocks, full_text=full_text, engine_used="tesseract")
```

**EasyOCR path:**

**Note:** `numpy` is a transitive dependency of EasyOCR (via PyTorch). The `import numpy` must be a **lazy import inside `_easyocr_extract()`**, not a top-level import, to avoid crashing when only the `vision` (non-full) dependency group is installed.

```python
async def _easyocr_extract(self, image, languages) -> OCRResult:
    import numpy  # lazy import — only available with vision-full deps
    reader = await self._get_reader(languages)
    results = await asyncio.to_thread(reader.readtext, numpy.array(image))
    blocks = []
    for bbox_points, text, confidence in results:
        if confidence < settings.vision.ocr_confidence_threshold:
            continue
        x1, y1 = bbox_points[0]
        x2, y2 = bbox_points[2]
        blocks.append(TextBlock(
            text=text, confidence=confidence,
            bbox={"x": int(x1), "y": int(y1),
                  "width": int(x2 - x1), "height": int(y2 - y1)},
        ))
    full_text = " ".join(b.text for b in blocks)
    return OCRResult(blocks=blocks, full_text=full_text, engine_used="easyocr")
```

**EasyOCR Reader singleton:** Reader initialization is expensive (~2s). Lazy singleton, created on first use and reused. Re-created only if language list changes.

```python
_easyocr_reader: easyocr.Reader | None = None
_reader_langs: list[str] | None = None

async def _get_reader(self, languages):
    if self._easyocr_reader is None or self._reader_langs != languages:
        self._easyocr_reader = await asyncio.to_thread(
            easyocr.Reader, languages, gpu=False
        )
        self._reader_langs = languages
    return self._easyocr_reader
```

**Fallback logic (symmetric — try preferred engine first, then the other):**

```python
async def extract(self, image, languages=None, engine=None) -> OCRResult:
    languages = languages or settings.vision.ocr_languages
    preferred = engine or settings.vision.ocr_engine
    other = "easyocr" if preferred == "tesseract" else "tesseract"

    engines = {"tesseract": self._tesseract_extract, "easyocr": self._easyocr_extract}

    # Try preferred engine first
    try:
        return await engines[preferred](image, languages)
    except (ImportError, Exception):
        pass

    # Fall back to the other engine
    try:
        return await engines[other](image, languages)
    except (ImportError, Exception):
        pass

    raise RuntimeError(
        "No OCR engine available. Install pytesseract or easyocr: "
        "pip install nobla[vision] or pip install nobla[vision-full]"
    )
```

**describe_action override:** `"Extract text using {engine} (languages: {langs})"`

**Public ToolResult.data:**

```python
{
    "blocks": [
        {"text": "Submit", "confidence": 0.95, "bbox": {"x": 100, "y": 200, "width": 80, "height": 30}},
        ...
    ],
    "full_text": "Submit Cancel ...",
    "engine_used": "tesseract",
}
```

### 6.4 UIDetectionTool (`detection.py`)

Detects UI elements in a screenshot. Uses UI-TARS model when enabled, falls back to OCR-based heuristic detection.

**Registration:**

```python
@register_tool
class UIDetectionTool(BaseTool):
    name = "ui.detect_elements"
    description = "Detect UI elements in a screenshot"
    category = ToolCategory.VISION
    tier = Tier.STANDARD
    requires_approval = False
```

**Parameters:**

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `image_b64` | str | required | Base64-encoded image |
| `element_types` | list[str] | None | Filter: only return matching types |

**Internal data model:**

```python
@dataclass
class DetectedElement:
    element_type: str     # "button", "input", "label", "link", "heading", "text"
    label: str
    bbox: dict            # {x, y, width, height}
    confidence: float
```

**Dual interface:**

- `detect(image) → list[DetectedElement]` — internal API. Used by targeting tool.
- `execute(params) → ToolResult` — public API.

**UI-TARS path (stub for Phase 4A):**

```python
async def _uitars_detect(self, image) -> list[DetectedElement]:
    if not settings.vision.ui_tars_model_path:
        raise RuntimeError("UI-TARS model path not configured")
    # Phase 4A: stub — raises to force OCR fallback.
    # Real implementation will load model and run inference.
    raise NotImplementedError("UI-TARS inference not yet implemented")
```

**OCR-based detection fallback (primary workhorse for Phase 4A):**

```python
async def _ocr_based_detect(self, image) -> list[DetectedElement]:
    # 1. Run OCR
    ocr_result = await self._ocr_tool.extract(image)

    # 2. Classify each text block using heuristics + pixel sampling
    elements = []
    for block in ocr_result.blocks:
        element_type = self._classify_element(image, block)
        confidence = block.confidence * 0.7   # discount vs UI-TARS
        if confidence >= settings.vision.detection_confidence_threshold:
            elements.append(DetectedElement(
                element_type=element_type,
                label=block.text,
                bbox=block.bbox,
                confidence=confidence,
            ))
    return elements
```

**Element classification heuristics (with pixel sampling):**

```python
def _classify_element(self, image: Image.Image, block: TextBlock) -> str:
    text = block.text.strip()
    bbox = block.bbox

    # Check for URL pattern
    if text.startswith(("http://", "https://", "www.")):
        return "link"

    # Check for label pattern (ends with ":")
    if text.endswith(":"):
        return "label"

    # Pixel sampling: check if text has a distinct background rectangle
    has_bg = self._has_distinct_background(image, bbox)

    # Short text with distinct background → button
    word_count = len(text.split())
    if word_count <= 3 and has_bg:
        return "button"

    # Larger text block height relative to neighbors → heading
    if bbox["height"] > 30:  # heuristic: heading text is taller
        return "heading"

    # Default
    return "text"
```

**Pixel sampling for background detection:**

Sample pixels at the edges of the bounding box and compare to pixels just outside. If there's a distinct color boundary (background rectangle), the text is likely inside a button or input field.

```python
def _has_distinct_background(self, image: Image.Image, bbox: dict) -> bool:
    x, y, w, h = bbox["x"], bbox["y"], bbox["width"], bbox["height"]
    pad = 4  # pixels outside bbox to sample

    # Sample inside and outside bbox edges
    try:
        inside = image.getpixel((x + w // 2, y + h // 2))
        outside_samples = [
            image.getpixel((max(0, x - pad), y + h // 2)),
            image.getpixel((min(image.width - 1, x + w + pad), y + h // 2)),
            image.getpixel((x + w // 2, max(0, y - pad))),
            image.getpixel((x + w // 2, min(image.height - 1, y + h + pad))),
        ]
    except (IndexError, Exception):
        return False

    # Check if inside color differs from outside by threshold
    for outside in outside_samples:
        diff = sum(abs(a - b) for a, b in zip(inside[:3], outside[:3]))
        if diff > 80:  # RGB distance threshold
            return True
    return False
```

**Cache integration:** After detection, write results to shared `ElementCache`:

```python
img_hash = hash_thumbnail(image)
element_cache.put(img_hash, [asdict(e) for e in elements])
```

**describe_action override:** `"Detect UI elements in screenshot"`

**Public ToolResult.data:**

```python
{
    "elements": [
        {"element_type": "button", "label": "Submit", "bbox": {...}, "confidence": 0.66},
        {"element_type": "heading", "label": "Settings", "bbox": {...}, "confidence": 0.72},
        ...
    ],
    "count": 12,
    "method": "ocr_heuristic",  # or "ui_tars"
}
```

### 6.5 ElementTargetingTool (`targeting.py`)

Resolves a natural language description to screen coordinates. Composes screenshot, detection, and fuzzy matching internally.

**Registration:**

```python
@register_tool
class ElementTargetingTool(BaseTool):
    name = "ui.target_element"
    description = "Find a UI element by natural language description"
    category = ToolCategory.VISION
    tier = Tier.STANDARD
    requires_approval = False
```

**Parameters:**

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `description` | str | required | NL description: "the Submit button" |
| `monitor` | int | 0 | Which monitor to search |
| `region` | dict | None | Narrow search to a screen region |

**Internal data model:**

```python
@dataclass
class TargetResult:
    x: int
    y: int
    element: DetectedElement
    match_score: float
```

**Internal data model for matching:**

```python
@dataclass
class _Match:
    element: DetectedElement
    score: float
```

**Tool composition via lazy properties (using public ToolRegistry API):**

```python
from nobla.tools.registry import ToolRegistry

_registry = ToolRegistry()

@property
def _capture(self):
    return _registry.get("screenshot.capture")

@property
def _detector(self):
    return _registry.get("ui.detect_elements")
```

**Rationale:** Lazy resolution at call time, not import time. Uses the public `ToolRegistry.get()` API instead of the private `_TOOL_REGISTRY` dict — avoids coupling to implementation details. Dict lookup is ~50ns — negligible overhead.

**Internal `target()` method:**

```python
async def target(self, description: str, monitor: int = 0,
                 region: dict | None = None) -> TargetResult:
    # 1. Capture screenshot
    capture = await self._capture.capture(monitor, region)

    # 2. Check element cache
    img_hash = hash_thumbnail(capture.image)
    cached = element_cache.get(img_hash)

    # 3. Detect elements if not cached
    if cached:
        elements = [DetectedElement(**e) for e in cached]
    else:
        elements = await self._detector.detect(capture.image)

    # 4. Fuzzy match
    match = self._best_match(description, elements)
    if not match:
        raise ValueError(f"No element matching '{description}' found")

    # 5. Return center coordinates
    bbox = match.element.bbox
    return TargetResult(
        x=bbox["x"] + bbox["width"] // 2,
        y=bbox["y"] + bbox["height"] // 2,
        element=match.element,
        match_score=match.score,
    )
```

**Matching algorithm — keyword extraction + fuzzy matching:**

```python
_STOPWORDS = frozenset({
    "the", "a", "an", "this", "that", "my", "your", "its",
    "in", "on", "at", "to", "for", "of", "with", "by",
    "big", "small", "large", "click", "find", "locate",
})

def _extract_keywords(self, description: str) -> list[str]:
    words = description.lower().split()
    return [w for w in words if w not in self._STOPWORDS]

def _best_match(self, description: str, elements: list[DetectedElement]):
    keywords = self._extract_keywords(description)
    if not keywords:
        return None

    scored = []
    for el in elements:
        label_lower = el.label.lower()

        # Keyword matching: how many keywords hit the label
        hits = sum(
            1 for kw in keywords
            if kw in label_lower
            or SequenceMatcher(None, kw, label_lower).ratio() > 0.6
        )
        text_score = hits / len(keywords)

        # Type bonus: "button", "link", "input" mentioned in description
        type_score = 1.0 if el.element_type in description.lower() else 0.0

        # Combined score, weighted by detection confidence
        score = ((text_score * 0.7) + (type_score * 0.3)) * el.confidence

        if score > 0.3:
            scored.append(_Match(element=el, score=score))

    return max(scored, key=lambda m: m.score, default=None)
```

**Rationale for keyword approach over whole-string fuzzy matching:**
- `SequenceMatcher("the blue Submit button", "Submit")` → low ratio (~0.4) due to extra words
- Keyword extraction: `["blue", "submit", "button"]` → "submit" matches "Submit" label with high confidence
- Type bonus: "button" matches element_type, adding 0.3 to score
- Stopword list is tiny (~20 words), hardcoded, no NLP dependency

**describe_action override:** `"Find element matching '{description}'"`

**Public ToolResult.data:**

```python
{
    "x": 450,
    "y": 320,
    "element": {"element_type": "button", "label": "Submit", "bbox": {...}, "confidence": 0.66},
    "match_score": 0.72,
}
```

---

## 7. Module Wiring (`vision/__init__.py`)

```python
"""Vision tools — auto-discovery imports."""

# Import modules to trigger @register_tool decorators.
# Import order does not matter — tools resolve siblings lazily via
# ToolRegistry.get() properties, not at import time.
from nobla.tools.vision import capture  # noqa: F401
from nobla.tools.vision import ocr  # noqa: F401
from nobla.tools.vision import detection  # noqa: F401
from nobla.tools.vision import targeting  # noqa: F401

# The shared element_cache singleton lives in cache.py (not here)
# to avoid circular imports. Tools import it directly:
#   from nobla.tools.vision.cache import element_cache
```

The parent `tools/__init__.py` adds:
```python
from nobla.tools import vision  # noqa: F401 — triggers @register_tool
```

---

## 8. Permission Model

All Phase 4A tools are STANDARD tier, no approval required:

| Tool | Tier | Approval | Rationale |
|------|------|----------|-----------|
| `screenshot.capture` | STANDARD | No | Read-only screen access |
| `ocr.extract` | STANDARD | No | Text extraction from image data |
| `ui.detect_elements` | STANDARD | No | Element detection from image data |
| `ui.target_element` | STANDARD | No | Coordinate resolution from image data |

**Principle:** All vision tools are read-only perception. No system state is modified. Phase 4B (mouse, keyboard) is where ADMIN tier + approval kicks in.

---

## 9. Error Handling & Graceful Degradation

| Condition | Behavior |
|-----------|----------|
| `python-mss` not installed | `screenshot.capture` returns error: "Install python-mss: pip install nobla[vision]" |
| `pytesseract` not installed | OCR falls back to EasyOCR |
| `easyocr` not installed | OCR uses Tesseract only. If also missing: clear install instructions |
| Tesseract binary not found | Fall back to EasyOCR with warning logged |
| EasyOCR Reader init fails | Fall back to Tesseract |
| UI-TARS model unavailable | Fall back to OCR-based detection (default behavior) |
| GPU unavailable | EasyOCR runs on CPU (`gpu=False`). Slower but functional. |
| Monitor index invalid | Validation error: "Monitor {n} not found. Available: 0-{max}" |
| Region out of bounds | Validation error with available screen dimensions |
| No elements match description | `ui.target_element` returns error: "No element matching '{desc}' found" |
| OCR returns no text | Empty blocks list, empty full_text. Not an error — screen may be blank. |
| Vision tools disabled | All 4 tools return error: "Vision tools disabled in settings" |

---

## 10. Testing Strategy

### Unit Tests (~250 lines)

**`tests/unit/test_vision_cache.py`:**
- Cache put/get with valid TTL
- Cache miss on expired TTL
- Cache miss on different screenshot hash
- Cache clear
- Thumbnail hash consistency (same image → same hash)

**`tests/unit/test_vision_capture.py`:**
- Mock `mss.mss()` → validate PIL.Image construction
- Region validation (negative values, out of bounds)
- Format validation ("png", "jpeg" valid; "bmp" invalid)
- Downscaling logic: 4K image → max_dimension=1920 → correct output size
- Native dimensions preserved in result
- `describe_action()` output format

**`tests/unit/test_vision_ocr.py`:**
- Mock `pytesseract.image_to_data()` → validate TextBlock construction
- Mock `easyocr.Reader.readtext()` → validate bbox conversion
- Confidence threshold filtering (blocks below threshold excluded)
- Fallback: mock Tesseract ImportError → EasyOCR used
- Fallback: mock EasyOCR ImportError → Tesseract used
- Both missing → RuntimeError with install instructions
- `describe_action()` output format
- `validate()` rejects missing/invalid `image_b64`

**`tests/unit/test_vision_detection.py`:**
- OCR-based detection with mock OCR results
- Element classification heuristics:
  - URL text → "link"
  - Text ending with ":" → "label"
  - Short text + distinct background → "button"
  - Tall text → "heading"
  - Default → "text"
- Pixel sampling mock (distinct background detection)
- Confidence discounting (block.confidence * 0.7)
- Detection threshold filtering
- UI-TARS stub raises → fallback to OCR-based
- Cache write after detection

**`tests/unit/test_vision_targeting.py`:**
- Keyword extraction: stopword removal
- Fuzzy matching: exact match → high score
- Fuzzy matching: partial match → medium score
- Fuzzy matching: type bonus ("button" in description)
- No match → ValueError
- Cache hit: skips detection, uses cached elements
- Cache miss: triggers full capture → detect pipeline
- `describe_action()` output format

### Integration Tests (~100 lines)

**`tests/integration/test_vision_tools.py`:**
- Full pipeline via WebSocket: `tool.execute("screenshot.capture", ...)` → ToolResult
- Full pipeline: `tool.execute("ocr.extract", {image_b64: ...})` → text blocks
- Full pipeline: `tool.execute("ui.detect_elements", {image_b64: ...})` → elements
- Full pipeline: `tool.execute("ui.target_element", {description: "Submit"})` → coordinates
- Permission check: SAFE tier user → cannot access vision tools (STANDARD required)
- `tool.list` includes all 4 vision tools for STANDARD tier
- Vision tools disabled via settings → error response
- All tests use mocked `mss`/OCR backends — no real screen capture in CI

---

## 11. Open Questions

1. **UI-TARS model selection** — Deferred from parent spec. Phase 4A ships with a stub. Model evaluation happens before enabling `ui_tars_enabled=True` in production.
2. **OCR-based heuristic accuracy** — The pixel sampling + text pattern approach is approximate. May need tuning after real-world testing. The confidence discount (0.7x) communicates this uncertainty to consumers.
3. **EasyOCR language model downloads** — EasyOCR downloads language models on first use (~50-200MB per language). Should we pre-download in setup, or let it happen lazily? Current design: lazy download with user notification.
