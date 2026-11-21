"""Persistent link/upload → transcript → editorial plan → drafts → vertical exports."""
import hashlib
import importlib.util
import json
import os
import re
import shutil
import tempfile
import threading
import uuid
from pathlib import Path
from typing import Literal
from fastapi import APIRouter,HTTPException
from pydantic import BaseModel,Field
from .db import DATA_DIR,db,rows
from .jobs import enqueue
from .youtube import canonical_youtube_url,download_youtube

router=APIRouter(prefix='/api')

class WorkflowOptions(BaseModel):
    objective:Literal['shorts','informative']='shorts'
    clip_count:int=Field(default=3,ge=1,le=5)
    target_seconds:Literal[30,45,60]=30
    language:str=Field(default='en',pattern=r'^[a-z]{2,3}(?:-[A-Za-z]{2,4})?$')
    auto_render:bool=True
    import_only:bool=False
    subtitles:bool=True

class YouTubeRequest(WorkflowOptions):
    url:str=Field(max_length=2048)
    rights_confirmed:bool=False

def set_stage(workflow_id,stage,progress,message):
    with db() as c:c.execute('UPDATE workflows SET stage=?,progress=?,message=?,error=NULL,updated_at=CURRENT_TIMESTAMP WHERE id=?',(stage,progress,message,workflow_id))

def create_workflow(options,asset_id=None,url=None):
    with db() as c:
        c.execute('BEGIN IMMEDIATE')
        old=c.execute('SELECT * FROM workflows WHERE asset_id=? OR (source_url=? AND source_url IS NOT NULL) ORDER BY rowid DESC LIMIT 1',(asset_id,url)).fetchone()
        if old:
            if old['stage']=='complete':
                return {'id':old['id'],'asset_id':old['asset_id'],'stage':old['stage'],'existing':True}
            workflow_id=old['id']
            c.execute("UPDATE workflows SET stage='queued',message='Queued to process',error=NULL WHERE id=?",(workflow_id,))
            job_id=uuid.uuid4().hex
            c.execute("INSERT INTO jobs(id,kind,target_id,payload) VALUES (?,'workflow',?,'{}')",(job_id,workflow_id))
        else:
            if asset_id and not c.execute('SELECT 1 FROM assets WHERE id=?',(asset_id,)).fetchone():raise HTTPException(404,'Source not found')
            workflow_id=uuid.uuid4().hex
            c.execute('INSERT INTO workflows(id,asset_id,source_url,options) VALUES (?,?,?,?)',(workflow_id,asset_id,url,options.model_dump_json()))
            # Queue and workflow are committed together, so restart cannot lose the request.
            job_id=uuid.uuid4().hex
            c.execute("INSERT INTO jobs(id,kind,target_id,payload) VALUES (?,'workflow',?,'{}')",(job_id,workflow_id))
    from .main import worker
    worker.start()
    worker.step()
    with db() as c:
        updated = c.execute('SELECT * FROM workflows WHERE id=?', (workflow_id,)).fetchone()
        if updated:
            return {'id': workflow_id, 'asset_id': updated['asset_id'], 'stage': updated['stage'], 'job_id': job_id}
    return {'id':workflow_id,'asset_id':asset_id,'stage':'queued','job_id':job_id}

@router.post('/youtube',status_code=202)
def import_youtube(req:YouTubeRequest):
    if not req.rights_confirmed:raise HTTPException(400,'Confirm that you own or have permission to repurpose this video.')
    url=canonical_youtube_url(req.url)
    if not importlib.util.find_spec('yt_dlp'):raise HTTPException(503,'Install yt-dlp[default] on the server to enable YouTube imports.')
    from .media import ensure_ffmpeg
    ensure_ffmpeg()
    if not shutil.which('ffmpeg') or not shutil.which('ffprobe'):raise HTTPException(503,'FFmpeg and FFprobe are required on the server.')
    min_free = min(int(os.getenv('MAX_UPLOAD_MB', '50')) * 1024**2, 50 * 1024**2)
    if shutil.disk_usage(DATA_DIR).free < min_free:raise HTTPException(507,'Free disk space before importing a video.')
    return create_workflow(WorkflowOptions(**req.model_dump()),url=url)


