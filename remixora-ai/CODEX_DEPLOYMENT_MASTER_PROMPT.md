# REMIXORA AI — Original, Free-Tier-First, Deployment-Ready Codex Master Prompt

> **Use with Codex:** Unzip `remixora_deployment_starter.zip`, open its folder in Codex, and paste the following instructions (or tell Codex to read this file in full). This document is a build task, not a claim the finished product is complete.

## ROLE

You are the principal engineer, AI-agent architect, video-processing engineer, product designer, security engineer, DevOps engineer and QA lead for **REMIXORA AI**.

Build a *genuinely original* agentic **Media Content Repurposing Studio with Brand Memory** satisfying Product Space Agentic AI Hackathon **PS 01**. The product is creatively inspired by the category of video repurposing apps, including OpenShorts at https://github.com/mutonby/openshorts. Do **not** clone, copy proprietary/restricted code, reskin a third-party UI, or disguise reused source. Independently implement the architecture and UX, and maintain licensing notices for any third-party code actually incorporated. The starter repository was authored independently and contains no OpenShorts source files.

**Tagline:** One video. Infinite creative angles. One evolving brand voice.

The current repository is a *tested starter*, not the finished SaaS. Inspect code before making assumptions. Be honest about finished, partial, and missing features in the README and demo.

## NON-NEGOTIABLE USER CONSTRAINTS

1. **All six PS 01 requirements must work from one persistent end-to-end workflow:** media ingestion, explainable clip selection, platform-tailored copy, brand memory learned from edits, content calendar, and performance feedback that changes future suggestions.
2. **Strict free-tier-first:** zero required paid API keys, zero GPU rental, zero paid hosted databases, zero paid media generation, no forced paid model upgrade, no required credit-card spending. Use local FFmpeg for rendering and local open-source speech transcription if hardware permits. Support actual eligible Gemini free-tier text API or configured local Ollama as optional high-quality intelligence. Account quotas and free eligibility must be checked, not assumed. Never promise unlimited free service.
3. **Low-resource smoothness:** target a single 2-vCPU, 12-GB ARM64 Always Free VM when available, with a working x86-64 local Docker alternative. Keep `MAX_CONCURRENT_JOBS=1`, a single web worker for SQLite/job state, 150-MB upload cap, configurable 30-minute source cap, 720x1280 H.264 CPU exports, low-res preview, bounded model context, and cached outputs. Expensive automatic transcription is optional in container build; always support source-matched SRT/VTT import. Include a feasibility assessment for ARM64 Whisper dependencies; use whisper.cpp adapter if necessary.
4. **Deployability first:** persistent files and SQLite across restarts, container image, health checks, authentication, Caddy HTTPS, upload limits, reverse proxy, backups, documented DNS, logs, fault and restart recovery, smoke tests on the actual target CPU architecture. No hardcoded localhost in browser API calls.
5. **No fake functionality:** label heuristic suggestions, generated template copy, sample analytics, scheduled-in-app status, and optional unconfigured providers honestly. Don't say a post was published if it wasn't. Don't call a generic function an autonomous agent if it doesn't reason, use tools, and update persistent state.
6. **Privacy and security:** private source media, Basic Auth minimum for the hackathon single-user demo, HTTPS for public access, server-only API secrets, request validation, per-user quota prior to multi-tenancy, avoid logging private transcripts or keys, path traversal protection, upload inspection, rate limits, safe error handling, no arbitrary user-supplied URL fetching by default. Add GDPR-style export/delete later.
7. **Copyright and ethics:** process only user-owned or appropriately licensed media; respect source meaning; don't fabricate quotes, claims, or transformations; don't suppress open-source attribution when code is reused.

## REQUIRED PS 01 FEATURES — DEFINITION OF DONE

### Feature 1: Media Ingestion
- Upload MP4/MOV/WebM/MKV and MP3/M4A/WAV to local persistent storage, with stream-to-disk limits.
- FFprobe duration, tracks, codec, MIME/content type. Reject non-media, corrupt uploads, oversized sources, over-duration videos, missing audio, unsupported codecs.
- Transcribe automatically with **faster-whisper CPU int8** when supported on target hardware, else integrate **whisper.cpp** with small language-appropriate model where practical. Time-aligned SRT/VTT import is mandatory fallback (timestamp-free text is not sufficient for precise exports).
- Show job states `QUEUED → PROBING → TRANSCRIBING/ALIGNING → READY/TRANSCRIPT_REQUIRED/FAILED`; persist state across restarts.
- Save transcript segment start/end and exact quote as evidence; allow manual repair of segments before clip selection.

