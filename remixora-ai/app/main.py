"""REMIXORA: persistent single-creator media studio. Run one ASGI worker."""
import base64
import csv
import difflib
import hashlib
import io
import json
import os
import secrets
import shutil
import sqlite3
import time
import uuid
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .ai import ANGLES, PLATFORMS, generate_json, infer_rules, make_copies, provider_status
from .agents import Candidate, Rubric, ScoutResult, ROLES
from .db import DATA_DIR, db, init_db, rows
from .jobs import DurableWorker, enqueue
from .media import candidates, classify_angle, parse_subtitles, probe, render, render_variant, transcribe

UPLOADS=DATA_DIR/'uploads'; EXPORTS=DATA_DIR/'exports'
UPLOADS.mkdir(exist_ok=True); EXPORTS.mkdir(exist_ok=True)
STATIC=Path(__file__).parent/'static'
def uid():return uuid.uuid4().hex
def revision(c,name):return c.execute('SELECT value FROM revisions WHERE name=?',(name,)).fetchone()[0]
def bump(c,name):c.execute('UPDATE revisions SET value=value+1 WHERE name=?',(name,))
def get(c,table,item_id):
    row=c.execute(f'SELECT * FROM {table} WHERE id=?',(item_id,)).fetchone()
    if not row:raise HTTPException(404,'Record not found')
    return dict(row)
def audit(asset_id,agent,action,result):
    with db() as c:c.execute('INSERT INTO agent_events(asset_id,agent,action,result) VALUES (?,?,?,?)',(asset_id,agent,action,json.dumps(result) if not isinstance(result,str) else result))

def validate_segments(segments,duration):
    if not segments or len(segments)>10000:raise ValueError('Provide 1â€“10000 aligned transcript segments')
    previous=0
    for s in segments:
        if not (previous<=s['start']<s['end']<=duration+.05) or not s['text'].strip() or len(s['text'])>4000:
            raise ValueError('Transcript cues must be ordered, non-overlapping and within the source duration')
        previous=s['end']

def process_job(job,payload):
    target=job['target_id']
    if job['kind'] in {'preset_analyze','preset_render'}:
        from .presets import process_analysis,process_render
        return (process_analysis if job['kind']=='preset_analyze' else process_render)(job)
    if job['kind']=='workflow':
        from .workflow import run_workflow
        return run_workflow(job)
    elif job['kind']=='ingest':
        with db() as c:
            asset=get(c,'assets',target)
            c.execute("UPDATE assets SET status='probing',error=NULL WHERE id=?",(target,))
        duration,kind=probe(asset['media_path'])
        with db() as c:c.execute('UPDATE assets SET duration=?,media_kind=?,status=? WHERE id=?',(duration,kind,'aligning' if payload.get('transcript') else 'transcribing',target))
        if payload.get('transcript'):segments=parse_subtitles(payload['transcript'])
        else:
            try:
                segments=transcribe(asset['media_path'])
                # Speech models can round the final cue past EOF by a fraction.
                # Keep evidence inside the actual media, leaving other validation strict.
                segments=[{**s,'end':min(s['end'],duration)} for s in segments if s['start']<min(s['end'],duration)]
            except RuntimeError:
                with db() as c:c.execute("UPDATE assets SET status='transcript_required',error='Import a source-matched SRT/VTT, or configure a local transcription model.' WHERE id=?",(target,))
                audit(target,'Ingestion Agent','transcribe_media',{'status':'transcript_required','job_id':job['id']})
                return
        validate_segments(segments,duration)
        with db() as c:
            c.execute('DELETE FROM segments WHERE asset_id=?',(target,))
            c.executemany('INSERT INTO segments(asset_id,start,end,text) VALUES (?,?,?,?)',[(target,s['start'],s['end'],s['text']) for s in segments])
            c.execute("UPDATE assets SET status='ready',error=NULL,transcript_source=? WHERE id=?",('imported_captions' if payload.get('transcript') else 'local_speech',target))
            c.execute("UPDATE projects SET status='ready',duration=? WHERE id=?",(duration,target))
            c.execute("UPDATE media_sources SET status='ready',duration=? WHERE id=?",(duration,target))
        audit(target,'Ingestion Agent','align_transcript',{'status':'ready','segments':len(segments),'job_id':job['id']})
    elif job['kind'] == 'project_render':
        from .media import generate_thumbnail, probe_output
        render_id = target
        project_id = payload['project_id']
        dest = Path(payload['dest_path'])
        dest.parent.mkdir(parents=True, exist_ok=True)
        with db() as c:
            asset = c.execute("SELECT * FROM assets WHERE id = ?", (project_id,)).fetchone()
            if not asset:
                src = c.execute("SELECT * FROM media_sources WHERE project_id = ?", (project_id,)).fetchone()
                source_path = src['storage_path']
                media_kind = src['media_type']
            else:
                source_path = asset['media_path']
                media_kind = asset['media_kind']
            segments = rows(c.execute("SELECT * FROM segments WHERE asset_id = ? ORDER BY start", (project_id,)))

        temp = dest.with_name(render_id + '.partial.mp4')
        render_variant(
            source=source_path,
            dest=temp,
            start=payload['start'],
            end=payload['end'],
            is_video=(media_kind == 'video'),
            headline=payload.get('headline', ''),
            angle='Teach It',
            segments=segments,
            subtitles=bool(payload.get('burn_subtitles', True)) and bool(segments),
            aspect_ratio=payload.get('aspect_ratio', '9:16'),
        )
        temp.replace(dest)
        actual_dur, _ = probe_output(dest)

        thumb_dest = dest.parent.parent / "thumbnails" / f"{render_id}.jpg"
        thumb_path = generate_thumbnail(dest, thumb_dest, timestamp=min(0.5, actual_dur / 2))

        with db() as c:
            c.execute(
                """UPDATE rendered_clips
                   SET status = 'rendered', duration = ?, thumbnail_path = ?
                   WHERE id = ?""",
                (actual_dur, str(thumb_path) if thumb_path else None, render_id)
            )
            c.execute("UPDATE clip_candidates SET status = 'approved' WHERE id = ?", (payload.get('candidate_id'),))
            if payload.get('clip_id'):
                c.execute("UPDATE clips SET render_status = 'rendered', output_path = ? WHERE id = ?", (str(dest), payload['clip_id']))
        audit(project_id, 'Remix Director', 'render_video_clip', {'status': 'rendered', 'render_id': render_id})
    elif job['kind'] in {'render','variant'}:
        with db() as c:
            variant=get(c,'variants',target) if job['kind']=='variant' else None
            clip=get(c,'clips',variant['clip_id'] if variant else target)
            asset=get(c,'assets',clip['asset_id'])
            segments=rows(c.execute('SELECT * FROM segments WHERE asset_id=? ORDER BY start',(asset['id'],)))
            if variant:c.execute("UPDATE variants SET status='rendering',error=NULL WHERE id=?",(target,))
            else:c.execute("UPDATE clips SET render_status='rendering' WHERE id=?",(target,))
        suffix='.mp4' if variant or asset['media_kind']=='video' else '.m4a'
        dest=EXPORTS/(target+suffix)
        if variant:render_variant(asset['media_path'],dest,clip['start'],clip['end'],asset['media_kind']=='video',variant['headline'],variant['angle'],segments,bool(variant['subtitles']))
        else:
            temp=EXPORTS/(target+'.partial'+suffix)
            render(asset['media_path'],temp,clip['start'],clip['end'],asset['media_kind']=='video')
            temp.replace(dest)
        with db() as c:
            if variant:c.execute("UPDATE variants SET status='rendered',output_path=? WHERE id=?",(str(dest),target))
            else:c.execute("UPDATE clips SET render_status='rendered',output_path=? WHERE id=?",(str(dest),target))
        audit(asset['id'],'Remix Director','render_video_clip',{'status':'rendered','job_id':job['id'],'variant':bool(variant)})
    else:raise ValueError('Unknown job type')

