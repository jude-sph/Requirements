# Web Frontend — Design Spec

## Overview

A lightweight single-page web frontend for the Requirements Decomposition System. Built with FastAPI + Jinja2 + vanilla JS + SSE. Launched via `reqdecomp --web`. No Node.js or build step required.

**Audience:** Team members who have API keys but prefer a browser over the CLI.

## Architecture

A thin FastAPI server wrapping the existing `src/` modules. No new decomposition logic — the web layer calls `decompose_dig`, `apply_vv_to_tree`, `validate_tree_structure`, `run_semantic_judge`, and `refine_tree` directly.

```
Browser (single page)
  │
  ▼
FastAPI (src/web/app.py)
  │
  ├── POST /upload          Upload xlsx file
  ├── POST /run             Start processing (returns job ID)
  ├── GET  /stream/{job_id} SSE endpoint for live progress
  ├── GET  /results         List completed DIGs
  ├── GET  /results/{id}    Get single DIG tree as JSON
  ├── GET  /export          Download xlsx
  ├── GET  /settings        Get current config
  ├── POST /settings        Update model/API keys
  ├── POST /dry-run         Estimate cost
  └── GET  /                Serve the single page
```

## Single Page Layout

Four sections stacked vertically:

### 1. Header Bar
- Logo + version
- Current model indicator (e.g. "Claude Sonnet 4.6" with green dot)
- Settings gear icon → opens modal

### 2. Input Section
- Drag-and-drop xlsx upload area (shows filename + DIG count when loaded)
- Depth slider (1-4, default 4)
- Breadth slider (1-5, default 3)
- V&V checkbox (default: on)
- Judge checkbox (default: on)
- DIG ID text input (comma-separated, or blank for all)
- "Run" button (green)
- "Est. Cost" button (runs dry-run, shows estimated cost in a toast)

### 3. Progress Section
- Only visible during processing
- Current DIG label + overall progress (e.g. "DIG 9646 [2/3]")
- Progress bar with phase description (e.g. "Generating V&V for 3 requirements...")
- Running cost display
- Cancel button
- Uses Server-Sent Events (SSE) for real-time updates

### 4. Results Section
- Summary line: "3 DIGs, 15 requirements"
- "Download XLSX" button
- List of DIG result cards (collapsible):
  - Header: DIG ID, short description, level count, node count, cost
  - Expanded: requirement tree with colour-coded levels
    - L1: purple, L2: blue, L3: orange, L4: green
  - Click a tree node → expands to show: full requirement text, rationale, allocation, chapter, system hierarchy, V&V data, confidence notes, judge feedback
- Results persist across page reloads (loaded from output/json/ on page load)

