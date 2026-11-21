# Verification report — 2026-11-21

## YouTube and guided workflow update

Final regression: **42 passed in 27.86 seconds**, with `python -m compileall -q app scripts`, both JavaScript syntax checks, and `test-results/pytest-workflows.xml`. The earlier 21-test baseline below is retained as historical evidence.

- Added strict HTTPS YouTube URL normalization, prohibited-host/playlist rejection, bounded downloads, caption normalization and actionable unavailable-video errors.
- Real downloader smoke: Blender Foundation's publicly available *Big Buck Bunny* video downloaded successfully: **634.624 seconds**, **102,240,387 bytes**, **39.72 seconds** on this connection. No captions were available on that test source. The older yt-dlp test video was unavailable and correctly returned an actionable error. Live caption acquisition is not separately claimed; normalization and caption-to-workflow integration use fixtures.
- Installed and exercised the local tiny faster-whisper CPU int8 model. Direct transcription of a 25.091-second original synthetic narration segment produced five segments in **8.22 seconds**. This is a simple fixture, not a multilingual accuracy or throughput benchmark.
- Browser file selection and upload succeeded with `demo/part-01.wav` and **no SRT**. After fixing the decoder compatibility error, Retry workflow resumed the same project: local transcription → one informative clip → nine labeled template drafts → one captioned **720×1280 MP4**. The 300,763-byte download was decoded successfully with FFmpeg. Metadata and SHA-256 are in `test-results/automatic-workflow-live.json`.
- Fixed faster-whisper/PyAV 19 incompatibility by pinning the exercised PyAV 16.0.1 dependency. Fixed final speech-cue rounding beyond EOF while keeping imported caption validation strict.
- New integration coverage includes real FFmpeg automatic exports, idempotent project creation, missing-caption pause/import/resume, enabling speech after a pause, source-bound speech timing, permission/options validation and restricted-download recovery. External YouTube download is mocked only inside the deterministic integration suite; the separate download above was live.
- Verified source tabs, clip count/objective controls, browser upload, retry, finished preview, API configuration dialog, saved project reopening and New project navigation. No console errors in the final browser pass. Desktop width 1440 and mobile width 390 both fit without horizontal overflow (document widths 1425 and 375 respectively).
- Screenshots: `test-results/create-clips-desktop.jpg` and `test-results/create-clips-mobile.jpg`.
- Gemini/Ollama remain unconfigured. Speech uses a real local model; editorial selection and writing stay visibly labeled heuristic/template until a text provider is configured. No API key is needed for local speech, import or exports. No external publishing occurred.

## Release scope

Verified **native Windows x86-64 local deployment**, Python 3.12.10, one Uvicorn worker, SQLite WAL, local FFmpeg/FFprobe. Live URL: http://127.0.0.1:8000. This is a local creator studio, not a claim of public SaaS readiness.

## Automated checks

- `python -m compileall -q app scripts` — passed.
- `node --check app/static/app.js` — passed.
- `python -m pytest -q --durations=3 --junitxml=test-results/pytest.xml` — **21 passed in 14.94 seconds**.
- One upstream Starlette/AnyIO deprecation warning; no test failures.

Coverage includes:

1. SRT/VTT parsing, malformed timestamps, cue overlap and absent timestamps.
2. Actual small FFmpeg video upload, source probing, evidence-linked discovery and nine distinct platform/angle drafts.
3. Two real remix MP4s decoded by FFmpeg with different SHA-256 hashes.
4. Caption edit → specific pending inference → explicit approval → different clip's new drafts materially changed.
5. Copy approval gate, timezone validation, slot conflicts and calendar database persistence.
6. Deduplicated actual metrics → changed scores on **two new sources**; historical recommendations unchanged.
7. Corrupt media, bogus extensions, declared 500 MB payload rejection, text playlists rejected before FFprobe/network access, and storage quota rejection.
8. Basic authentication on private routes, unauthenticated health, cross-origin write rejection.
9. Durable interrupted-job recovery, bounded attempt count and three consecutive audio uploads.
10. Missing transcription configuration returns an actionable transcript-required state.
11. Gemini 429 simulation → bounded retry → configured Ollama response; persistent provider cache avoids repeat requests.
12. SQLite backup/restore integrity and prevention of overwriting an existing restore destination.
13. Deterministic brand profile controls and exact-quote vocabulary protection.
14. Synthetic CSV labels cannot be overridden as actual data; synthetic samples never change future actual recommendations.
15. Storage diagnostics tolerate SQLite WAL/SHM files disappearing while the UI polls.

## Live deployment checks