worker=DurableWorker(process_job)
@asynccontextmanager
async def lifespan(app):
    if os.getenv('DEPLOY_MODE')=='production' and (len(os.getenv('AUTH_PASSWORD',''))<16 or not os.getenv('AUTH_USER') or os.getenv('AUTH_PASSWORD','').startswith('CHOOSE_')):
        raise RuntimeError('Production requires AUTH_USER and a non-placeholder password of at least 16 characters')
    init_db();worker.start()
    yield
    worker.close()

app=FastAPI(title='REMIXORA AI',version='1.0.0',lifespan=lifespan)

class BodyLimitMiddleware:
    """Bound chunked requests before multipart parsing can spool unlimited data."""
    def __init__(self,app):self.app=app
    async def __call__(self,scope,receive,send):
        if scope['type']!='http':return await self.app(scope,receive,send)
        received=0
        cap=int(os.getenv('MAX_UPLOAD_MB','150'))*1024*1024+2_100_000
        async def limited_receive():
            nonlocal received
            message=await receive()
            received+=len(message.get('body',b''))
            if received>cap:raise HTTPException(413,'Request body exceeds configured size limit')
            return message
        await self.app(scope,limited_receive,send)

app.add_middleware(BodyLimitMiddleware)
attempts=defaultdict(deque)
@app.middleware('http')
async def protect(request:Request,call_next):
    if request.url.path!='/health':
        user=os.getenv('AUTH_USER');password=os.getenv('AUTH_PASSWORD')
        if user and password:
            try:
                scheme,token=request.headers.get('authorization','').split(' ',1)
                login,_,pw=base64.b64decode(token,validate=True).decode().partition(':')
                allowed=scheme=='Basic' and secrets.compare_digest(login,user) and secrets.compare_digest(pw,password)
            except (ValueError,UnicodeError):allowed=False
            if not allowed:return Response(status_code=401,headers={'WWW-Authenticate':'Basic realm="Remixora Studio"'})
        if request.method not in {'GET','HEAD','OPTIONS'}:
            origin=request.headers.get('origin')
            if origin and origin.rstrip('/') not in {str(request.base_url).rstrip('/'),os.getenv('PUBLIC_ORIGIN','').rstrip('/')}:
                return JSONResponse({'detail':'Cross-origin writes are not allowed'},status_code=403)
            if request.headers.get('sec-fetch-site')=='cross-site':return JSONResponse({'detail':'Cross-site request rejected'},status_code=403)
            bucket=attempts[request.client.host if request.client else 'local'];now=time.monotonic()
            while bucket and bucket[0]<now-60:bucket.popleft()
            if len(bucket)>=120:return JSONResponse({'detail':'Too many requests; retry in one minute'},status_code=429,headers={'Retry-After':'60'})
            bucket.append(now)
            try:length=int(request.headers.get('content-length','0'))
            except ValueError:return JSONResponse({'detail':'Invalid request length'},status_code=400)
            cap=int(os.getenv('MAX_UPLOAD_MB','150'))*1024*1024+2_100_000
            if length>cap:return JSONResponse({'detail':'Upload exceeds configured limit'},status_code=413)
    response=await call_next(request)
    response.headers.update({'X-Content-Type-Options':'nosniff','Referrer-Policy':'same-origin','X-Frame-Options':'DENY','Content-Security-Policy':"default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self'; img-src 'self' data:; media-src 'self' blob:; connect-src 'self'; frame-ancestors 'none'"})
    if request.url.path.startswith('/api'):response.headers['Cache-Control']='no-store'
    return response

