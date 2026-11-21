# Baseline audit — 2026-11-21

Source: supplied independently authored `remixora_deployment_starter.zip`.
Baseline: `python -m compileall -q app` succeeds; `python -m pytest -q`: **3 passed**.

Working unit coverage: subtitle parsing, heuristic clip selection, nine template copies.
Implemented but not integration-tested in starter: uploads, FFmpeg cuts, optional providers, SQLite edits, simple calendar and CSV import.
Missing: durable queue/recovery, distinct rendered remixes, subtitle overlay, structured evidence and rubric, profile/revisions, approval-gated calendar with timezone/conflict validation, immutable/deduplicated metrics, backup/restore and end-to-end tests.
Environment: Windows x86-64, Python 3.12.10. Docker client installed; engine initially unavailable. FFmpeg not initially on PATH. No cloud target or credentials supplied.

Do not infer production readiness from the three baseline tests.