### Feature 2: Source-grounded, Explainable Clip Selection (Content Scout Agent)
- Define Pydantic schema with candidate ID, source ID, `start_ms`, `end_ms`, headline, topical hook, 0–5 rubric scores (clarity, usefulness, opening hook, brand relevance), evidence segment IDs, exact quote, and selection reason.
- Use eligible Gemini free-tier or Ollama to select source-aligned ranges from *numbered segments*, validating timestamps and quotes server-side. When no AI provider is available, fall back to labeled deterministic heuristics, not fictional AI analysis.
- Deduplicate near-overlapping candidates. Restrict short length (e.g. 15–60 sec by default) and prevent invalid source boundaries.
- Save model/provider provenance and reasoning **summary** (not private chain-of-thought) in event log.
- Apply real-world performance ranking when platform/angle sample size is adequate and show the numeric adjustment and evidence; a feedback update must change the ranking or score of a **new** source's recommendations in a reproducible test.

### Feature 3: Platform-Specific Repurposing (Copywriter + Remix Director)
- For each source clip, present three original editorial angles: **Teach It, Tell It, Challenge It** (contrarian only if transcript actually supports it).
- Generate truly distinct Instagram Reel, YouTube Short and LinkedIn copy for each angle: 3×3 outputs, grounded in the transcript. Provide hook, title, caption, CTA, hashtags when appropriate, source evidence, and Brand Fit explanation.
- Ensure drafts are reviewable and editable. Support copy-to-clipboard, actual export, one-click rollback, and clear `template` or provider provenance.
- Upgrade the starter to actually render a *remix-specific* MP4: at minimum a distinct on-video opening headline, burned-in subtitle option, and consistent branding template applied to original footage. Only label results video remixes if their output files differ. No fabricated scenes, faces, or voices.
- The default physical video export must remain local FFmpeg. Do not depend on proprietary GPU clip APIs.

### Feature 4: Brand DNA Memory (Brand Curator Agent)
- Persist creator preferences: audience, tone, formality, sentence length, CTA pattern, emoji/hashtag preferences, banned phrases, preferred vocabulary, language, revision number.
- Record `{AI draft, human edit, diff, evidence copy ID, inferred rule, pending/approved status}` for every edit.
- A bounded AI agent proposes a specific rule from an actual before/after edit. When cloud/offline model unavailable, deterministic inference handles at least shortened copy, question-first openings, removal of hype, hashtag removal, and vocabulary preference. Never silently auto-approve an inference.
- On user approval, save versioned rule and apply it to a **different, newly generated** clip. UI highlights exact memory rules used in copy. Test before/after texts are materially different.
- Avoid regurgitating the old caption in unrelated future contexts. Show rule evidence and allow deactivate/delete.

### Feature 5: Real Persistent Content Calendar (Calendar Agent)
- Human approval-gated scheduling: clip, platform, editable caption, date/time, IANA timezone, draft/approved/scheduled-in-app/manually-published states.
- Persistent month/week/list views with filters; detect conflicting slots and prompt user to adjust; allow rescheduling and canceling.
- Optional external posting integrations may be stubbed as disabled, not simulated. Show clear notice that scheduling in REMIXORA does **not** auto-publish.
- Persist after restart and include in exportable product demo.

### Feature 6: Performance Feedback Loop (Performance Learner)
- Import actual CSV with clip ID, platform, angle, publication time if known, impressions, views, likes, comments, shares, saves, optional watch-time; validate numeric data and missing fields.
- Use a transparent metric such as engagement rate = (likes+comments+shares+saves)/impressions, where impressions>0; use smoothing and per-platform normalization. Never compare incomparable periods or label a guess as a measurement.
- Use sample-size minimum (at least three comparable posts per angle for MVP), display count, confidence caveat, base score, adjustment and updated rank on **future** clip recommendations.
- Include a labeled synthetic CSV for demonstration only. Do not invent actual campaign performance or performance lift.
- Add automatic incremental analytics revision to invalidate ranking caches while retaining immutable historical records.