@app.exception_handler(ValueError)
async def value_error(request,ex):return JSONResponse({'detail':str(ex)[:250]},status_code=400)

@app.exception_handler(Exception)
async def unexpected_error(request,ex):
    import logging
    logging.getLogger('remixora').error('Request failed: %s',type(ex).__name__)
    return JSONResponse({'detail':'The operation could not finish. Check System Health and retry.'},status_code=500)

@app.get('/health')
def health():
    with db() as c:c.execute('SELECT 1')
    return {'status':'ok','worker_alive':bool(worker.thread and worker.thread.is_alive())}
@app.get('/debug')
def debug_endpoint(request: Request):
    return {
        "url": str(request.url),
        "path": request.url.path,
        "scope_path": request.scope.get("path"),
        "headers": dict(request.headers)
    }

@app.get('/')
@app.get('/api/index')
@app.get('/api/index.py')
def home():return FileResponse(STATIC/'index.html')

app.mount('/static',StaticFiles(directory=STATIC),name='static')


@app.get('/api/status')
def status():
    from .media import ensure_ffmpeg
    ensure_ffmpeg()
    with db() as c:
        counts={t:c.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0] for t in ['assets','clips','copies','calendar','metrics']}
        rev={r['name']:r['value'] for r in c.execute('SELECT * FROM revisions')}
    usage=directory_size(DATA_DIR)
    return {'providers':provider_status(),'transcription_backend':os.getenv('TRANSCRIPTION_BACKEND','none'),'max_upload_mb':int(os.getenv('MAX_UPLOAD_MB','150')),'max_duration_seconds':int(os.getenv('MAX_DURATION_SECONDS','1800')),'mode':'single-user','counts':counts,'revisions':rev,'ffmpeg':bool(shutil.which('ffmpeg')),'ffprobe':bool(shutil.which('ffprobe')),'storage_bytes':usage,'free_bytes':shutil.disk_usage(DATA_DIR).free,'worker_alive':bool(worker.thread and worker.thread.is_alive()),'authentication':bool(os.getenv('AUTH_USER') and os.getenv('AUTH_PASSWORD')),'agents':[{'name':n,'tools':t} for n,t in ROLES]}


def directory_size(folder):
    """SQLite WAL/SHM and atomic render files may disappear during inspection."""
    import stat
    total=0
    for path in folder.rglob('*'):
        try:
            metadata=path.stat()
            if stat.S_ISREG(metadata.st_mode):total+=metadata.st_size
        except FileNotFoundError:continue
    return total

def read_subtitle(upload):
    if Path(upload.filename or '').suffix.lower() not in {'.srt','.vtt'}:raise HTTPException(400,'Use a source-matched SRT or VTT file')
    raw=upload.file.read(2_000_001)
    if len(raw)>2_000_000:raise HTTPException(413,'Transcript exceeds 2 MB')
    try:text=raw.decode('utf-8-sig')
    except UnicodeError:raise HTTPException(400,'Use UTF-8 subtitles')
    parse_subtitles(text)
    return text

@app.post('/api/assets',status_code=202)
def ingest(media:UploadFile=File(...),transcript:UploadFile|None=File(default=None)):
    ext=Path(media.filename or '').suffix.lower()
    if ext not in {'.mp4','.mov','.mkv','.webm','.mp3','.m4a','.wav'}:raise HTTPException(400,'Unsupported media extension')
    if media.content_type and not (media.content_type.startswith(('video/','audio/')) or media.content_type in {'application/octet-stream','application/mp4'}):raise HTTPException(400,'Upload must have a media content type')
    text=read_subtitle(transcript) if transcript else None
    limit=int(os.getenv('MAX_UPLOAD_MB','150'))*1024*1024
    used=directory_size(UPLOADS)
    if used+limit>int(os.getenv('STORAGE_QUOTA_MB','5000'))*1024*1024 or shutil.disk_usage(DATA_DIR).free<min(limit, 30*1024*1024):raise HTTPException(507,'Insufficient media storage; free space before uploading')
    asset_id=uid();dest=UPLOADS/(asset_id+ext);received=0;digest=hashlib.sha256()
    try:
        with dest.open('wb') as fp:
            while chunk:=media.file.read(1024*1024):
                received+=len(chunk)
                if received>limit:raise HTTPException(413,'Upload exceeds the configured size limit')
                fp.write(chunk);digest.update(chunk)
        if not received:raise ValueError('Empty media upload')
        duration,kind=probe(dest)
        if text:validate_segments(parse_subtitles(text),duration)
    except HTTPException:
        dest.unlink(missing_ok=True);raise
    except Exception as ex:
        dest.unlink(missing_ok=True)
        raise HTTPException(400,str(ex) if isinstance(ex,ValueError) else 'Media inspection failed. Check FFmpeg/FFprobe and upload a valid file with audio.')
    with db() as c:
        previous=c.execute('SELECT id,status FROM assets WHERE checksum=?',(digest.hexdigest(),)).fetchone()
        if previous:
            dest.unlink(missing_ok=True)
            return {'asset_id':previous['id'],'status':previous['status'],'duplicate':True}
        from .media import generate_thumbnail
        thumb_dest = UPLOADS / (asset_id + '.jpg')
        thumb_path = generate_thumbnail(dest, thumb_dest, timestamp=min(1.0, duration / 2))
        c.execute('INSERT INTO assets(id,project_id,filename,media_path,media_kind,duration,status,checksum) VALUES (?,?,?,?,?,?,?,?)',(asset_id,asset_id,Path(media.filename).name,str(dest),kind,duration,'queued',digest.hexdigest()))
        c.execute('INSERT OR IGNORE INTO projects(id,title,thumbnail_path,status,source_type,duration) VALUES (?,?,?,?,?,?)', (asset_id, Path(media.filename).name, str(thumb_path) if thumb_path else None, 'queued', 'upload', duration))
        c.execute('INSERT OR IGNORE INTO media_sources(id,project_id,source_type,original_name,storage_path,duration,media_type,status) VALUES (?,?,?,?,?,?,?,?)', (asset_id, asset_id, 'upload', Path(media.filename).name, str(dest), duration, kind, 'queued'))
    job_id=enqueue('ingest',asset_id,{'transcript':text})
    return {'asset_id':asset_id,'status':'queued','job_id':job_id,'duration_seconds':duration}

