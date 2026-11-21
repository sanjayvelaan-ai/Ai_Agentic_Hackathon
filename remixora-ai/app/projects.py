"""Project-based organization, isolated media storage, candidate management, and render workflows."""
import hashlib
import json
import os
import re
import shutil
import urllib.request
import uuid
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, RedirectResponse, Response
from pydantic import BaseModel, Field

from .db import DATA_DIR, db, project_paths, rows
from .jobs import enqueue
from .media import generate_thumbnail, parse_subtitles, probe, probe_output
from .presets import PRESETS, PresetConfig, REGISTRY, definition
from .workflow import WorkflowOptions, create_workflow
from .youtube import canonical_youtube_url

router = APIRouter(prefix="/api/projects")


def get_project_or_404(c, project_id: str):
    p = c.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
    if not p:
        raise HTTPException(404, "Project not found")
    return dict(p)


class ProjectUpdate(BaseModel):
    title: str = Field(min_length=1, max_length=200)


class RenderRequest(BaseModel):
    candidate_id: str
    aspect_ratio: Literal["9:16", "1:1", "16:9"] = "9:16"
    burn_subtitles: bool = True
    headline: str = Field(default="", max_length=120)


class RenderUpdate(BaseModel):
    title: str = Field(min_length=1, max_length=200)


@router.get("")
def list_projects(
    search: str = "",
    status: str = "",
    sort: str = "newest",
):
    with db() as c:
        query = """
            SELECT
                p.*,
                (SELECT COUNT(*) FROM clip_candidates cc WHERE cc.project_id = p.id) as candidates_count,
                (SELECT COUNT(*) FROM rendered_clips rc WHERE rc.project_id = p.id AND rc.status = 'rendered') as renders_count
            FROM projects p
            WHERE 1=1
        """
        params = []
        if search.strip():
            query += " AND p.title LIKE ?"
            params.append(f"%{search.strip()}%")
        if status.strip():
            query += " AND p.status = ?"
            params.append(status.strip())

        if sort == "oldest":
            query += " ORDER BY p.created_at ASC"
        elif sort == "updated":
            query += " ORDER BY p.updated_at DESC"
        elif sort == "title":
            query += " ORDER BY p.title ASC"
        else:  # newest
            query += " ORDER BY p.created_at DESC"

        result = rows(c.execute(query, params))

    for p in result:
        p["has_thumbnail"] = bool(p["thumbnail_path"] and Path(p["thumbnail_path"]).is_file())
        p["thumbnail_url"] = f"/api/projects/{p['id']}/thumbnail"

    return result