## AGENTIC WORKFLOW — SIX SPECIALIZED AGENTS

Create `/app/agents/` (or choose equally simple original paths) with a typed, testable agent contract:

- **1. Ingestion Agent:** validate media, segment and transcribe source using FFmpeg/Whisper tools; call no cloud model unless user explicitly enables it.
- **2. Content Scout Agent:** retrieve transcript windows, brand rules, historic analytics, call an optional text AI model, validate candidate segments, and explain shortlisting.
- **3. Remix Director:** plan three truthful editorial treatments; use FFmpeg tools to produce different actual outputs when rendering.
- **4. Platform Copywriter:** synthesize platform-tailored copy while applying brand rules, with source facts validation and structured JSON.
- **5. Brand Memory Curator:** compare edits, propose grounded style rules, require approval, increment memory revision, influence next draft.
- **6. Calendar + Feedback Agent:** propose content slots and analyze imported post outcomes, change future ranking weights, never auto-publish without real integration and approval.

You may combine the last two into separate agents for clear separation. The orchestrator must store real states, tool calls, job IDs, retry policy, provider/fallback, status, and timestamps in SQLite. Use deterministic code for I/O, FFmpeg, SQL, numeric analytics, and approval gates. AI output must never bypass validation. A model prompt is not a durable workflow engine.

**Suggested agent tool contract** (implement with Pydantic; names may differ):
`probe_media`, `transcribe_media`, `get_transcript_segments`, `get_brand_rules`, `get_platform_analytics`, `validate_clip_proposal`, `rank_candidates`, `render_video_clip`, `generate_platform_copy`, `suggest_brand_rule`, `request_human_approval`, `save_calendar_entry`, `import_metrics`, `compute_engagement_summary`, `record_agent_event`.

**Orchestrator states:** `UPLOADED`, `PROBING`, `TRANSCRIBING`, `READY_FOR_SCOUT`, `DISCOVERING`, `CANDIDATES_READY`, `REMIX_DRAFTS_READY`, `AWAITING_APPROVAL`, `RENDERING`, `RENDERED`, `SCHEDULED_IN_APP`, `PERFORMANCE_UPDATED`, `FAILED`, `RETRYABLE_FAILED`.

## DATABASE & STORAGE

Inspect existing `app/db.py`; migrate incrementally without destructive recreation. Maintain foreign keys and indexes. Tables: `creators`/single-user profile, `media_assets`, `transcript_segments`, `clip_candidates`, `remix_variants`, `platform_copies`, `edit_history`, `brand_rules`, `calendar_items`, `post_analytics`, `performance_insights`, `jobs`, `agent_events`, `provider_cache`.

Persistence settings: SQLite WAL; volume-mounted `/data`; file ownership uid 10001; `PRAGMA foreign_keys=ON`; safe constraints; upload and export paths resolved within volume; checksum/idempotency keys; no accidental duplicates after retries. Add schema migration version and backup/restore scripts. Limit retained original video size and allow deletion after successful export, with explicit confirmation.

## AI PROVIDER ROUTING / ZERO-COST POLICY

- Config: `AI_PROVIDER=auto|gemini|ollama|none`, `GEMINI_API_KEY`, `GEMINI_MODEL` (not hardcoded to an ineligible paid-only model), `OLLAMA_URL`, `OLLAMA_MODEL`, max request time, token budget, rate limit, retry limit (<=2).
- Prefer eligible free Gemini text access *only when configured* and allowed. If API returns 401/403/429/5xx, respect provider guidance, retry transient failures at most twice, move to healthy configured Ollama; if none, continue with explicitly labeled deterministic heuristics/templates.
- Cache by transcript/source checksum + provider + model + prompt version + brand revision + performance revision. Window long transcripts; do not send entire huge video to a model. No external payment method needed for mandatory functionality.
- Avoid assuming the Google free tier covers private data; display provider privacy disclosure and offer local-only path. Never put keys in frontend or commit them.
- Gate automatic Whisper model downloads to deployment setup; first use may take minutes on CPU. Treat hardware limitations honestly.

## USER EXPERIENCE — DISTINCT REMIXORA DESIGN