@app.get('/api/assets')
def assets():
    with db() as c:return rows(c.execute('SELECT id,filename,media_kind,duration,status,error,created_at FROM assets ORDER BY rowid DESC'))
@app.get('/api/assets/{asset_id}/media')
def source_media(asset_id:str):
    with db() as c:asset=get(c,'assets',asset_id)
    path=Path(asset['media_path']).resolve()
    if not path.is_relative_to(UPLOADS) or not path.is_file():raise HTTPException(404,'Source no longer available')
    return FileResponse(path)
@app.get('/api/assets/{asset_id}/transcript')
def transcript(asset_id:str):
    with db() as c:
        get(c,'assets',asset_id)
        return rows(c.execute('SELECT id,start,end,text FROM segments WHERE asset_id=? ORDER BY start',(asset_id,)))

def save_segments(asset_id,segments):
    with db() as c:
        asset=get(c,'assets',asset_id)
        if c.execute("SELECT 1 FROM jobs WHERE status IN ('queued','running') AND (target_id=? OR target_id IN (SELECT id FROM workflows WHERE asset_id=?))",(asset_id,asset_id)).fetchone():raise HTTPException(409,'Wait for the ingestion workflow to finish')
        if c.execute('SELECT 1 FROM clips WHERE asset_id=?',(asset_id,)).fetchone():raise HTTPException(409,'Transcript is frozen after discovery to preserve clip evidence. Upload a revised source as a new project.')
        validate_segments(segments,asset['duration'])
        c.execute('DELETE FROM segments WHERE asset_id=?',(asset_id,))
        c.executemany('INSERT INTO segments(asset_id,start,end,text) VALUES (?,?,?,?)',[(asset_id,s['start'],s['end'],s['text']) for s in segments])
        c.execute("UPDATE assets SET status='ready',error=NULL,transcript_source='creator_captions' WHERE id=?",(asset_id,))
    return {'segments':len(segments),'status':'ready'}
@app.post('/api/assets/{asset_id}/transcript')
def attach_transcript(asset_id:str,transcript:UploadFile=File(...)):return save_segments(asset_id,parse_subtitles(read_subtitle(transcript)))
class Segment(BaseModel):
    start:float=Field(ge=0,allow_inf_nan=False)
    end:float=Field(gt=0,allow_inf_nan=False)
    text:str=Field(min_length=1,max_length=4000)
class TranscriptEdit(BaseModel):
    segments:list[Segment]=Field(min_length=1,max_length=10000)
@app.put('/api/assets/{asset_id}/transcript')
def repair_transcript(asset_id:str,req:TranscriptEdit):return save_segments(asset_id,[s.model_dump() for s in req.segments])

def performance_summary():
    with db() as c:
        data=rows(c.execute("SELECT platform,angle,period,source,COUNT(DISTINCT clip_id) AS n,SUM(likes+comments+shares+saves) AS engagement,SUM(impressions) AS impressions FROM metrics WHERE impressions>0 GROUP BY platform,angle,period,source"))
        rev=revision(c,'performance')
    for r in data:r.update(smoothed_rate=round((r['engagement']+9)/(r['impressions']+300),6),eligible=r['n']>=3,raw_rate=r['engagement']/r['impressions'])
    return {'groups':data,'revision':rev,'note':'At least 3 distinct clips per platform, angle and measurement period. Synthetic samples are isolated from actual outcomes. Small samples are uncertain; no causal lift is claimed.'}

