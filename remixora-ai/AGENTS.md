# REMIXORA AI agent coding instructions

- Primary specification: `CODEX_DEPLOYMENT_MASTER_PROMPT.md`.
- This repository was originally written for REMIXORA; do not replace it with a copied/rebranded OpenShorts codebase.
- Open-source references are welcome, but keep relevant licenses and authors' notices on code actually imported. Do not import OpenShorts `cloud/` files.
- Source-ground all clip timecodes and quotes in persisted transcription segments; never fabricate audio/video scenes or claimed performance.
- Make every model output Pydantic-validated and log only metadata, not secrets or private transcript contents.
- Mark heuristic and template fallbacks honestly. Never promise free hosted unlimited compute.
- Never store API tokens in browser assets or commit them. Only approved actions leave the app.
- Use deterministic FFmpeg, SQLite and analytics calculations; avoid model calls for tasks code can reliably do.
- Keep one active heavy media job, predictable CPU/thread settings, durable state and single SQLite writer.
- Always validate with `python -m compileall -q app` and `python -m pytest -q` before saying it works. Add end-to-end tests when extending workflows.
- Single-user Basic Auth is a hackathon demo boundary, not full public multiuser auth. Do not launch publicly without HTTPS and strong credentials.

## Application contracts
- `app/agents` contains validated model/tool contracts; offline tools must stay labeled heuristic/template.
- Keep schema changes additive in `db.migrate`; never delete a user's database for an upgrade.
- Media jobs go through `jobs.enqueue`, with a single `DurableWorker` started by FastAPI lifespan.
- Freeze transcript evidence once clips are selected. Keep historical recommendations and metrics immutable.
- Brand proposals require explicit approval. Caption edits revoke copy approval. Calendar writes require approved current text.
- Analytics samples count distinct clips; synthetic imports never affect actual rankings. Compare matching periods/platforms only.
- Run `python -m pytest -q` with FFmpeg/FFprobe available. `tests/conftest.py` isolates test storage from the live `data` folder.
- Current requested deployment is local only. Do not provision cloud services or publish this private media studio.

## Smart Cuts contracts
- Keep all 12 registry presets distinct; evidence gates must run before optional semantic ranking. A valid model shortlist must take precedence over unreviewed local scores.
- Model rankings reference bounded window indices only. Never turn audio amplitude into a claim of laughter/emotion, or frame statistics into scene/face understanding.
- Unsupported source capabilities and no matches are successful, visible outcomes; never manufacture clips to fill a count.
- Commit preset state and queued jobs together. Reuse the single heavy worker; recover both queue and visible preset state after interruption.
- Range edits create new clip IDs and preserve previous evidence, approvals and metrics. Review rejection must block rendering until restored.
- Silence removal requires a retained-range edit list and verified media concatenation. Keep all selected intervals within source duration.
- Preserve the warm glass studio design. Keep provider/stack explanations in Settings and developer documentation; use functional product copy in editing flows.