Build a unique and consistent responsive interface, not a copied OpenShorts dashboard:
- Dark obsidian/navy background with muted lavender + teal highlights, generous whitespace, compact typography, accessible contrast.
- Navigation: Studio Home, Ingest, Clip Scout, Remix Lab, Brand DNA, Content Calendar, Feedback Lab, System Health.
- Main experience: source video panel + transcript timeline, evidence card explaining selected moments, creative angle comparison, editable generated captions, approval and provenance, real export download, creator voice preferences, and before/after recommendation evidence.
- No decorative buttons without behavior. No fake placeholder numbers presented as actual data.
- Implement usable progress states, processing messages, background polling, error retry, empty states, upload limits, storage diagnostics, feedback on action results.
- Don't auto-enable paid services or attach additional telemetry.

## PRODUCTION-READY FREE CLOUD DEPLOYMENT

**Primary recommended hosting:** Oracle Cloud Always Free Ampere A1, within *current verified free limits*, if VM capacity available. Current documentation lists the free allowance equivalent to 2 OCPUs / 12 GB RAM and combined 200 GB block volumes. Do NOT claim guaranteed availability. Read official resource docs before provisioning.

**Fallback:** Local Docker + optional exposure through a carefully configured secure tunnel or DNS/reverse proxy for temporary judging demonstrations. No permanent free uptime promised.

**Avoid:** Render Free for video workers due to sleeping/ephemeral disk. Avoid Vercel serverless functions for FFmpeg plus large video transcriptions. Avoid relying on an ephemeral-only SQLite filesystem.

**Docker:** one application container + optional `caddy:2-alpine` reverse proxy. Compose volume `./data:/data`, single worker, health check, restart policy, environment secrets loaded from `.env`, non-root UID, CPU and RAM controls. Proxy must terminate HTTPS for real DNS; open only 80/443 on cloud; app's port binds loopback. Basic Auth strong credentials mandatory in production; later add proper user accounts and CSRF protection.

**Process management:** move in-memory ThreadPoolExecutor media jobs to a *SQLite-backed durable job queue* with single worker and restart recovery. Persist transitions with failure messages and retry counter. Atomic file writes and transactional updates. Avoid 20 concurrent FFmpeg jobs on free CPUs.

**CLI runbook:** `cp .env.example .env`, choose secrets, `docker compose up --build -d` for local; `docker compose --profile public up --build -d` after DNS setup for cloud. Include ARM64-specific dependency test, `docker compose ps`, `docker compose logs -f`, `curl /health`, volume persistence test, HTTPS test, export test, analytics update test, backup/restore test. Explain free-tier CPU time, latency and limits.

**Caddy:** validate DNS record and VM firewall. Add security headers, body-size bound, compression and access logs with no sensitive payload. Do not expose private video files unauthenticated.

## ENGINEERING SPRINTS — DO ACTUAL WORK, NOT JUST A PLAN

### Phase 0 — Audit and baseline
1. Read all relevant files and `CODEX_DEPLOYMENT_MASTER_PROMPT.md`.
2. Run `python -m compileall -q app` and `python -m pytest -q`.
3. Inspect FastAPI routes, media formats, FFmpeg calls, SQLite schema, free provider, static UI and Dockerfile.
4. Create/update `AGENTS.md` documenting conventions, API contracts, source validation, no fabricated features, license requirements and tests.
5. Produce `BASELINE_AUDIT.md`: verified working / partially working / missing, with file paths and reproduction commands.

### Phase 1 — Reliable media ingestion and jobs
- Add structured job states and durable worker, concurrency 1, status polling and real recovery after restart.
- Improve MIME/codec validation and SRT/VTT time alignment, optional supported CPU whisper.cpp/faster-whisper backend with no GPU required.
- Ensure safe upload constraints, progress UI, error handling, and a working MP4/M4A export.
- Verify on real source, not mock media path. Run tests.

### Phase 2 — Real agentic Content Scout
- Implement model-powered source-grounded clip selection with Pydantic JSON validation, segment index checks, overlap/duration checks, deterministic scoring and an evidence timeline.
- Keep offline heuristic selection as clearly labeled fallback. Show which provider was used.
- Demonstrate 3 meaningful candidate moments from a real 5–10-minute video and at least one playable export. Run tests.