@app.post('/api/assets/{asset_id}/discover')
def discover(asset_id:str):
    with db() as c:
        asset=get(c,'assets',asset_id)
        if asset['status']!='ready':raise HTTPException(409,'Import an aligned transcript first')
        previous=rows(c.execute('SELECT * FROM clips WHERE asset_id=? AND preset_id IS NULL ORDER BY score DESC',(asset_id,)))
        if previous:return {'candidates':previous,'cached':True}
        seg=rows(c.execute('SELECT * FROM segments WHERE asset_id=? ORDER BY start',(asset_id,)))
        flow=c.execute('SELECT options FROM workflows WHERE asset_id=?',(asset_id,)).fetchone()
        options=json.loads(flow['options']) if flow else {}
        clip_count=options.get('clip_count',3);target_seconds=options.get('target_seconds',24);objective=options.get('objective','shorts')
        brand_rev=revision(c,'brand');perf_rev=revision(c,'performance')
        rules=rows(c.execute("SELECT text FROM brand_rules WHERE status='approved'"))
    pool=candidates(seg,asset['duration'],count=30,target_seconds=target_seconds,objective=objective)
    windows=[]
    for candidate in pool:
        indices=[i for i,x in enumerate(seg) if x['start']>=candidate['start'] and x['end']<=candidate['end']]
        if indices:windows.append({'first':indices[0],'last':indices[-1],'seconds':round(candidate['end']-candidate['start'],2),'evidence':candidate['quote'][:420]})
    prompt=f'Select up to {clip_count} strongest source-grounded windows for {objective}, aiming for {target_seconds} seconds. Return JSON only: {{"clips":[{{"first":0,"last":2,"title":"source-based headline","reason":"editorial reason"}}]}}. Copy first and last EXACTLY from a supplied window. These are segment indices, not seconds. The tool already validated timing. Do not merge windows or invent claims. Prefer complete useful explanations for informative clips and compelling opening hooks for shorts.'
    response,provider=generate_json(prompt,json.dumps({'windows':windows,'approved_rules':rules,'brand_revision':brand_rev,'performance_revision':perf_rev}))
    items=[]
    try:
        proposals=ScoutResult.model_validate(response).clips if response else []
        for p in proposals:
            if not (0<=p.first<=p.last<len(seg)):continue
            if not any(w['first']==p.first and w['last']==p.last for w in windows):continue
            start=seg[p.first]['start'];end=seg[p.last]['end']
            if not 15<=end-start<=60:continue
            if any(min(end,x['end'])>max(start,x['start']) for x in items):continue
            quote=' '.join(s['text'] for s in seg[p.first:p.last+1])
            items.append(dict(start=start,end=end,quote=quote,title=p.title,reason=p.reason,score=3.5,source=provider))
    except ValueError:pass
    for item in candidates(seg,asset['duration'],count=15,target_seconds=target_seconds,objective=objective):
        if len(items)>=6:break
        if all(min(item['end'],x['end'])<=max(item['start'],x['start']) for x in items):items.append(item)
    if not items:raise HTTPException(422,'At least 15 seconds of aligned speech is required')
    insight=performance_summary()
    relevant=[g for g in insight['groups'] if g['platform']=='instagram' and g['eligible'] and g['period']=='lifetime' and g['source']=='actual']
    average=sum(g['smoothed_rate'] for g in relevant)/len(relevant) if relevant else 0
    for item in items:
        angle=classify_angle(item['quote']);group=next((g for g in relevant if g['angle']==angle),None)
        adjustment=round(max(-.75,min(.75,(group['smoothed_rate']-average)*12)),3) if group and len(relevant)>1 else 0
        item.update(id=uid(),asset_id=asset_id,suggested_angle=angle,base_score=item['score'],adjustment=adjustment,performance_revision=perf_rev)
        item['score']=round(min(5,max(0,item['base_score']+adjustment)),3)
        if group:item['reason']+=f" Feedback: {group['n']} actual Instagram clips; adjustment {adjustment:+.3f}, smoothed engagement {group['smoothed_rate']:.2%}."
        evidence=[s['id'] for s in seg if s['start']>=item['start'] and s['end']<=item['end']]
        rubric=Rubric(clarity=min(5,item['base_score']+.2),usefulness=item['base_score'],opening_hook=min(5,item['base_score']+(.4 if '?' in item['quote'] else 0)),brand_relevance=3 if rules else 2.5)
        validated=Candidate(id=item['id'],source_id=asset_id,start_ms=round(item['start']*1000),end_ms=round(item['end']*1000),headline=item['title'],topical_hook=angle,rubric=rubric,evidence_segment_ids=evidence,exact_quote=item['quote'],selection_reason=item['reason'])
        item['evidence']=json.dumps(validated.evidence_segment_ids);item['rubric']=rubric.model_dump_json()
    items.sort(key=lambda x:(x['source'] in {'gemini','ollama'},x['score']),reverse=True);items=items[:clip_count]
    with db() as c:
        c.execute('BEGIN IMMEDIATE')
        concurrent=rows(c.execute('SELECT * FROM clips WHERE asset_id=? AND preset_id IS NULL ORDER BY score DESC',(asset_id,)))
        if concurrent:return {'candidates':concurrent,'cached':True}
        for item in items:
            keys=list(item);c.execute(f'INSERT INTO clips({",".join(keys)}) VALUES ({",".join("?" for _ in keys)})',list(item.values()))
    audit(asset_id,'Content Scout','rank_candidates',{'status':'candidates_ready','provider':provider if response else 'heuristic','count':len(items),'brand_revision':brand_rev,'performance_revision':perf_rev})
    return {'candidates':items,'cached':False}

@app.get('/api/clips')
def list_clips():
    with db() as c:return rows(c.execute('SELECT * FROM clips ORDER BY rowid DESC'))
@app.post('/api/clips/{clip_id}/render',status_code=202)
def render_clip(clip_id:str):
    with db() as c:
        clip=get(c,'clips',clip_id)
        if clip['render_status']=='rendered':return {'status':'rendered'}
    return {'status':'queued','job_id':enqueue('render',clip_id)}
class VariantRequest(BaseModel):
    angle:Literal['Teach It','Tell It','Challenge It']
    headline:str=Field(min_length=3,max_length=120)
    subtitles:bool=True