`scripts/live_smoke.py` used the included original script with **explicitly labeled synthetic narration**. It uploaded a real MP4 via HTTP with matching paragraph-aligned SRT. Narration duration: **309.46 seconds**; the encoded video displays approximately **05:10**. This is a static title-card fixture, not a real customer campaign or complex footage benchmark.

- Upload + alignment: **0.94 s** on this machine.
- Three source-grounded candidate clips persisted.
- Nine drafts generated with `template` provenance.
- Two 25.746-second 720×1280 H.264 MP4 variants rendered: **2.81 s** and **2.80 s** as observed by HTTP polling.
- Export sizes: **341,469** and **340,549 bytes**.
- Distinct SHA-256 hashes recorded in `test-results/live-smoke.json`.
- An extracted frame was visually inspected: opening headline, REMIXORA treatment label, original source frame and burned-in subtitles were present.

These timings apply only to this simple fixture and this Windows computer. Memory peak, representative moving-footage throughput, cloud CPU latency and ARM64 performance were not benchmarked.

The server process was stopped and restarted. `scripts/verify_restart.py` verified one source, three clips, nine copies, one scheduled-in-app demo entry, edit evidence, two downloadable exports and a live worker. The UI independently showed the retained calendar entry after reload. Actual filesystem backup and restore completed in `backups/local-verified` and `backups/restored-verification` with SQLite integrity checks.

## Browser verification

- All eight screens navigated successfully after final backend fixes.
- No browser console errors were observed in the final navigation pass.
- Edited the Instagram demo copy in the UI and observed three specific pending memory proposals with edit evidence.
- Approved that demo copy and scheduled it for **24 November 2026, 10:00 Asia/Calcutta**, explicitly as an in-app demonstration. No external post was created.
- Checked desktop at 1440 px and narrow layout at 390 px. Corrected populated-library overflow; final mobile document width was 375 px inside a 390 px viewport (scrollbar included).
- Screenshots: `test-results/studio-desktop.jpg`, `test-results/studio-mobile.jpg`.
- The browser automation file chooser failed with a stale browser-node error. Live HTTP and integration uploads succeeded; automated file-chooser upload itself is not claimed as verified.

## Bugs found and fixed

- SQLite initialization originally left a connection open, preventing Windows test database cleanup. Initialization now explicitly closes it.
- Storage diagnostics raced SQLite sidecar cleanup and occasionally failed the dashboard. A single-stat, missing-file-tolerant implementation and regression test fix it.
- A populated source library exceeded narrow mobile grid width. Grid children now shrink correctly and source rows wrap.
- Offline excerpts previously stopped mid-sentence. New generations prefer complete source sentences.

## Not verified / intentionally unavailable

- Docker Desktop Linux engine unavailable; Docker image build/runtime and ARM64 remain unverified.
- Public deployment, TLS/DNS/Caddy runtime and cloud quota eligibility were not attempted after the user chose local deployment.
- No live Gemini key or Ollama text model was configured. Local faster-whisper is now configured and exercised as documented in the update above. whisper.cpp and multilingual speech accuracy remain unverified.
- Offline mode uses labeled heuristics/templates. Calendar planning is not social posting. Synthetic data is not measured campaign performance.
- No screen-recorded three-minute presentation, GDPR delete UI, multi-user accounts or automated source-retention policy was created.

Raw local evidence is gitignored to avoid publishing source media and private state. Keep it with the local demo or export selected artifacts deliberately.

## Exact user-link repair and Gemini activation

- Fixed `/live/` URLs and recognized scheme-less YouTube links. Tested the supplied `https://www.youtube.com/live/GcBkSnxIbf0` through actual download, local transcription, selection, writing and rendering.
- Moved the supplied key from the example file into ignored `.env.local`, enabled Gemini and removed the key from the example. A live provider test returned successful JSON.
- Replaced model time arithmetic with code-validated candidate windows drawn from the source. Gemini chooses exact eligible index pairs; validated model selections take priority over heuristic fallbacks.
- Added Replan with current AI, retaining prior clips, transcript evidence and approvals as a separate editorial revision.
- Final live revision: three Gemini-selected clips, 27 drafts (Gemini plus explicitly labeled validation fallbacks), three downloaded MP4s successfully decoded with FFmpeg. Evidence: `test-results/user-youtube-gemini.json`.
- Final regression suite: 46 passed in 32.19 seconds. Python compilation and both JavaScript syntax checks passed.
- Updated model writing instructions to avoid unsupported digits and paraphrases inside quotation marks; retained source validation and labeled fallback behavior.