### Phase 3 — Original Remix Lab and Brand DNA
- Add three editorial treatments × three platforms, unique source-grounded hooks/titles/CTAs, and actual distinct on-video hook/subtitle variants if promising real media remixes.
- Implement edit history, specific inferred memory rules, human approval, version changes, and *new* generation affected by approved rules.
- Add brand fit evidence panel and persist across server restart. Run tests.

### Phase 4 — Calendar and Performance adaptation
- Build calendar month/list UI; validate schedule timezone; support edit, cancel, status changes with human approval.
- Import metrics with schema validation and source labels; calculate rates/smoothing within platform. Change future ranking, not just append an explanation. Show old vs new score for two simulated future sources under a controlled test. Run tests.

### Phase 5 — Production hardening and deployment
- Health checks, single job worker, persistent volumes, graceful shutdown, storage quota, backups, password gating, HTTPS, basic security headers, error logging, secrets, restore test.
- Validate Docker build on `linux/arm64` or actual OCI VM; if faster-whisper wheels fail, document and implement compatible whisper.cpp.
- Test 3 consecutive uploads sequentially, FFmpeg output integrity, simulator of free API 429, fallback, process restart, full refresh persistence, actual user edits, analytics rank changes.
- Deploy only after target VM/resource check. Do not claim deployment complete unless URL works and all steps are verified.

### Phase 6 — Hackathon presentation
- README: exact free vs optional constraints, how to launch, original features, limitations, copyright notices, architecture diagram, measured demo metrics.
- Record a ≤3-minute live-demo workflow: upload → three source-grounded clips → real MP4 export → three editorial angles → edit caption → approve learned rule → new generation changes → calendar schedule → import sample-labeled analytics → future suggestions re-rank.
- Prepare truthful side-by-side comparisons with general repurposing tools; never claim comparative superiority without direct testing.

## MANDATORY TEST SUITE

- Unit tests: SRT/VTT parsing, bad timestamps, malformed video, size limits, deterministic selection, quote/time validation, clip overlaps, copy format, inferred rules, scoring math, invalid CSV, permissions, schedules.
- Integration tests: upload real small test video + SRT → ready → AI/heuristic candidates → FFmpeg output decodes → edit and approve brand rule → different clip output changes → calendar persists → metrics imported → **new** clip ordering/score changes.
- Resilience tests: no API key; local model offline; Gemini 429/5xx; corrupt video; bogus file extension; 500-MB upload rejection; zero speech; process crash and recovery; disk space unavailable; restarted Docker with retained SQLite and files.
- Deployment tests: Docker build, ARM64 build/runtime if claimed, Caddy HTTPS, authenticated access, API key never in browser assets, port 8000 not public, health endpoint, `docker compose restart`, backups, public URL verification.
- Performance tests on actual target hardware: one representative 5–10-minute source; measure memory peak and clip render wall time; optimize to stay within free quotas. Never fabricate benchmarks.

## DEFINITION OF DONE / RELEASE BLOCKERS

**A version is demo-ready only if:**
1. An actual uploaded user-owned media file with timestamped transcript is ingested.
2. At least three source-grounded clips with reasons are identified, with AI or heuristic provenance.
3. At least one MP4 export is valid and playable; if video remix claims are shown, two actual variant files differ.
4. Three platforms have genuinely distinct copies for three angles.
5. A creator edit creates a pending brand-memory inference, creator approval is recorded, and **next** generation demonstrably reflects it.
6. An approved draft can be scheduled and survives restart, without implying it posted externally.
7. Imported metrics change future ranked candidates and the app visibly explains the data and sample size.
8. There is a fully verified no-paid-API local path; optional Gemini free tier works only if legitimately configured/eligible.
9. All errors, rate limits, and out-of-memory hazards are handled. Deploy credentials, media and DB are protected.
10. Test logs, deployment evidence and README accurately match observed behavior.

**Start now:** inspect the existing project, run tests, create `BASELINE_AUDIT.md` and `AGENTS.md`, then implement Phase 1 in code and test it. Continue incrementally until release blockers are cleared. Avoid stopping after high-level architecture notes. When blocked by unavailable credentials/VM hardware, complete everything verifiable locally, identify precisely what remains unverified, and do not claim a cloud deployment or quota guarantee.