@app.post('/api/clips/{clip_id}/variants',status_code=202)
def create_variant(clip_id:str,req:VariantRequest):
    with db() as c:
        get(c,'clips',clip_id)
        old=c.execute('SELECT * FROM variants WHERE clip_id=? AND angle=? AND headline=? AND subtitles=?',(clip_id,req.angle,req.headline,int(req.subtitles))).fetchone()
        variant_id=old['id'] if old else uid()
        if not old:c.execute('INSERT INTO variants(id,clip_id,angle,headline,subtitles) VALUES (?,?,?,?,?)',(variant_id,clip_id,req.angle,req.headline,int(req.subtitles)))
        if old and old['status']=='rendered':return {'id':variant_id,'status':'rendered'}
    return {'id':variant_id,'status':'queued','job_id':enqueue('variant',variant_id)}
@app.get('/api/variants')
def variants():
    with db() as c:return rows(c.execute('SELECT id,clip_id,angle,headline,subtitles,status,error FROM variants ORDER BY rowid DESC'))
def output_file(table,item_id):
    with db() as c:item=get(c,table,item_id)
    path=Path(item.get('output_path') or '').resolve()
    if not path.is_relative_to(EXPORTS) or not path.is_file():raise HTTPException(404,'Export is not ready')
    return FileResponse(path,media_type='video/mp4' if path.suffix=='.mp4' else 'audio/mp4',filename=f'remixora-{item_id}{path.suffix}')
@app.get('/api/clips/{clip_id}/download')
def download(clip_id:str):return output_file('clips',clip_id)
@app.get('/api/variants/{variant_id}/download')
def download_variant(variant_id:str):return output_file('variants',variant_id)

@app.post('/api/clips/{clip_id}/remix')
def remix(clip_id:str):
    with db() as c:
        clip=get(c,'clips',clip_id)
        existing=rows(c.execute('SELECT * FROM copies WHERE clip_id=?',(clip_id,)))
        if existing:return {'copies':existing,'cached':True}
        rules=rows(c.execute("SELECT * FROM brand_rules WHERE status='approved'"));rev=revision(c,'brand')
        profile=json.loads(c.execute('SELECT content FROM profile WHERE id=1').fetchone()[0])
    generated=make_copies(clip,rules,profile)
    with db() as c:
        c.execute('BEGIN IMMEDIATE')
        concurrent=rows(c.execute('SELECT * FROM copies WHERE clip_id=?',(clip_id,)))
        if concurrent:return {'copies':concurrent,'cached':True}
        for platform,angle,text,source in generated:
            c.execute('INSERT INTO copies(id,clip_id,platform,angle,content,source,rules_used,brand_revision) VALUES (?,?,?,?,?,?,?,?)',(uid(),clip_id,platform,angle,text,source,json.dumps([{'id':r['id'],'text':r['text']} for r in rules]),rev))
        result=rows(c.execute('SELECT * FROM copies WHERE clip_id=?',(clip_id,)))
    audit(clip['asset_id'],'Platform Copywriter','generate_platform_copy',{'count':len(result),'provider':result[0]['source'],'brand_revision':rev})
    return {'copies':result,'cached':False}
@app.get('/api/copies')
def all_copies():
    with db() as c:return rows(c.execute('SELECT * FROM copies ORDER BY rowid DESC'))
class EditCopy(BaseModel):
    content:str=Field(min_length=3,max_length=2500)
@app.patch('/api/copies/{copy_id}')
def edit_copy(copy_id:str,req:EditCopy):
    with db() as c:
        old=get(c,'copies',copy_id)
        if old['content']==req.content:return {'saved':True,'proposed_rules':[]}
        edit_id=uid();diff='\n'.join(difflib.unified_diff(old['content'].splitlines(),req.content.splitlines(),lineterm=''))
        c.execute('INSERT INTO edits(id,copy_id,original,revised,diff) VALUES (?,?,?,?,?)',(edit_id,copy_id,old['content'],req.content,diff))
        c.execute('UPDATE copies SET content=?,approved=0,updated_at=CURRENT_TIMESTAMP WHERE id=?',(req.content,copy_id))
        proposals=[]
        for text in infer_rules(old['content'],req.content):
            rule_id=uid();c.execute('INSERT INTO brand_rules(id,text,evidence_edit_id) VALUES (?,?,?)',(rule_id,text,edit_id));proposals.append({'id':rule_id,'text':text,'status':'pending'})
    audit(None,'Brand Memory Curator','suggest_brand_rule',{'status':'awaiting_approval','count':len(proposals),'provider':'deterministic'})
    return {'saved':True,'proposed_rules':proposals}
@app.post('/api/copies/{copy_id}/rollback')
def rollback(copy_id:str):
    with db() as c:
        old=c.execute('SELECT * FROM edits WHERE copy_id=? ORDER BY rowid DESC LIMIT 1',(copy_id,)).fetchone()
        if not old:raise HTTPException(409,'No revision available')
        original=old['original']
    return edit_copy(copy_id,EditCopy(content=original))
@app.post('/api/copies/{copy_id}/approve')
def approve_copy(copy_id:str):
    with db() as c:get(c,'copies',copy_id);c.execute('UPDATE copies SET approved=1 WHERE id=?',(copy_id,))
    return {'approved':True}
@app.get('/api/copies/{copy_id}/download')
def copy_download(copy_id:str):
    with db() as c:item=get(c,'copies',copy_id)
    return Response(item['content'],media_type='text/plain',headers={'Content-Disposition':f'attachment; filename="remixora-{copy_id}.txt"'})

@app.get('/api/brand-rules')
def get_brand_rules():
    with db() as c:return rows(c.execute('SELECT brand_rules.*,edits.original,edits.revised,edits.diff FROM brand_rules LEFT JOIN edits ON edits.id=brand_rules.evidence_edit_id ORDER BY brand_rules.rowid DESC'))
class NewRule(BaseModel):
    text:str=Field(min_length=5,max_length=250)
