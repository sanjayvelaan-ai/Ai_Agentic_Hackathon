# Local deployment and optional Docker runbook

The requested target is **local only**. A native Windows deployment has been exercised at http://127.0.0.1:8000. No cloud resource, public tunnel or public Site was created.

## Windows launch

From this directory:

```powershell
python -m pip install --target .tools/python -r requirements.txt
.\run-local.ps1 -Background
# To require browser Basic Auth on the local instance instead:
.\run-local.ps1 -Background -Authenticate
```

The script binds **127.0.0.1 only**, uses one worker and stores state in `data`. The downloaded FFmpeg build in `.tools/ffmpeg` is picked up automatically. On another machine, install FFmpeg and FFprobe on PATH. Do not copy this Windows tool build to an ARM64 host.

`-Authenticate` creates a random local password in gitignored `.local-auth.json`. Read that file locally to sign in as `creator`. Do not start a second server on the same port. Without the switch or AUTH variables, the loopback development instance has no password; it is not suitable for LAN/public exposure.

Logs: `logs/server.log`, `logs/server-error.log`. The process ID is in `remixora.pid`. To stop the process, verify that the recorded ID is the Python REMIXORA server, then stop it. Restart with the same command and data directory. Existing sources, exports, edits, approvals, schedules and metrics remain in SQLite and on disk.

## Docker alternative

```powershell
Copy-Item .env.example .env
# Edit .env: replace AUTH_PASSWORD with a random 24+ character value.
# The host data directory must be writable by container UID 10001.
docker compose up --build -d
docker compose ps
docker compose logs --tail 100
curl.exe http://127.0.0.1:8000/health
docker compose restart
```

The Docker Desktop Linux engine was unavailable during this session. The image build, container runtime, Linux filesystem permissions and ARM64 execution are **not verified**. Native Windows execution is verified. The image installs distribution FFmpeg and DejaVu fonts; optional faster-whisper dependencies are excluded by default. Do not run multiple application containers against the same data directory.

On Linux prepare the volume: `mkdir -p data && sudo chown 10001:10001 data`.

## Future HTTPS deployment (not performed)

Supply a real VM, DNS record, firewall access and eligibility information before provisioning. No current free allowance or capacity guarantee is made here. Set `DEPLOY_MODE=production`, strong AUTH credentials, `DOMAIN=studio.your-domain`, and `PUBLIC_ORIGIN=https://studio.your-domain` in `.env`. Set A/AAAA DNS to the host and allow only 80/443 inbound. Keep app port 8000 on loopback. Then use `docker compose --profile public up --build -d`. Caddy obtains TLS for the configured DNS name and proxies private routes. Verify authentication, HTTPS, media downloads, startup recovery and backups on the actual host before judging it production-ready.

## Speech transcription

Both **source-matched SRT/VTT import** and **local faster-whisper transcription** have been exercised on this Windows machine. A tiny multilingual CPU int8 model is installed under `.models/whisper-tiny` and enabled in gitignored `.env.local`. No model downloads happen during uploads. Automatic transcription needs review, especially names and multilingual speech.

To set up speech on another local checkout:

```powershell
python -m pip install --target .tools/python -r requirements-transcription.txt
$env:PYTHONPATH=(Resolve-Path .tools/python).Path
python scripts/setup_speech.py
# Restart the server after setup.
```

The transcription requirements pin PyAV 16.0.1 because PyAV 19 removed an argument used by faster-whisper 1.2. Stop the server before updating loaded binary dependencies on Windows.

- `TRANSCRIPTION_BACKEND=faster-whisper`: install `requirements-transcription.txt`, pre-download a suitable CPU model during setup, and set `WHISPER_MODEL` to its local directory. Uses CPU int8, two threads, local files only. Verified locally on Windows x86-64; ARM64 wheels must be checked on the target.
- `TRANSCRIPTION_BACKEND=whisper.cpp`: build/install whisper.cpp for the target, pre-download a compatible model, set `WHISPER_CPP_BIN` and `WHISPER_CPP_MODEL`. The adapter produces 16 kHz mono WAV then imports CLI SRT. Not exercised here.

## Optional text providers

Open `.env.local` (create from `.env.local.example` only if missing); retain its existing speech settings. The launcher loads it server-side without overriding explicit environment variables. Default `AI_PROVIDER=none` keeps editorial selection/writing offline. `auto`, `gemini` or `ollama` enable configured providers. For Gemini, supply a server-only key and explicit model; independently verify account eligibility, quota, pricing and data terms. This app cannot attest free eligibility from an API key. For Ollama use `OLLAMA_URL=http://127.0.0.1:11434/v1` and a locally installed model. In Docker, use an explicitly reachable host address. Requests are bounded, cached, schema-validated, and fall back to labeled templates/heuristics. No paid endpoint is enabled by the project.

## YouTube ingestion

`yt-dlp[default]`, Node.js and FFmpeg must be available. The Windows dependencies are installed locally; Node.js is also included in the Dockerfile. Public watch, live, Shorts and youtu.be URLs are canonicalized to one video; arbitrary hosts and playlists are rejected. Downloads run in a bounded subprocess, with duration, size and quota checks. Captions are preferred, followed by local speech. Sources stay local. Nothing is posted to YouTube. No YouTube Data API key is required.

If a public video is restricted, use the original file instead. Update yt-dlp when extraction changes, then restart. The **Settings → Configure** panel distinguishes import/render/speech from optional Gemini or Ollama planning.

## Backup and restore

Stop the server or make sure no upload/render starts during backup. Keep backups outside `data`:

```powershell
python scripts/backup.py backup data backups/2026-11-21
python scripts/backup.py restore backups/2026-11-21 restored-data
```

Restore requires a new destination and rewrites internal media paths for that destination. Point `DATA_DIR` to it when starting Uvicorn manually. Never overwrite live data. SQLite integrity and record preservation are covered by tests; protect backups as private media.

## Verification

```powershell
python -m compileall -q app scripts
python -m pytest -q
node --check app/static/app.js
python scripts/live_smoke.py
```

The smoke script uploads only the included original synthetic-narration demo, checks three clips and nine drafts, and downloads two different MP4s. It changes local demo data; it does not publish anything. See `TEST_REPORT.md` for observed evidence and remaining limits.

## Smart Cuts upgrade

Restart the local server with `run-local.ps1 -Background` after the current queue is idle. Startup applies additive schema version 4; do not delete the database. Install updated `requirements.txt` in a new environment (NumPy supports local audio/frame measurements). The current workspace already has the dependency.

New endpoints cover `/api/presets`, `/api/assets/{id}/presets/analyze`, `/api/preset-runs/{id}/candidates`, `/api/preset-candidates/{id}`, `/api/clips/{id}/bounds`, `/api/preset-runs/{id}/render-selected` and `/api/render-jobs/{id}`. Existing optional Basic Auth and same-origin protections cover them and media downloads. Workspace JSON export includes preset runs, candidates and clip revisions; filesystem backups also retain their media.

The import page saves a source first. Choose a preset, inspect candidates, then render explicitly. Previous automatic workflows remain accessible through saved import history and the existing API. Pending render work survives restarts; exhausted retry states remain visible. Rendering checks quota and free disk space. No retention purge runs automatically.

No new API key is required: Gemini uses the existing server-only `.env.local` configuration. Local analysis, Whisper and FFmpeg do not need hosted credentials. Provider validation/fallback remains bounded; local analysis is labeled if the model is unavailable. Do not copy credentials into browser files or documentation.