@router.post("/import", status_code=202)
def import_file(
    media: UploadFile = File(...),
    transcript: UploadFile | None = File(default=None),
    title: str | None = Form(default=None),
):
    ext = Path(media.filename or "").suffix.lower()
    if ext not in {".mp4", ".mov", ".mkv", ".webm", ".mp3", ".m4a", ".wav"}:
        raise HTTPException(400, "Unsupported media format. Use MP4, MOV, MKV, WebM, MP3, M4A, or WAV.")

    # Read transcript if provided
    text = None
    if transcript and transcript.filename:
        sub_ext = Path(transcript.filename).suffix.lower()
        if sub_ext not in {".srt", ".vtt"}:
            raise HTTPException(400, "Transcript must be .srt or .vtt")
        raw = transcript.file.read(2_000_001)
        if len(raw) > 2_000_000:
            raise HTTPException(413, "Transcript exceeds 2 MB")
        try:
            text = raw.decode("utf-8-sig")
            parse_subtitles(text)
        except UnicodeError:
            raise HTTPException(400, "Transcript must be valid UTF-8")

    limit = int(os.getenv("MAX_UPLOAD_MB", "150")) * 1024 * 1024
    project_id = uuid.uuid4().hex
    paths = project_paths(project_id)
    dest = paths["sources"] / f"original{ext}"

    received = 0
    hasher = hashlib.sha256()
    try:
        with dest.open("wb") as fp:
            while chunk := media.file.read(1024 * 1024):
                received += len(chunk)
                if received > limit:
                    raise HTTPException(413, "Upload exceeds configured size limit")
                fp.write(chunk)
                hasher.update(chunk)
        if not received:
            raise ValueError("Empty media file uploaded")

        duration, kind = probe(dest)
        if text:
            from .main import validate_segments
            validate_segments(parse_subtitles(text), duration)
    except Exception as ex:
        shutil.rmtree(paths["root"], ignore_errors=True)
        if isinstance(ex, HTTPException):
            raise ex
        raise HTTPException(400, str(ex) if isinstance(ex, ValueError) else "Media inspection failed.")

    checksum = hasher.hexdigest()

    # Deduplication check
    with db() as c:
        existing = c.execute("SELECT id FROM assets WHERE checksum = ?", (checksum,)).fetchone()
        if existing:
            shutil.rmtree(paths["root"], ignore_errors=True)
            existing_p = c.execute("SELECT * FROM projects WHERE id = ?", (existing["id"],)).fetchone()
            return {
                "project_id": existing["id"],
                "project": dict(existing_p) if existing_p else None,
                "status": "ready",
                "duplicate": True,
            }

        project_title = title.strip() if title and title.strip() else Path(media.filename or "Uploaded Media").stem
        thumb_path = paths["thumbnails"] / "cover.jpg"
        generated_thumb = generate_thumbnail(dest, thumb_path, timestamp=min(2.0, duration / 2))

        # Insert project
        c.execute(
            """INSERT INTO projects (id, title, thumbnail_path, status, source_type, duration)
               VALUES (?, ?, ?, 'queued', 'upload', ?)""",
            (project_id, project_title, str(generated_thumb) if generated_thumb else None, duration),
        )

        # Insert media source
        c.execute(
            """INSERT INTO media_sources (id, project_id, source_type, original_name, storage_path, duration, media_type, status)
               VALUES (?, ?, 'upload', ?, ?, ?, ?, 'queued')""",
            (project_id, project_id, Path(media.filename or "media").name, str(dest), duration, kind),
        )

        # Insert asset for backward compatibility
        c.execute(
            """INSERT INTO assets (id, project_id, filename, media_path, media_kind, duration, status, checksum)
               VALUES (?, ?, ?, ?, ?, ?, 'queued', ?)""",
            (project_id, project_id, project_title, str(dest), kind, duration, checksum),
        )

    # Save transcript file if present
    if text:
        (paths["transcripts"] / "original.srt").write_text(text, encoding="utf-8")

    job_id = enqueue("ingest", project_id, {"transcript": text})

    return {
        "project_id": project_id,
        "title": project_title,
        "status": "queued",
        "job_id": job_id,
        "duration": duration,
        "duplicate": False,
    }


@router.post("/import-youtube", status_code=202)
def import_youtube_link(
    url: str = Form(...),
    rights_confirmed: bool = Form(default=False),
    title: str | None = Form(default=None),
    language: str = Form(default="en"),
):
    if not rights_confirmed:
        raise HTTPException(400, "Confirm that you have permission to repurpose this video.")
    canonical_url = canonical_youtube_url(url)

    options = WorkflowOptions(
        objective="shorts",
        clip_count=3,
        target_seconds=30,
        language=language,
        auto_render=False,
        import_only=True,
        subtitles=True,
    )

    with db() as c:
        existing = c.execute("SELECT id FROM workflows WHERE source_url = ?", (canonical_url,)).fetchone()
        if existing:
            flow = c.execute("SELECT * FROM workflows WHERE id = ?", (existing["id"],)).fetchone()
            asset_id = flow["asset_id"]
            if asset_id:
                p = c.execute("SELECT * FROM projects WHERE id = ?", (asset_id,)).fetchone()
                if p:
                    return {"project_id": p["id"], "existing": True, "workflow_id": existing["id"]}

    res = create_workflow(options, url=canonical_url)
    flow_id = res["id"]

    return {
        "workflow_id": flow_id,
        "status": "queued",
        "message": "YouTube import initiated in the background.",
    }


@router.get("/{project_id}")
def get_project(project_id: str):
    with db() as c:
        p = get_project_or_404(c, project_id)
        source = c.execute("SELECT * FROM media_sources WHERE project_id = ?", (project_id,)).fetchone()
        candidates_count = c.execute("SELECT COUNT(*) FROM clip_candidates WHERE project_id = ?", (project_id,)).fetchone()[0]
        renders_count = c.execute("SELECT COUNT(*) FROM rendered_clips WHERE project_id = ? AND status = 'rendered'", (project_id,)).fetchone()[0]
        runs_count = c.execute("SELECT COUNT(*) FROM preset_runs WHERE project_id = ? OR asset_id = ?", (project_id, project_id)).fetchone()[0]
        segments_count = c.execute("SELECT COUNT(*) FROM segments WHERE asset_id = ?", (project_id,)).fetchone()[0]
        copies_count = c.execute(
            "SELECT COUNT(*) FROM copies cp JOIN clips cl ON cl.id = cp.clip_id WHERE cl.project_id = ? OR cl.asset_id = ?",
            (project_id, project_id)
        ).fetchone()[0]

    p["has_thumbnail"] = bool(p["thumbnail_path"] and Path(p["thumbnail_path"]).is_file())
    p["thumbnail_url"] = f"/api/projects/{p['id']}/thumbnail" if p["has_thumbnail"] else None
    p["source"] = dict(source) if source else None
    p["counts"] = {
        "candidates": candidates_count,
        "renders": renders_count,
        "preset_runs": runs_count,
        "segments": segments_count,
        "copies": copies_count,
    }
    return p