@app.post('/api/brand-rules')
def add_rule(rule:NewRule):
    with db() as c:c.execute("INSERT INTO brand_rules(id,text,status) VALUES (?,?,'approved')",(uid(),rule.text));bump(c,'brand')
    return {'saved':True}
@app.post('/api/brand-rules/{rule_id}/approve')
def approve_rule(rule_id:str):
    with db() as c:
        get(c,'brand_rules',rule_id)
        if c.execute("UPDATE brand_rules SET status='approved' WHERE id=? AND status!='approved'",(rule_id,)).rowcount:bump(c,'brand')
    return {'approved':True}
@app.delete('/api/brand-rules/{rule_id}')
def deactivate_rule(rule_id:str):
    with db() as c:get(c,'brand_rules',rule_id);c.execute("UPDATE brand_rules SET status='inactive' WHERE id=?",(rule_id,));bump(c,'brand')
    return {'deactivated':True}
class Profile(BaseModel):
    audience:str=Field(default='Curious creators',max_length=200)
    tone:str=Field(default='Practical and conversational',max_length=200)
    language:str=Field(default='English',max_length=50)
    formality:Literal['casual','balanced','formal']='balanced'
    sentence_length:Literal['short','balanced','detailed']='balanced'
    cta_pattern:str=Field(default='Ask a thoughtful question',max_length=200)
    emojis:bool=False
    hashtags:bool=True
    banned_phrases:str=Field(default='',max_length=500)
    preferred_vocabulary:str=Field(default='',max_length=500)
@app.get('/api/profile')
def get_profile():
    with db() as c:return {'profile':Profile(**json.loads(c.execute('SELECT content FROM profile WHERE id=1').fetchone()[0])).model_dump(),'revision':revision(c,'brand')}
@app.put('/api/profile')
def set_profile(req:Profile):
    with db() as c:c.execute('UPDATE profile SET content=? WHERE id=1',(req.model_dump_json(),));bump(c,'brand')
    return {'saved':True}

class CalendarRequest(BaseModel):
    copy_id:str
    scheduled_at:str=Field(min_length=16,max_length=40)
    timezone:str=Field(default='Asia/Kolkata',max_length=70)
    status:Literal['draft','approved','scheduled_in_app','manually_published','cancelled']='scheduled_in_app'
    caption:str=Field(default='',max_length=2500)
def schedule_time(value,zone):
    try:
        tz=ZoneInfo(zone);dt=datetime.fromisoformat(value.replace('Z','+00:00'))
        if dt.tzinfo is None:
            if dt.replace(tzinfo=tz,fold=0).utcoffset()!=dt.replace(tzinfo=tz,fold=1).utcoffset():raise ValueError('Ambiguous or nonexistent local time; provide an explicit UTC offset')
            dt=dt.replace(tzinfo=tz)
        return dt.astimezone(timezone.utc).isoformat()
    except ZoneInfoNotFoundError:raise ValueError('Use a valid IANA timezone, for example Asia/Kolkata')
def save_calendar(req,item_id=None):
    utc=schedule_time(req.scheduled_at,req.timezone)
    with db() as c:
        copy=get(c,'copies',req.copy_id)
        if item_id:get(c,'calendar',item_id)
        if req.status in {'approved','scheduled_in_app','manually_published'} and not copy['approved']:raise HTTPException(409,'Review and approve this copy before scheduling')
        caption=req.caption or copy['content']
        if req.status in {'approved','scheduled_in_app','manually_published'} and caption!=copy['content']:raise HTTPException(409,'Save caption edits in Remix Lab and approve the updated copy first')
        if req.status=='scheduled_in_app' and datetime.fromisoformat(utc)<=datetime.now(timezone.utc):raise HTTPException(400,'Choose a future time')
        conflict=c.execute("SELECT calendar.id FROM calendar JOIN copies ON copies.id=calendar.copy_id WHERE utc_at=? AND platform=? AND calendar.status NOT IN ('cancelled','draft') AND calendar.id!=?",(utc,copy['platform'],item_id or '')).fetchone()
        if conflict and req.status not in {'cancelled','draft'}:raise HTTPException(409,'This platform already has a post in that time slot')
        if item_id:c.execute('UPDATE calendar SET copy_id=?,scheduled_at=?,timezone=?,status=?,caption=?,utc_at=? WHERE id=?',(req.copy_id,req.scheduled_at,req.timezone,req.status,caption,utc,item_id))
        else:
            item_id=uid();c.execute('INSERT INTO calendar(id,copy_id,scheduled_at,timezone,status,caption,utc_at) VALUES (?,?,?,?,?,?,?)',(item_id,req.copy_id,req.scheduled_at,req.timezone,req.status,caption,utc))
    audit(None,'Calendar + Feedback','save_calendar_entry',{'status':req.status,'id':item_id})
    return {'id':item_id,'status':req.status,'note':'In-app scheduling does not publish externally'}
@app.post('/api/calendar')
def schedule(req:CalendarRequest):return save_calendar(req)
@app.patch('/api/calendar/{item_id}')
def reschedule(item_id:str,req:CalendarRequest):return save_calendar(req,item_id)
@app.delete('/api/calendar/{item_id}')
def cancel_schedule(item_id:str):
    with db() as c:get(c,'calendar',item_id);c.execute("UPDATE calendar SET status='cancelled' WHERE id=?",(item_id,))
    return {'cancelled':True}
@app.get('/api/calendar')
def get_calendar():
    with db() as c:return rows(c.execute('SELECT calendar.*,copies.platform,copies.angle,copies.content FROM calendar JOIN copies ON copies.id=calendar.copy_id ORDER BY utc_at'))