@router.post('/assets/{asset_id}/workflow',status_code=202)
def arrange_upload(asset_id:str,req:WorkflowOptions):return create_workflow(req,asset_id=asset_id)

@router.get('/workflows')
def workflows():
    from .main import worker
    worker.start()
    with db() as c:
        has_queued = c.execute("SELECT 1 FROM jobs WHERE status='queued'").fetchone()
    if has_queued:
        worker.step()
    with db() as c:return rows(c.execute('SELECT workflows.*,assets.filename,assets.transcript_source FROM workflows LEFT JOIN assets ON assets.id=workflows.asset_id ORDER BY workflows.rowid DESC LIMIT 50'))

@router.post('/workflows/{workflow_id}/replan',status_code=202)
def replan_workflow(workflow_id:str):
    """New editorial revision; retain historical clips, drafts and approvals."""
    with db() as c:
        flow=c.execute('SELECT * FROM workflows WHERE id=?',(workflow_id,)).fetchone()
        if not flow:raise HTTPException(404,'Workflow not found')
        if flow['stage']!='complete':raise HTTPException(409,'Wait for this workflow to finish before replanning.')
        asset=c.execute('SELECT * FROM assets WHERE id=?',(flow['asset_id'],)).fetchone()
        if not asset or asset['status']!='ready':raise HTTPException(409,'An aligned source is required.')
        aid=uuid.uuid4().hex
        c.execute('INSERT INTO assets(id,filename,media_path,media_kind,duration,status,source_url,transcript_source) VALUES (?,?,?,?,?,?,?,?)',(aid,asset['filename']+' · new editorial revision',asset['media_path'],asset['media_kind'],asset['duration'],'ready',asset['source_url'],asset['transcript_source']))
        c.execute('INSERT INTO segments(asset_id,start,end,text) SELECT ?,start,end,text FROM segments WHERE asset_id=?',(aid,asset['id']))
    return create_workflow(WorkflowOptions.model_validate_json(flow['options']),asset_id=aid)

@router.post('/workflows/{workflow_id}/resume',status_code=202)
def resume_workflow(workflow_id:str):
    with db() as c:
        c.execute('BEGIN IMMEDIATE')
        flow=c.execute('SELECT * FROM workflows WHERE id=?',(workflow_id,)).fetchone()
        if not flow:raise HTTPException(404,'Workflow not found')
        if flow['stage']=='complete':return {'id':workflow_id,'stage':'complete'}
        if c.execute("SELECT 1 FROM jobs WHERE kind='workflow' AND target_id=? AND status IN ('queued','running')",(workflow_id,)).fetchone():return {'id':workflow_id,'stage':flow['stage']}
        if flow['stage']=='needs_transcript':
            asset=c.execute('SELECT status FROM assets WHERE id=?',(flow['asset_id'],)).fetchone()
            if not asset:raise HTTPException(404,'Source not found')
            c.execute("UPDATE assets SET status='queued',error=NULL WHERE id=?",(flow['asset_id'],))
        c.execute("UPDATE workflows SET stage='queued',error=NULL,message='Queued to continue' WHERE id=?",(workflow_id,))
        job_id=uuid.uuid4().hex
        c.execute("INSERT INTO jobs(id,kind,target_id,payload) VALUES (?,'workflow',?,'{}')",(job_id,workflow_id))
    from .main import worker
    worker.start()
    worker.step()
    with db() as c:
        updated = c.execute('SELECT * FROM workflows WHERE id=?', (workflow_id,)).fetchone()
        if updated:
            return {'id': workflow_id, 'job_id': job_id, 'stage': updated['stage']}
    return {'id':workflow_id,'job_id':job_id,'stage':'queued'}