@router.patch("/{project_id}")
def update_project(project_id: str, update: ProjectUpdate):
    with db() as c:
        get_project_or_404(c, project_id)
        c.execute("UPDATE projects SET title = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (update.title.strip(), project_id))
        c.execute("UPDATE assets SET filename = ? WHERE id = ?", (update.title.strip(), project_id))
    return {"id": project_id, "title": update.title.strip()}


@router.delete("/{project_id}")
def delete_project(project_id: str):
    with db() as c:
        get_project_or_404(c, project_id)
        c.execute("DELETE FROM projects WHERE id = ?", (project_id,))
        c.execute("DELETE FROM assets WHERE id = ?", (project_id,))
        c.execute("DELETE FROM segments WHERE asset_id = ?", (project_id,))
        c.execute("DELETE FROM clip_candidates WHERE project_id = ?", (project_id,))
        c.execute("DELETE FROM rendered_clips WHERE project_id = ?", (project_id,))

    # Safely remove isolated project directory
    p_path = project_paths(project_id)["root"]
    if p_path.is_dir():
        shutil.rmtree(p_path, ignore_errors=True)

    return {"deleted": True, "id": project_id}


@router.get("/{project_id}/thumbnail")
def project_thumbnail(project_id: str):
    with db() as c:
        p = get_project_or_404(c, project_id)
        source = c.execute("SELECT * FROM media_sources WHERE project_id = ?", (project_id,)).fetchone()
        asset = c.execute("SELECT * FROM assets WHERE id = ?", (project_id,)).fetchone()

    # 1. Existing verified thumbnail file
    if p["thumbnail_path"] and Path(p["thumbnail_path"]).is_file():
        return FileResponse(Path(p["thumbnail_path"]), media_type="image/jpeg")

    paths = project_paths(project_id)
    target_thumb = paths["thumbnails"] / "cover.jpg"

    # 2. Extract video frame if local video file exists
    candidate_media = []
    sources = list(paths["sources"].glob("original.*"))
    if sources and sources[0].is_file():
        candidate_media.append(sources[0])
    if source and source["storage_path"] and Path(source["storage_path"]).is_file():
        candidate_media.append(Path(source["storage_path"]))
    if asset and asset["media_path"] and Path(asset["media_path"]).is_file():
        candidate_media.append(Path(asset["media_path"]))

    for med in candidate_media:
        if med.suffix.lower() in {".mp4", ".mov", ".mkv", ".webm"}:
            dur = p.get("duration") or 10.0
            gen = generate_thumbnail(med, target_thumb, timestamp=min(2.0, max(0.5, dur / 3)))
            if gen and Path(gen).is_file():
                with db() as c:
                    c.execute("UPDATE projects SET thumbnail_path = ? WHERE id = ?", (str(gen), project_id))
                return FileResponse(Path(gen), media_type="image/jpeg")

    # 3. YouTube link thumbnail (fetch or redirect)
    yt_url = (source and source["source_url"]) or (asset and asset["source_url"]) or ""
    yt_m = re.search(r'(?:v=|\/)([0-9A-Za-z_-]{11})', yt_url)
    if yt_m:
        yt_id = yt_m.group(1)
        try:
            target_thumb.parent.mkdir(parents=True, exist_ok=True)
            urllib.request.urlretrieve(f"https://img.youtube.com/vi/{yt_id}/hqdefault.jpg", str(target_thumb))
            if target_thumb.is_file() and target_thumb.stat().st_size > 500:
                with db() as c:
                    c.execute("UPDATE projects SET thumbnail_path = ? WHERE id = ?", (str(target_thumb), project_id))
                return FileResponse(target_thumb, media_type="image/jpeg")
        except Exception:
            pass
        return RedirectResponse(f"https://img.youtube.com/vi/{yt_id}/hqdefault.jpg")

    # 4. Audio-only / placeholder SVG
    svg = """<svg xmlns="http://www.w3.org/2000/svg" width="640" height="360" viewBox="0 0 640 360">
      <defs>
        <linearGradient id="g" x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stop-color="#282238"/>
          <stop offset="100%" stop-color="#151622"/>
        </linearGradient>
      </defs>
      <rect width="640" height="360" fill="url(#g)"/>
      <circle cx="320" cy="180" r="44" fill="#7c3aed" fill-opacity="0.25"/>
      <path d="M308 160 L340 180 L308 200 Z" fill="#b8a5f5"/>
      <text x="320" y="260" text-anchor="middle" fill="#aaaabd" font-family="'Segoe UI', sans-serif" font-size="14" font-weight="600" letter-spacing="1.5">AUDIO RECORDING</text>
    </svg>"""
    return Response(content=svg, media_type="image/svg+xml")


@router.get("/{project_id}/sources")
def project_sources(project_id: str):
    with db() as c:
        get_project_or_404(c, project_id)
        sources = rows(c.execute("SELECT * FROM media_sources WHERE project_id = ?", (project_id,)))
    return sources


@router.get("/{project_id}/media")
def project_media_stream(project_id: str):
    with db() as c:
        p = get_project_or_404(c, project_id)
        source = c.execute("SELECT * FROM media_sources WHERE project_id = ?", (project_id,)).fetchone()
        asset = c.execute("SELECT * FROM assets WHERE id = ?", (project_id,)).fetchone()

    path = None
    if source and source["storage_path"] and Path(source["storage_path"]).is_file():
        path = Path(source["storage_path"])
    elif asset and asset["media_path"] and Path(asset["media_path"]).is_file():
        path = Path(asset["media_path"])

    if not path:
        raise HTTPException(404, "Original media file not found")

    media_type = "video/mp4" if path.suffix.lower() in {".mp4", ".mov", ".mkv", ".webm"} else "audio/mpeg"
    return FileResponse(path, media_type=media_type)


@router.get("/{project_id}/transcript")
def project_transcript(project_id: str):
    with db() as c:
        get_project_or_404(c, project_id)
        seg = rows(c.execute("SELECT id, start, end, text FROM segments WHERE asset_id = ? ORDER BY start", (project_id,)))
    return seg


@router.get("/{project_id}/preset-runs")
def project_preset_runs(project_id: str):
    with db() as c:
        get_project_or_404(c, project_id)
        runs = rows(c.execute(
            "SELECT * FROM preset_runs WHERE project_id = ? OR asset_id = ? ORDER BY rowid DESC",
            (project_id, project_id)
        ))
    for r in runs:
        r["preset_name"] = REGISTRY[r["preset_id"]].name if r.get("preset_id") in REGISTRY else r.get("preset_id")
    return runs


@router.post("/{project_id}/preset-runs", status_code=202)
def start_preset_run(project_id: str, config: PresetConfig):
    with db() as c:
        c.execute("BEGIN IMMEDIATE")
        p = get_project_or_404(c, project_id)
        active = c.execute(
            "SELECT id FROM preset_runs WHERE (project_id = ? OR asset_id = ?) AND config_json = ? AND status IN ('queued', 'analyzing')",
            (project_id, project_id, config.model_dump_json())
        ).fetchone()
        if active:
            return {"id": active["id"], "existing": True}

        rid = uuid.uuid4().hex
        c.execute(
            "INSERT INTO preset_runs (id, project_id, asset_id, preset_id, config_json) VALUES (?, ?, ?, ?, ?)",
            (rid, project_id, project_id, config.preset_id, config.model_dump_json())
        )
        job_id = enqueue("preset_analyze", rid, connection=c)

    return {"id": rid, "job_id": job_id, "preset_id": config.preset_id}


@router.get("/{project_id}/candidates")
def project_candidates(project_id: str, preset_run_id: str | None = None):
    with db() as c:
        get_project_or_404(c, project_id)
        query = """
            SELECT cc.*, pr.preset_id
            FROM clip_candidates cc
            LEFT JOIN preset_runs pr ON pr.id = cc.preset_run_id
            WHERE cc.project_id = ?
        """
        params = [project_id]
        if preset_run_id:
            query += " AND cc.preset_run_id = ?"
            params.append(preset_run_id)
        query += " ORDER BY cc.score DESC"
        results = rows(c.execute(query, params))

    for item in results:
        item["preset_name"] = REGISTRY[item["preset_id"]].name if item.get("preset_id") in REGISTRY else "Custom"
        item["is_source_preview"] = True  # Explicitly label as source preview!
    return results


@router.patch("/{project_id}/candidates/{candidate_id}")
def review_candidate(project_id: str, candidate_id: str, status: Literal["proposed", "approved", "rejected"] = Form(...)):
    with db() as c:
        c.execute("BEGIN IMMEDIATE")
        cand = c.execute("SELECT * FROM clip_candidates WHERE id = ? AND project_id = ?", (candidate_id, project_id)).fetchone()
        if not cand:
            raise HTTPException(404, "Candidate not found")
        c.execute("UPDATE clip_candidates SET status = ? WHERE id = ?", (status, candidate_id))
        c.execute("UPDATE preset_candidates SET status = ? WHERE id = ?", (status, candidate_id))
    return {"id": candidate_id, "status": status}


@router.post("/{project_id}/renders", status_code=202)
def create_render(project_id: str, req: RenderRequest):
    with db() as c:
        c.execute("BEGIN IMMEDIATE")
        p = get_project_or_404(c, project_id)
        cand = c.execute("SELECT * FROM clip_candidates WHERE id = ? AND project_id = ?", (req.candidate_id, project_id)).fetchone()
        if not cand:
            # Fallback to check preset_candidates
            cand = c.execute("SELECT * FROM preset_candidates WHERE id = ?", (req.candidate_id,)).fetchone()
            if cand:
                clip = c.execute("SELECT * FROM clips WHERE id = ?", (cand["clip_id"],)).fetchone()
            else:
                clip = c.execute("SELECT * FROM clips WHERE id = ? AND (project_id = ? OR asset_id = ?)", (req.candidate_id, project_id, project_id)).fetchone()
            if not clip:
                raise HTTPException(404, "Candidate clip not found")
            start = clip["start"]
            end = clip["end"]
            title = clip["title"]
            clip_id = clip["id"]
            run_id = cand["run_id"] if cand else None
        else:
            start = cand["start_time"]
            end = cand["end_time"]
            title = cand["title"]
            clip_id = cand["clip_id"] or cand["id"]
            run_id = cand["preset_run_id"]

        render_id = uuid.uuid4().hex
        paths = project_paths(project_id)
        dest_file = paths["renders"] / f"{render_id}.mp4"

        # Record into rendered_clips as 'rendering'
        c.execute(
            """INSERT INTO rendered_clips (id, project_id, candidate_id, preset_run_id, clip_id, title, file_path, duration, aspect_ratio, status)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'rendering')""",
            (render_id, project_id, req.candidate_id, run_id, clip_id, req.headline or title, str(dest_file), end - start, req.aspect_ratio),
        )

        # Enqueue background render job
        job_payload = {
            "project_id": project_id,
            "render_id": render_id,
            "candidate_id": req.candidate_id,
            "clip_id": clip_id,
            "start": start,
            "end": end,
            "headline": req.headline or title,
            "aspect_ratio": req.aspect_ratio,
            "burn_subtitles": req.burn_subtitles,
            "dest_path": str(dest_file),
        }
        job_id = enqueue("project_render", render_id, job_payload, connection=c)

    return {
        "render_id": render_id,
        "job_id": job_id,
        "status": "rendering",
        "title": req.headline or title,
    }


@router.get("/{project_id}/renders")
def list_renders(project_id: str):
    """Return only completed, valid rendered clips with real files on disk."""
    with db() as c:
        get_project_or_404(c, project_id)
        all_renders = rows(c.execute(
            "SELECT * FROM rendered_clips WHERE project_id = ? ORDER BY created_at DESC",
            (project_id,)
        ))

    verified = []
    for r in all_renders:
        file_path = Path(r["file_path"])
        if r["status"] == "rendered" and file_path.is_file() and file_path.stat().st_size > 500:
            r["stream_url"] = f"/api/projects/{project_id}/renders/{r['id']}/stream"
            r["download_url"] = f"/api/projects/{project_id}/renders/{r['id']}/download"
            r["thumbnail_url"] = f"/api/projects/{project_id}/renders/{r['id']}/thumbnail" if (r["thumbnail_path"] and Path(r["thumbnail_path"]).is_file()) else None
            r["is_rendered"] = True
            verified.append(r)
        elif r["status"] in {"rendering", "queued"}:
            r["is_rendered"] = False
            verified.append(r)

    return verified


@router.get("/{project_id}/renders/{render_id}")
def get_render(project_id: str, render_id: str):
    with db() as c:
        get_project_or_404(c, project_id)
        r = c.execute("SELECT * FROM rendered_clips WHERE id = ? AND project_id = ?", (render_id, project_id)).fetchone()
        if not r:
            raise HTTPException(404, "Rendered clip not found")
        item = dict(r)

    file_path = Path(item["file_path"])
    item["exists_on_disk"] = file_path.is_file()
    item["stream_url"] = f"/api/projects/{project_id}/renders/{render_id}/stream"
    item["download_url"] = f"/api/projects/{project_id}/renders/{render_id}/download"
    return item


@router.get("/{project_id}/renders/{render_id}/stream")
def stream_render(project_id: str, render_id: str):
    """Play the actual rendered output MP4 with full HTTP range-request support."""
    with db() as c:
        r = c.execute("SELECT * FROM rendered_clips WHERE id = ? AND project_id = ?", (render_id, project_id)).fetchone()
        if not r:
            raise HTTPException(404, "Rendered clip not found")
        path = Path(r["file_path"])

    if not path.is_file():
        raise HTTPException(404, "Rendered output file does not exist on disk")

    return FileResponse(path, media_type="video/mp4", headers={"Accept-Ranges": "bytes"})


@router.get("/{project_id}/renders/{render_id}/download")
def download_render(project_id: str, render_id: str):
    with db() as c:
        r = c.execute("SELECT * FROM rendered_clips WHERE id = ? AND project_id = ?", (render_id, project_id)).fetchone()
        if not r:
            raise HTTPException(404, "Rendered clip not found")
        path = Path(r["file_path"])
        title = r["title"] or f"remixora-{render_id}"

    if not path.is_file():
        raise HTTPException(404, "Rendered output file not found")

    safe_title = "".join(c for c in title if c.isalnum() or c in " -_").strip() or f"clip-{render_id[:8]}"
    return FileResponse(
        path,
        media_type="video/mp4",
        filename=f"{safe_title}.mp4",
        headers={"Content-Disposition": f'attachment; filename="{safe_title}.mp4"'},
    )


@router.get("/{project_id}/renders/{render_id}/thumbnail")
def render_thumbnail(project_id: str, render_id: str):
    with db() as c:
        r = c.execute("SELECT * FROM rendered_clips WHERE id = ? AND project_id = ?", (render_id, project_id)).fetchone()
        if not r:
            raise HTTPException(404, "Rendered clip not found")
        thumb_path = r["thumbnail_path"]
        file_path = Path(r["file_path"])

    if thumb_path and Path(thumb_path).is_file():
        return FileResponse(Path(thumb_path), media_type="image/jpeg")

    # Generate if possible
    if file_path.is_file():
        paths = project_paths(project_id)
        t = paths["thumbnails"] / f"{render_id}.jpg"
        gen = generate_thumbnail(file_path, t, timestamp=0.5)
        if gen and Path(gen).is_file():
            with db() as c:
                c.execute("UPDATE rendered_clips SET thumbnail_path = ? WHERE id = ?", (gen, render_id))
            return FileResponse(Path(gen), media_type="image/jpeg")

    raise HTTPException(404, "Thumbnail not available")


@router.patch("/{project_id}/renders/{render_id}")
def update_render(project_id: str, render_id: str, req: RenderUpdate):
    with db() as c:
        get_project_or_404(c, project_id)
        if not c.execute("SELECT 1 FROM rendered_clips WHERE id = ? AND project_id = ?", (render_id, project_id)).fetchone():
            raise HTTPException(404, "Rendered clip not found")
        c.execute("UPDATE rendered_clips SET title = ? WHERE id = ?", (req.title.strip(), render_id))
    return {"id": render_id, "title": req.title.strip()}


@router.delete("/{project_id}/renders/{render_id}")
def delete_render(project_id: str, render_id: str):
    with db() as c:
        get_project_or_404(c, project_id)
        r = c.execute("SELECT file_path, thumbnail_path FROM rendered_clips WHERE id = ? AND project_id = ?", (render_id, project_id)).fetchone()
        if not r:
            raise HTTPException(404, "Rendered clip not found")
        c.execute("DELETE FROM rendered_clips WHERE id = ?", (render_id,))

    if r["file_path"] and Path(r["file_path"]).is_file():
        Path(r["file_path"]).unlink(missing_ok=True)
    if r["thumbnail_path"] and Path(r["thumbnail_path"]).is_file():
        Path(r["thumbnail_path"]).unlink(missing_ok=True)

    return {"deleted": True, "id": render_id}