@app.get('/api/insights')
def insights():return performance_summary()
@app.post('/api/analytics/import')
def import_metrics(csv_file:UploadFile=File(...),source:Literal['actual','synthetic']=Form(default='actual')):
    raw=csv_file.file.read(2_000_001)
    if len(raw)>2_000_000:raise HTTPException(413,'CSV exceeds 2 MB')
    try:reader=list(csv.DictReader(io.StringIO(raw.decode('utf-8-sig'))))
    except (UnicodeError,csv.Error):raise HTTPException(400,'Use valid UTF-8 CSV')
    required={'clip_id','platform','angle','impressions','views','likes','comments','shares','saves'}
    if not reader or len(reader)>2000 or not required.issubset(reader[0]):raise HTTPException(400,'Provide up to 2000 rows with columns: '+', '.join(sorted(required)))
    if any(r.get('source')=='synthetic' for r in reader):source='synthetic'
    validated=[]
    with db() as c:valid_ids={r[0] for r in c.execute('SELECT id FROM clips')}
    for n,r in enumerate(reader,2):
        try:
            if r['clip_id'] not in valid_ids or r['platform'] not in PLATFORMS or r['angle'] not in ANGLES:raise ValueError()
            numbers=[int(r[k]) for k in ['impressions','views','likes','comments','shares','saves']]
            if any(v<0 or v>10**12 for v in numbers):raise ValueError()
            period=r.get('period') or 'lifetime'
            if period not in {'lifetime','first_7_days','first_30_days'}:raise ValueError()
            published=r.get('published_at') or None
            if published:datetime.fromisoformat(published.replace('Z','+00:00'))
            watch=float(r['watch_time']) if r.get('watch_time') else None
            if watch is not None and (not 0<=watch<=1e12):raise ValueError()
            # One immutable measurement per clip/platform/angle/period/source. Reimports cannot inflate sample size.
            fp=hashlib.sha256(json.dumps([r['clip_id'],r['platform'],r['angle'],period,source]).encode()).hexdigest()
            validated.append((r['clip_id'],r['platform'],r['angle'],*numbers,source,period,published,fp,watch))
        except (ValueError,TypeError):raise HTTPException(400,f'Invalid CSV row {n}; check clip ID, platform, angle, period and nonnegative counts')
    with db() as c:
        before=c.total_changes
        c.executemany('INSERT OR IGNORE INTO metrics(clip_id,platform,angle,impressions,views,likes,comments,shares,saves,source,period,published_at,fingerprint,watch_time) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)',validated)
        imported=c.total_changes-before
        if imported:bump(c,'performance')
    audit(None,'Calendar + Feedback','import_metrics',{'status':'performance_updated','imported':imported,'source':source})
    return {'imported':imported,'duplicates':len(validated)-imported,'insights':performance_summary()}
@app.get('/api/analytics/template')
def analytics_template():
    return Response('clip_id,platform,angle,published_at,impressions,views,likes,comments,shares,saves,period,watch_time\n',media_type='text/csv',headers={'Content-Disposition':'attachment; filename="metrics-template.csv"'})
@app.get('/api/analytics/sample')
def synthetic_sample():
    with db() as c:clips=rows(c.execute('SELECT id FROM clips ORDER BY rowid DESC LIMIT 3'))
    if len(clips)<3:raise HTTPException(409,'Discover three clips before downloading a sample')
    buffer=io.StringIO();writer=csv.writer(buffer)
    writer.writerow(['clip_id','platform','angle','impressions','views','likes','comments','shares','saves','period','source'])
    for clip in clips:
        for angle,likes in [('Teach It',75),('Tell It',25),('Challenge It',10)]:writer.writerow([clip['id'],'instagram',angle,1000,700,likes,4,3,2,'lifetime','synthetic'])
    return Response(buffer.getvalue(),media_type='text/csv',headers={'Content-Disposition':'attachment; filename="SYNTHETIC-demo-metrics.csv"'})
@app.get('/api/jobs')
def jobs():
    with db() as c:return rows(c.execute('SELECT id,kind,target_id,status,attempts,error,created_at,updated_at FROM jobs ORDER BY rowid DESC LIMIT 100'))
@app.post('/api/jobs/{job_id}/retry')
def retry_job(job_id:str):
    with db() as c:
        job=get(c,'jobs',job_id)
        if job['status']!='failed':raise HTTPException(409,'Only failed jobs can be retried')
        if job['attempts']>=3:raise HTTPException(409,'Retry limit reached; repair the input or configuration')
        c.execute("UPDATE jobs SET status='queued',error=NULL WHERE id=?",(job_id,))
    return {'status':'queued'}
@app.get('/api/events')
def events():
    with db() as c:return rows(c.execute('SELECT * FROM agent_events ORDER BY id DESC LIMIT 60'))
@app.get('/api/export')
def export_data():
    with db() as c:
        data={table:rows(c.execute(f'SELECT * FROM {table}')) for table in ['assets','segments','clips','copies','edits','brand_rules','calendar','metrics','revisions','profile','preset_runs','preset_candidates','clip_edits']}
    for a in data['assets']:a.pop('media_path',None)
    for clip in data['clips']:clip.pop('output_path',None)
    for candidate in data['preset_candidates']:candidate.pop('output_path',None)
    return Response(json.dumps(data,indent=2),media_type='application/json',headers={'Content-Disposition':'attachment; filename="remixora-studio.json"'})

from .workflow import router as workflow_router
app.include_router(workflow_router)

from .presets import router as preset_router
app.include_router(preset_router)

from .projects import router as projects_router
app.include_router(projects_router)
