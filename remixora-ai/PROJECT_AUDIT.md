# REMIXORA AI — Full Project Audit & Architecture Refactor Plan

**Audit Date:** 2026-11-21  
**Project:** REMIXORA AI — Agentic AI Media Content Repurposing Studio with Brand Memory  
**Author:** Principal Full-Stack Engineer & Software Architect  

---

## 1. Current Architecture

### 1.1 Backend & Engine
- **Framework:** FastAPI running under Uvicorn (single-worker ASGI architecture).
- **Database:** SQLite 3 with Write-Ahead Logging (`PRAGMA journal_mode=WAL`) and foreign keys enabled (`PRAGMA foreign_keys=ON`). Located at `DATA_DIR/remixora.sqlite3`.
- **Background Worker:** `DurableWorker` in `app/jobs.py` running in a dedicated background daemon thread. It polls the `jobs` table with `BEGIN IMMEDIATE` transactions and updates state.
- **Media Processing:** FFmpeg and FFprobe binaries bundled in `.tools/ffmpeg/ffmpeg-9.1-essentials_build/bin/` or resolved from `PATH`.
- **Transcription:** `faster-whisper` (`.tools/python`), local SRT/VTT parser in `app/media.py`, or YouTube caption extraction in `app/youtube.py`.
- **AI Providers:** Optional Gemini (`google-genai` / `gemini-3.1-flash-lite`) and local Ollama with deterministic offline heuristic fallback.

### 1.2 Storage Layout (Legacy)
```text
data/
├── remixora.sqlite3
├── uploads/
│   └── {asset_id}.mp4 / {asset_id}.mov / etc.
└── exports/
    └── {target_id}.mp4 / {target_id}.partial.mp4
```
- Flat unstructured files: uploads and exports are intermingled in global directories without project-level isolation or subfolders.
- Temporary files during rendering are created alongside completed outputs as `.partial.mp4`.

### 1.3 Database Schema (Legacy)
- `assets`: Original uploaded or imported media.
- `segments`: Transcript cues associated with an asset.
- `clips`: Unified table storing both discovered editorial candidates and rendered clips (identified only by `render_status`).
- `preset_runs` & `preset_candidates`: Tracking for the 12 smart presets, linking runs to `asset_id` and candidates to `clips.id`.
- `variants`: Vertical branded renders linked to `clips.id`.
- `workflows`: Ingestion workflow tracking linked to `asset_id`.
- `copies`, `edits`, `brand_rules`, `calendar`, `metrics`, `agent_events`, `profile`, `revisions`, `jobs`.

### 1.4 Frontend Architecture
- Zero-build vanilla HTML5/ES6+ SPA delivered via FastAPI `StaticFiles` at `/static/`.
- Managed by `app.js`, `smart.js`, `workflow.js`, and `product.js`.
- State managed globally through `state` object and `location.hash` routing (`#home`, `#ingest`, `#smart`, `#remix`, `#brand`, `#calendar`, `#feedback`, `#health`).

---

## 2. Confirmed Problems & Root Causes

| Problem | Symptoms | Root Cause |
| :--- | :--- | :--- |
| **No Project Entity** | Uploads appear as raw assets or workflows. No cohesive "project" entity links sources, candidates, and renders. | The database lacks a `projects` table; `assets` and `workflows` were treated as disparate records without a parent project abstraction. |
| **Clips & Renders Confused** | Users cannot distinguish between an AI-suggested moment and a rendered MP4 file. The same card shows "Preview source" and "Play export". | Candidate proposals and rendered outputs share the `clips` table and UI components. Previews seek original video instead of streaming rendered outputs. |
| **Unorganized File Storage** | Files saved flatly in `uploads/` and `exports/`. No per-project isolation or structured folders. | Code directly uses `UPLOADS / (asset_id + ext)` and `EXPORTS / (clip_id + '.mp4')`. |
| **Lost Project Context** | Navigating between Library, Smart Cuts, and Remix loses the active source and preset runs. | State depends on scattered `localStorage` keys (`remixora-source`, `remixora-clip`, `remixora-preset-run`) rather than URL-driven `#projects/{project_id}` routing. |
| **Overwritten Preset Runs** | Re-running presets or switching filters can obscure previous candidate batches. | Preset candidates were partially coupled to generic `clips` rows without isolated run grouping in workspace views. |
| **Render Previews Play Source Media** | Clicking preview on suggested clips plays the raw source media rather than verifying the rendered MP4. | UI reused `<video src="/api/assets/{id}/media">` with timecode offsets instead of pointing to a dedicated rendered MP4 streaming endpoint. |

---

