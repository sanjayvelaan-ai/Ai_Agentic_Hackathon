# Three-minute demo walkthrough

The bundled source is an **original script with synthetic Windows TTS narration**. It is not a customer campaign, cloned voice, testimonial or real performance dataset. The product only transforms supplied footage; it does not generate voices during normal use.

1. **0:00–0:25 — Studio and ingestion.** Open Studio Home, show real counters and the labeled sample. On Ingest, explain 150 MB / 30 minute bounds and mandatory matching SRT/VTT in offline mode.
2. **0:25–0:55 — Scout.** Open the demo source. Seek a timestamp, open a clip’s evidence, show exact source quote, rubric and heuristic provenance.
3. **0:55–1:30 — Remix.** Open the first clip, compare Teach It / Tell It / Challenge It across Instagram, YouTube and LinkedIn. Preview the existing Teach It and Tell It exports. Their real MP4 files differ.
4. **1:30–2:05 — Brand memory.** Edit a caption to remove hashtags. Save, then open Brand DNA. Show before/after evidence. Explicitly approve the rule. Generate copies for a different clip and show that new copies omit hashtags; historical drafts remain intact. Deactivate demo preferences afterward if they do not match your voice.
5. **2:05–2:35 — Calendar.** Approve a reviewed draft, choose a future slot and an IANA timezone. Explain that scheduled-in-app does not publish externally. Show rescheduling, list/week/month views and conflict protection.
6. **2:35–3:00 — Feedback and health.** Show the CSV template and transparent sample threshold. Synthetic imports remain labeled and do not influence actual rankings. Automated tests demonstrate actual-data ranking adaptation across two future sources. Show the job/event trail and persistent storage.

To reproduce the sample on Windows, run `scripts/create_demo.ps1` with System.Speech and FFmpeg available, then `python scripts/live_smoke.py` while the server runs. Live smoke timings are in `test-results/live-smoke.json`. No screen-recorded presentation has been produced.