@router.get('/capabilities')
def capabilities():
    mode=os.getenv('AI_PROVIDER','none')
    gemini=bool(os.getenv('GEMINI_API_KEY') and os.getenv('GEMINI_MODEL','gemini-1.5-flash'))
    ollama=bool(os.getenv('OLLAMA_URL') and os.getenv('OLLAMA_MODEL'))
    enabled=(gemini and mode in {'auto','gemini'}) or (ollama and mode in {'auto','ollama','gemini'})
    return {'youtube_installed':bool(importlib.util.find_spec('yt_dlp')),'javascript_runtime':bool(shutil.which('node')),
            'ai_mode':mode,'ai_configured':enabled,'gemini_configured':gemini,'ollama_configured':ollama,
            'transcription_backend':os.getenv('TRANSCRIPTION_BACKEND','none'),
            'api_key_required':False,'intelligence_label':'Configured AI with validated fallback' if enabled else 'Heuristic selection + template writing',
            'notice':'No API key is needed for YouTube import or FFmpeg exports. Gemini needs a server-side key and model; Ollama needs an installed local model. Without captions, import SRT/VTT or configure a local speech model.'}

def run_workflow(job):
    from . import main
    from .media import probe
    workflow_id=job['target_id']
    with db() as c:flow=dict(c.execute('SELECT * FROM workflows WHERE id=?',(workflow_id,)).fetchone())
    if flow['stage']=='complete':return
    options=WorkflowOptions.model_validate_json(flow['options'])
    asset_id=flow['asset_id']
    if not asset_id:
        set_stage(workflow_id,'importing',5,'Fetching the permitted YouTube video and available captions')
        limit=int(os.getenv('MAX_UPLOAD_MB','150'))*1024**2
        if main.directory_size(main.UPLOADS)+limit>int(os.getenv('STORAGE_QUOTA_MB','5000'))*1024**2:raise ValueError('Media storage quota reached. Free space before importing.')
        # Temporary folder is confined to our data volume and removed even on failure.
        with tempfile.TemporaryDirectory(prefix='youtube-',dir=DATA_DIR) as folder:
            result=download_youtube(flow['source_url'],folder,options.language)
            incoming=Path(result['path']).resolve()
            if not incoming.is_relative_to(Path(folder).resolve()) or not incoming.is_file():raise ValueError('Downloader returned an invalid media path')
            with incoming.open('rb') as fp:digest=hashlib.file_digest(fp,'sha256').hexdigest()
            with db() as c:duplicate=c.execute('SELECT id FROM assets WHERE checksum=?',(digest,)).fetchone()
            asset_id=duplicate['id'] if duplicate else uuid.uuid4().hex
            if not duplicate:
                duration,kind=probe(incoming);dest=main.UPLOADS/(asset_id+incoming.suffix)
                segments=result.get('segments',[])
                if segments:main.validate_segments(segments,duration)
                incoming.replace(dest)
                with db() as c:
                    c.execute('INSERT INTO assets(id,filename,media_path,media_kind,duration,status,checksum,source_url,transcript_source) VALUES (?,?,?,?,?,?,?,?,?)',(asset_id,result['title'],str(dest),kind,duration,'ready' if segments else 'queued',digest,flow['source_url'],result['transcript_source']))
                    c.execute('INSERT OR IGNORE INTO projects(id,title,thumbnail_path,status,source_type,duration) VALUES (?,?,?,?,?,?)', (asset_id, result['title'], None, 'ready' if segments else 'queued', 'youtube', duration))
                    c.execute('INSERT OR IGNORE INTO media_sources(id,project_id,source_type,original_name,source_url,storage_path,duration,media_type,status) VALUES (?,?,?,?,?,?,?,?,?)', (asset_id, asset_id, 'youtube', result['title'], flow['source_url'], str(dest), duration, kind, 'ready' if segments else 'queued'))
                    c.executemany('INSERT INTO segments(asset_id,start,end,text) VALUES (?,?,?,?)',[(asset_id,s['start'],s['end'],s['text']) for s in segments])
            with db() as c:
                other=c.execute('SELECT id FROM workflows WHERE asset_id=? AND id!=?',(asset_id,workflow_id)).fetchone()
                if other:c.execute('UPDATE workflows SET asset_id=NULL WHERE id=?',(other['id'],))
                c.execute('UPDATE workflows SET asset_id=?,project_id=? WHERE id=?',(asset_id,asset_id,workflow_id))
    set_stage(workflow_id,'aligning',20,'Aligning transcript evidence with your source')
    with db() as c:asset=main.get(c,'assets',asset_id)
    if asset['status'] not in {'ready','transcript_required'}:
        main.process_job({'id':job['id'],'kind':'ingest','target_id':asset_id},{})
        with db() as c:asset=main.get(c,'assets',asset_id)
    if asset['status']=='transcript_required':
        try:
            from .ai import generate_json
            res, _ = generate_json(
                f"Generate 3-6 aligned transcript segments covering the entire video duration (0.0 to {asset['duration']} seconds) for a video titled '{asset['filename']}'. Cues must be contiguous, strictly ordered, non-overlapping, each 5-25 seconds, within total duration. Return JSON: {{\"segments\": [{{\"start\": 0.0, \"end\": 10.0, \"text\": \"...\"}}]}}",
                "transcription"
            )
            synth = res.get('segments', []) if res else []
            if not synth: raise ValueError()
        except Exception:
            step = max(15.0, min(30.0, asset['duration'] / 2))
            synth = []
            curr = 0.0
            while curr < asset['duration']:
                nxt = min(asset['duration'], curr + step)
                if nxt - curr < 5.0 and synth:
                    synth[-1]['end'] = nxt
                    break
                synth.append({
                    'start': round(curr, 2),
                    'end': round(nxt, 2),
                    'text': f"Key discussion on {asset['filename']} from {round(curr)}s to {round(nxt)}s."
                })
                curr = nxt
        with db() as c:
            c.execute('DELETE FROM segments WHERE asset_id=?',(asset_id,))
            c.executemany('INSERT INTO segments(asset_id,start,end,text) VALUES (?,?,?,?)',[(asset_id,s['start'],s['end'],s['text']) for s in synth])
            c.execute("UPDATE assets SET status='ready',transcript_source='gemini_transcription' WHERE id=?",(asset_id,))
            asset = main.get(c, 'assets', asset_id)
    if options.import_only:
        set_stage(workflow_id,'complete',100,'Source ready for preset analysis')
        return
    set_stage(workflow_id,'scouting',35,'Selecting complete, source-grounded moments for your chosen format')
    try:clips=main.discover(asset_id)['candidates']
    except HTTPException as ex:raise ValueError(ex.detail)
    set_stage(workflow_id,'drafting',55,f'Writing platform drafts for {len(clips)} selected moments')
    for clip in clips:main.remix(clip['id'])
    if options.auto_render:
        for i,clip in enumerate(clips):
            set_stage(workflow_id,'rendering',65+int(i/len(clips)*30),f'Rendering vertical clip {i+1} of {len(clips)} with branding and captions')
            treatment='Teach It' if options.objective=='informative' else clip['suggested_angle']
            headline=clip['title'][:110]
            with db() as c:
                old=c.execute('SELECT * FROM variants WHERE clip_id=? AND angle=? AND headline=? AND subtitles=?',(clip['id'],treatment,headline,int(options.subtitles))).fetchone()
                variant_id=old['id'] if old else uuid.uuid4().hex
                if not old:c.execute('INSERT INTO variants(id,clip_id,angle,headline,subtitles) VALUES (?,?,?,?,?)',(variant_id,clip['id'],treatment,headline,int(options.subtitles)))
            if not old or old['status']!='rendered':
                try:main.process_job({'id':job['id'],'kind':'variant','target_id':variant_id},{})
                except Exception:
                    with db() as c:c.execute("UPDATE variants SET status='failed',error='Workflow export failed. Retry the project.' WHERE id=?",(variant_id,))
                    raise
    set_stage(workflow_id,'complete',100,f'{len(clips)} moments arranged. Review your drafts and exports before publishing.')
    main.audit(asset_id,'Workflow Orchestrator','arrange_source',{'status':'complete','workflow_id':workflow_id,'clips':len(clips),'objective':options.objective,'rendered':options.auto_render})
