# Smart Preset Engine and glass studio — local implementation

The two supplied briefs are feature/design specifications. The user's local-only deployment choice remains the deployment boundary.

1. **Preserve and extend:** additive version-4 migrations for preset runs, candidates, cached measurements and clip revisions; retain existing sources, drafts, approvals and metrics.
2. **Measure source evidence:** reuse aligned transcripts; measure audio energy, sampled frames and silence with local tools; validate capability requirements before selecting.
3. **Select by preset:** register all 12 presets with distinct evidence gates and weights; apply duration/context/count/intensity; use bounded, validated optional AI ranking; retain truthful fallback provenance and no-match states.
4. **Review before export:** persist each analysis independently; preview evidence, select/reject/restore, edit a range as a new revision, then queue only the selected exports.
5. **Render actual media:** three aspect ratios, optional captions and validated output durations; real silence-removal EDL/concatenation for MP4/M4A. One durable media worker, transactional enqueue and restart recovery.
6. **Connect existing workflows:** preset clips work with Remix, approved brand rules, copy review, local calendar and imported metrics; source evidence and old recommendations stay frozen.
7. **Apply the design brief:** warm cream/sage glass, rim lighting, controlled blur, editorial typography, one violet accent, practical library and editing controls. Remove promotional/stack explanations from primary pages; keep diagnostics in Settings.
8. **Verify and deploy locally:** regression and FFmpeg tests, live Gemini selection on the user's YouTube recording, browser desktop/mobile review, real export decoding, then restart the native local service.

## Scope boundaries

- Cinematic uses sampled image-quality/motion measurements, not semantic vision, speaker tracking or automatic face reframing.
- Local speech cue recognition is English; limited non-English broad selection requires appropriate transcript/model evidence. It does not translate subtitles.
- Preset feedback is a bounded comparable-group score adjustment, not model training or a claim of campaign improvement.
- Existing file quotas, authentication option and backups remain. Automatic retention deletion, public multi-user accounts and social publishing are not enabled.
- Docker/Caddy packaging remains available; the verified target is native Windows localhost.

See TEST_REPORT.md for observed validation and README.md for usage. The earlier implementation plan is retained below as history.

# Earlier implementation plan

1. Preserve starter schema with additive versioned migrations. Add durable jobs, profile, revisions, variants, evidence, approval and analytics identity.
2. Harden source validation and aligned transcripts. Use a single recoverable media worker and atomic exports. Optional local speech adapters; no automatic downloads.
3. Validate scouting and expose exact evidence, rubric, base score and feedback adjustments. Implement bounded provider routing and cache.
4. Build three editorial treatments and nine editable platform drafts; render distinct headline/subtitle MP4s. Record edits and explicit memory approval.
5. Add calendar approval, timezone validation, conflicts/rescheduling/canceling; deduplicate imported metrics and adapt future recommendations.
6. Build a responsive obsidian/lavender/teal studio with eight functional views, actual state, errors, downloads and provenance.
7. Run API/FFmpeg integration, security, recovery and persistence tests. Visually inspect desktop/mobile UI. Package Docker/Caddy, backups and runbook; deploy to the available local target. Cloud verification depends on a supplied VM/domain.

Release evidence lives in TEST_REPORT.md; unverified environments remain explicit.

## Guided link/upload workflow — completed locally

1. Normalize permitted YouTube URLs and fetch bounded media/captions in an isolated process.
2. Persist a project and queued orchestration job together. Continue through aligned transcript, selection, drafts and actual vertical renders using one media worker.
3. Share Shorts/informative objectives, requested count and approximate duration between link and upload flows. Persist progress, recover errors, and resume after transcript import or local speech setup.
4. Expose a responsive creation screen, stage progress, source evidence, previews, downloads, recent projects and truthful API/provider guidance.
5. Install project-local speech dependencies and a CPU model; exercise real download, browser upload, transcription and MP4 decoding. Pin the compatible audio decoder and validate EOF cue handling.
6. Run the expanded 42-test suite, inspect desktop/mobile layouts, and restart only the local server. Keep optional text providers and cloud publishing unconfigured.