## 3. Existing Functionality to Preserve
1. **12 Smart Editing Presets:** Funny Moments, Best Highlights, Best Talking Moments, Reactions, Fail Moments, Clutch Moments, Funny Clips, Motivation, Cinematic, Key Takeaways, Remove Silence, Shorts / Reels.
2. **Deterministic & Model-Based Intelligence:** Gemini 3.1 Flash Lite integration with heuristic fallback.
3. **Local FFmpeg Pipeline:** Silence detection EDL, vertical 9:16 / 1:1 cropping, subtitle burn-in, audio extraction.
4. **Brand DNA Memory:** Editable copy diffing, automatic preference inference, rule approval lifecycle.
5. **Multi-Platform Content Studio:** Instagram Reel, YouTube Short, LinkedIn variations for each moment.
6. **In-App Calendar & Scheduling:** Timezone-aware conflict detection and status tracking.
7. **Performance Analytics & Feedback Loop:** CSV import, lifetime/smoothed engagement calculation, score adjustments.
8. **Durable Worker Queue:** Resilient crash recovery, job retry mechanism, SQLite WAL persistence.

---

## 4. Proposed Target Architecture

### 4.1 Target Storage Structure
Isolated per-project directory layout under `storage/projects/{project_id}/`:
```text
storage/
└── projects/
    └── {project_uuid}/
        ├── sources/
        │   └── original{ext}
        ├── thumbnails/
        │   ├── cover.jpg
        │   └── {render_uuid}.jpg
        ├── transcripts/
        │   ├── original.json
        │   └── original.srt
        ├── preset-runs/
        │   └── {preset_run_uuid}/
        │       └── metadata.json
        ├── renders/
        │   ├── {render_uuid}.mp4
        │   └── {render_uuid}.jpg
        ├── exports/
        └── temp/
```

### 4.2 Target Database Schema
Additive, non-destructive migration introducing:
- `projects`: Primary container entity (`id`, `title`, `thumbnail_path`, `status`, `created_at`, `updated_at`).
- `media_sources`: Source files linked to `project_id`.
- `clip_candidates`: AI-discovered candidate proposals linked to `project_id` and `preset_run_id`.
- `rendered_clips`: Successfully rendered, verified video files (`id`, `project_id`, `candidate_id`, `file_path`, `thumbnail_path`, `duration`, `aspect_ratio`, `status`, `created_at`).
- Backward-compatible foreign keys and views linking `assets`, `clips`, `preset_runs`, and `variants`.

### 4.3 Target UI Workspace (`/projects/{project_id}`)
A unified project workspace with 8 distinct tabs:
1. **Overview:** Project metadata, source summary, quick action cards, processing pipeline status.
2. **Original Media:** High-resolution source player, synchronized transcript browser, metadata inspector.
3. **AI Presets:** Preset configuration and execution console for all 12 presets.
4. **Suggested Clips:** Candidate cards clearly labeled **SOURCE PREVIEW**, showing AI evidence, timestamps, and "Render Clip" action.
5. **Rendered Clips:** Dedicated gallery of completed, verified MP4 renders with full playback modal, seeking, download, and copy generation.
6. **Content Studio:** 3 platform-specific copy angles (Instagram, YouTube, LinkedIn) linked to Brand DNA.
7. **Content Calendar:** Project-filtered scheduling board with time slots and platform previews.
8. **Analytics:** Clip performance metrics and engagement attribution.

---

## 5. Database Migration Plan
1. **Additive Schema Updates:** Execute `CREATE TABLE IF NOT EXISTS projects ...`, `media_sources`, `clip_candidates`, and `rendered_clips`.
2. **Data Backfill:**
   - For every existing row in `assets`, create a corresponding `projects` record using its `filename` as the title.
   - Insert corresponding `media_sources` records pointing to the asset's media path.
   - Migrate existing candidate `clips` into `clip_candidates`.
   - Migrate rendered clips (where `render_status = 'rendered'` or associated with `variants`) into `rendered_clips`, verifying actual file presence on disk.
3. **Foreign Key Alignment:** Ensure all `preset_runs`, `copies`, `calendar`, and `metrics` retain their relationships to projects and clips.
4. **Data Safety Guarantee:** Zero record deletion; fallback views preserve legacy endpoints.

---

## 6. Implementation Order
- **Phase 1:** Schema & Storage Infrastructure (models, directory isolator, additive migration).
- **Phase 2:** Project Creation & Ingestion API (file uploads & YouTube imports creating projects).
- **Phase 3:** Background Rendering Queue & Verification (isolated FFmpeg render pipeline, thumbnail generation, range-request streaming).
- **Phase 4:** RESTful Project APIs (backward-compatible `/api/projects/*` endpoints).
- **Phase 5:** Frontend Workspace & Dashboard Refactor (Projects Dashboard, 8-tab Project Workspace, separated Suggested vs Rendered tabs, playable preview modal).
- **Phase 6:** Full Automated Testing & Verification (covering all 14 test scenarios).

---

## 7. Risks & Rollback Plan
- **Risk:** Existing rendered clips or assets become inaccessible if paths change abruptly.
  - *Mitigation:* File migration will copy/link paths without deleting legacy files in `data/uploads` and `data/exports`. Both relative and absolute paths will resolve safely.
- **Risk:** Database migration locks during concurrent operations.
  - *Mitigation:* Migration is run during application startup inside an immediate transaction with additive checks.
- **Rollback:** `DB_FILE` is backed up before running migrations to `remixora.sqlite3.bak`. If any migration step fails, the backup is restored seamlessly.