### Settings Modal
- Model picker — reuses the `MODELS` list from `scripts/configure.py` (import it, don't duplicate)
- API key fields (Anthropic + OpenRouter)
- Save button → writes to the package-root `.env` file (same location as `scripts/configure.py`)
- After save, the backend reloads config values in-memory (see Config Reload below)
- Shows current config on open

## Processing Flow

### Single/Few DIGs (real-time)
1. User enters DIG IDs, clicks Run
2. Frontend POSTs to `/run` with DIG IDs + settings
3. Backend starts async processing, returns job ID
4. Frontend connects to `/stream/{job_id}` SSE endpoint
5. Backend streams events: `{"phase": "decompose", "level": 1, "dig_id": "9584", "progress": 0.25}`
6. Frontend updates progress bar in real-time
7. On completion, frontend fetches results and renders tree

### Batch (all DIGs)
1. User leaves DIG input blank, clicks Run
2. Same flow but progress shows per-DIG completion
3. Results appear incrementally as each DIG completes

### SSE Event Types
```json
{"type": "started", "total_digs": 3, "job_id": "abc123"}
{"type": "dig_started", "dig_id": "9584", "index": 1, "total": 3}
{"type": "phase", "dig_id": "9584", "phase": "decompose", "detail": "Level 2"}
{"type": "phase", "dig_id": "9584", "phase": "vv", "detail": "3 requirements"}
{"type": "phase", "dig_id": "9584", "phase": "judge", "detail": "reviewing"}
{"type": "phase", "dig_id": "9584", "phase": "refine", "detail": "5 issues"}
{"type": "cost", "total_cost": 0.15, "api_calls": 4}
{"type": "dig_complete", "dig_id": "9584", "nodes": 5, "levels": 3, "cost": 0.20}
{"type": "complete", "total_digs": 3, "total_nodes": 15, "total_cost": 0.52}
{"type": "error", "dig_id": "9584", "message": "API call failed"}
```

## File Structure

```
src/web/
├── app.py              # FastAPI app, all routes, SSE logic, job management
├── templates/
│   └── index.html      # Single page (Jinja2 template)
└── static/
    ├── style.css       # All styles
    └── app.js          # Client-side JS: SSE, tree rendering, uploads, modals
```

## Job Management

Simple in-memory job tracking (no database):

```python
jobs: dict[str, Job] = {}

class Job:
    id: str
    status: str           # "running", "complete", "error", "cancelled"
    dig_ids: list[str]
    settings: dict        # depth, breadth, skip_vv, skip_judge
    progress: list[dict]  # SSE events (append-only)
    results: list[str]    # completed DIG IDs
```

Jobs run via `asyncio.to_thread()` (thread pool executor) because the existing pipeline functions (`decompose_dig`, `apply_vv_to_tree`, etc.) are synchronous and make blocking HTTP calls. Running them directly in an async task would block the event loop and prevent SSE streaming.

**Cancellation:** The `Job` object has a `cancelled: bool` flag. The pipeline is wrapped in a function that checks `job.cancelled` between major steps (after each DIG, after each phase). If set, processing stops and the job status becomes `"cancelled"`. This is coarse-grained (won't interrupt a running API call) but sufficient.

## Config Reload

`config.py` sets `MODEL`, `PROVIDER`, `ANTHROPIC_API_KEY`, etc. as module-level constants at import time. When the settings modal saves to `.env`, the backend must reload these values. Implementation: `app.py` provides a `reload_config()` function that re-reads `.env` via `dotenv` and updates the module-level variables in `src.config` directly (`src.config.MODEL = new_value`). This avoids requiring a server restart.

## Upload Handling

- xlsx uploaded via drag-and-drop or file picker
- Saved to working directory (overwrites existing)
- Upload is blocked if a job is currently running (returns 409 Conflict)
- Backend loads it and returns DIG count
- File persists across server restarts

## Dry Run

`POST /dry-run` accepts the same parameters as `/run` (DIG IDs, depth, breadth, skip flags). It reuses the existing cost estimation formula from the CLI (worst-case node count calculation), not an actual LLM call. Returns estimated call count and approximate cost.

## Dependencies

Add to existing:
```
fastapi>=0.100.0
uvicorn>=0.20.0
python-multipart>=0.0.5
jinja2>=3.1.0
```

## CLI Integration

`--web` joins the existing mutually exclusive argument group (`--dig`, `--all`, `--export-only`, `--setup`, `--web`). You cannot combine `--web` with other modes.

```bash
reqdecomp --web                    # Start on http://localhost:8000
reqdecomp --web --port 3000        # Custom port
```

Static files served via FastAPI's `StaticFiles` mount. No CORS needed (localhost only).

## Depth Slider

The depth slider is hard-capped at 4 (matching `LEVEL_NAMES` which only defines levels 1-4). The breadth slider caps at 5.

## Export

`GET /export` exports all JSON files in `output/json/` to xlsx (same as CLI `--export-only`). Returns the xlsx file as a download.

## Out of Scope

- Authentication (team tool, local network)
- Persistent job history (JSON files are the record)
- Multi-user concurrent jobs (single user assumed)
- Editing requirements in the browser
