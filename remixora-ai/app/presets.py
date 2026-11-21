"""Evidence-driven preset analysis and review, backed by the durable media queue."""
import json, re, uuid, os, shutil
from pathlib import Path
from typing import Literal
from fastapi import APIRouter,HTTPException
from pydantic import BaseModel,Field,model_validator
from .db import db,rows,DATA_DIR
from .jobs import enqueue
from .preset_signals import cached_signals,silence_edl,render_edl

class PresetDefinition(BaseModel):
    id:str
    name:str
    category:str
    description:str
    signals:list[str]
    weights:dict[str,float]
    threshold:float=.48
    video_only:bool=False
    cost:str='Light'

def definition(id,name,category,description,signals,weights,**kwargs):
    return PresetDefinition(id=id,name=name,category=category,description=description,signals=signals,weights=weights,**kwargs)

PRESETS=[
 definition('funny_moments','Funny Moments','Entertainment / Gaming','Jokes and punchlines with a clear setup.',['transcript','audio'],{'humor':.6,'punchline':.25,'energy':.15}),
 definition('reactions','Reactions','Entertainment / Gaming','Spoken surprise supported by changes in delivery.',['transcript','audio'],{'reaction':.65,'energy':.35}),
 definition('fail_moments','Fail Moments','Entertainment / Gaming','Mistakes with an explicit outcome.',['transcript','audio'],{'failure':.5,'outcome':.35,'energy':.15},threshold=.55),
 definition('clutch_moments','Clutch Moments','Entertainment / Gaming','Tension followed by a confirmed turnaround.',['transcript','audio'],{'tension':.35,'victory':.45,'context':.2},threshold=.55),
 definition('funny_clips','Funny Clips','Entertainment / Gaming','Conversational setups, banter and witty replies.',['transcript'],{'banter':.45,'humor':.25,'punchline':.3}),
 definition('best_highlights','Best Highlights','Creator / Podcast / Learning','A varied selection from across the recording.',['transcript'],{'clarity':.25,'lesson':.25,'story':.15,'hook':.15,'emotion':.2},threshold=.35),
 definition('best_talking_moments','Best Talking Moments','Creator / Podcast / Learning','Complete stories, opinions and thoughtful exchanges.',['transcript','audio'],{'continuity':.4,'story':.35,'clarity':.25},threshold=.42),
 definition('motivation','Motivation','Creator / Podcast / Learning','Encouragement, perseverance and practical resolve.',['transcript'],{'motivation':.7,'story':.15,'clarity':.15}),
 definition('key_takeaways','Key Takeaways','Creator / Podcast / Learning','Lessons, definitions and actionable explanations.',['transcript'],{'lesson':.7,'clarity':.2,'context':.1}),
 definition('shorts_reels','Shorts / Reels','Creator / Podcast / Learning','A focused opening with a self-contained payoff.',['transcript'],{'hook':.4,'clarity':.25,'lesson':.2,'context':.15},threshold=.4),
 definition('cinematic','Cinematic','Visual / Utility','Scenes ranked by sampled image quality and motion.',['visual'],{'exposure':.4,'sharpness':.35,'controlled_motion':.25},video_only=True,cost='Frame scan'),
 definition('remove_silence','Remove Silence','Visual / Utility','Trim extended quiet gaps from the full recording.',['silence'],{},cost='Timeline scan'),
]
REGISTRY={p.id:p for p in PRESETS}

class PresetConfig(BaseModel):
    preset_id:str
    min_seconds:float=Field(default=15,ge=8,le=90,allow_inf_nan=False)
    max_seconds:float=Field(default=45,ge=8,le=90,allow_inf_nan=False)
    count:int=Field(default=3,ge=1,le=20)
    intensity:Literal['balanced','only_best','find_more']='balanced'
    context_before:float=Field(default=1,ge=0,le=5)
    context_after:float=Field(default=1,ge=0,le=5)
    aspect_ratio:Literal['9:16','1:1','16:9']='9:16'
    burn_subtitles:bool=True
    language:str=Field(default='en',max_length=20)
    platform:Literal['youtube','instagram','linkedin']='youtube'
    silence_db:float=Field(default=-38,ge=-60,le=-15)
    silence_min:float=Field(default=.8,ge=.3,le=5)
    silence_padding:float=Field(default=.2,ge=0,le=1)
    use_ai:bool=True
    @model_validator(mode='after')
    def valid(self):
        if self.preset_id not in REGISTRY:raise ValueError('Unknown preset')
        if self.min_seconds>self.max_seconds:raise ValueError('Minimum duration must not exceed maximum duration')
        return self

def migrate(c):
    c.executescript('''
    CREATE TABLE IF NOT EXISTS preset_runs(id TEXT PRIMARY KEY,asset_id TEXT REFERENCES assets(id),preset_id TEXT,config_json TEXT,status TEXT DEFAULT 'queued',progress INTEGER DEFAULT 0,capability_report_json TEXT DEFAULT '{}',error TEXT,started_at TEXT DEFAULT CURRENT_TIMESTAMP,completed_at TEXT);
    CREATE TABLE IF NOT EXISTS preset_candidates(id TEXT PRIMARY KEY,run_id TEXT REFERENCES preset_runs(id),clip_id TEXT REFERENCES clips(id),score REAL,confidence TEXT,score_breakdown_json TEXT,evidence_json TEXT,reason TEXT,status TEXT DEFAULT 'proposed',edl_json TEXT DEFAULT '[]',render_status TEXT DEFAULT 'not_rendered',output_path TEXT,error TEXT);
    CREATE INDEX IF NOT EXISTS ix_preset_candidates_run ON preset_candidates(run_id);
    CREATE TABLE IF NOT EXISTS media_analysis_cache(asset_id TEXT REFERENCES assets(id),kind TEXT,fingerprint TEXT,data TEXT,created_at TEXT,PRIMARY KEY(asset_id,kind));
    CREATE TABLE IF NOT EXISTS clip_edits(id TEXT PRIMARY KEY,clip_id TEXT REFERENCES clips(id),revised_clip_id TEXT REFERENCES clips(id),original_start REAL,original_end REAL,revised_start REAL,revised_end REAL,created_at TEXT DEFAULT CURRENT_TIMESTAMP);
    PRAGMA user_version=4;
    ''')

router=APIRouter(prefix='/api')

@router.get('/presets')
def library():return [p.model_dump() for p in PRESETS]

@router.post('/assets/{asset_id}/presets/analyze',status_code=202)
def analyze(asset_id:str,config:PresetConfig):
    with db() as c:
        c.execute('BEGIN IMMEDIATE')
        asset=c.execute('SELECT * FROM assets WHERE id=?',(asset_id,)).fetchone()
        if not asset:raise HTTPException(404,'Source not found')
        active=c.execute("SELECT id FROM preset_runs WHERE asset_id=? AND config_json=? AND status IN ('queued','analyzing')",(asset_id,config.model_dump_json())).fetchone()
        if active:return {'id':active['id'],'existing':True}
        rid=uuid.uuid4().hex
        c.execute('INSERT INTO preset_runs(id,asset_id,preset_id,config_json) VALUES (?,?,?,?)',(rid,asset_id,config.preset_id,config.model_dump_json()))
        jid=enqueue('preset_analyze',rid,connection=c)
    return {'id':rid,'job_id':jid}

@router.get('/preset-runs')
def runs():
    with db() as c:return rows(c.execute('SELECT r.*,a.filename FROM preset_runs r JOIN assets a ON a.id=r.asset_id ORDER BY r.rowid DESC LIMIT 50'))

@router.get('/preset-runs/{rid}')
def run_detail(rid:str):
    with db() as c:r=c.execute('SELECT * FROM preset_runs WHERE id=?',(rid,)).fetchone()
    if not r:raise HTTPException(404,'Analysis not found')
    return dict(r)

@router.get('/preset-runs/{rid}/candidates')
def results(rid:str):
    run_detail(rid)
    with db() as c:return rows(c.execute('SELECT pc.*,cl.start,cl.end,cl.title,cl.quote,cl.source,cl.asset_id FROM preset_candidates pc JOIN clips cl ON cl.id=pc.clip_id WHERE run_id=? ORDER BY pc.score DESC',(rid,)))

class Selection(BaseModel):
    candidate_ids:list[str]=Field(min_length=1,max_length=20)

class CandidateReview(BaseModel):
    status:Literal['proposed','approved','rejected']

@router.patch('/preset-candidates/{candidate_id}')
def review_candidate(candidate_id:str,review:CandidateReview):
    with db() as c:
        c.execute('BEGIN IMMEDIATE')
        if not c.execute('SELECT 1 FROM preset_candidates WHERE id=?',(candidate_id,)).fetchone():raise HTTPException(404,'Candidate not found')
        if c.execute("SELECT 1 FROM jobs WHERE target_id=? AND status IN ('queued','running')",(candidate_id,)).fetchone():raise HTTPException(409,'Wait for the active render to finish.')
        c.execute('UPDATE preset_candidates SET status=? WHERE id=?',(review.status,candidate_id))
    return {'id':candidate_id,'status':review.status}

@router.post('/preset-runs/{rid}/render-selected',status_code=202)
def render_selected(rid:str,selection:Selection):
    run=run_detail(rid)
    if run['status']!='ready':raise HTTPException(409,'Wait for a completed analysis')
    jobs=[]
    with db() as c:
        c.execute('BEGIN IMMEDIATE')
        items=[c.execute('SELECT * FROM preset_candidates WHERE run_id=? AND id=?',(rid,i)).fetchone() for i in set(selection.candidate_ids)]
        if not all(items):raise HTTPException(404,'One or more selections do not belong to this analysis')
        if any(item['status']=='rejected' for item in items):raise HTTPException(409,'Restore rejected candidates before rendering.')
        for item in items:
            c.execute("UPDATE preset_candidates SET status='approved' WHERE id=?",(item['id'],))
            if item['render_status']!='rendered':
                jobs.append(enqueue('preset_render',item['id'],connection=c))
                if item['render_status']!='rendering':c.execute("UPDATE preset_candidates SET render_status='queued',error=NULL WHERE id=?",(item['id'],))
    return {'job_ids':jobs,'selected':len(items)}

class Bounds(BaseModel):
    start:float=Field(ge=0,allow_inf_nan=False)
    end:float=Field(gt=0,allow_inf_nan=False)

@router.patch('/clips/{clip_id}/bounds')
def edit_bounds(clip_id:str,b:Bounds):
    from . import main
    with db() as c:
        c.execute('BEGIN IMMEDIATE')
        old=main.get(c,'clips',clip_id);asset=main.get(c,'assets',old['asset_id'])
        candidate=c.execute('SELECT * FROM preset_candidates WHERE clip_id=?',(clip_id,)).fetchone()
        if not candidate:raise HTTPException(409,'Edit boundaries in a Smart Cuts analysis.')
        if json.loads(candidate['edl_json']):raise HTTPException(409,'Adjust silence settings and analyze again to change this timeline.')
        if c.execute("SELECT 1 FROM jobs WHERE target_id=? AND status IN ('queued','running')",(candidate['id'],)).fetchone():raise HTTPException(409,'Wait for the active render before editing.')
        if not b.start<b.end<=asset['duration'] or not 8<=b.end-b.start<=90:raise HTTPException(400,'Choose an 8–90 second range inside the source.')
        segments=rows(c.execute('SELECT * FROM segments WHERE asset_id=? AND start>=? AND end<=? ORDER BY start',(asset['id'],b.start,b.end)))
        revised={**old,'id':uuid.uuid4().hex,'start':b.start,'end':b.end,'quote':' '.join(s['text'] for s in segments),'evidence':json.dumps([s['id'] for s in segments]),'render_status':'not_rendered','output_path':None,'source':'manual'}
        keys=list(revised);c.execute(f'INSERT INTO clips({",".join(keys)}) VALUES ({",".join("?" for _ in keys)})',list(revised.values()))
        c.execute('INSERT INTO clip_edits(id,clip_id,revised_clip_id,original_start,original_end,revised_start,revised_end) VALUES (?,?,?,?,?,?,?)',(uuid.uuid4().hex,clip_id,revised['id'],old['start'],old['end'],b.start,b.end))
        c.execute("UPDATE preset_candidates SET clip_id=?,render_status='not_rendered',output_path=NULL,status='proposed',evidence_json=?,reason=? WHERE id=?",(revised['id'],json.dumps({'segments':[s['id'] for s in segments],'limitations':['Manual boundaries; review the source context.']}),'Boundaries edited by creator; previous clip retained in history.',candidate['id']))
    return {'clip_id':revised['id'],'start':b.start,'end':b.end}

@router.get('/render-jobs/{jid}')
def render_job(jid:str):
    with db() as c:
        job=c.execute('SELECT * FROM jobs WHERE id=?',(jid,)).fetchone()
        if not job:raise HTTPException(404,'Render job not found')
        item=c.execute('SELECT clip_id,render_status FROM preset_candidates WHERE id=?',(job['target_id'],)).fetchone()
    return {**dict(job),'download_url':f'/api/clips/{item["clip_id"]}/download' if item and item['render_status']=='rendered' else None}

PATTERNS={
 'humor':r'\b(joke|joking|hilarious|funny|ridiculous|laugh|laughter|punchline|absurd)\b',
 'punchline':r'\b(turns out|plot twist|just kidding|punchline|laugh|laughter|instead of|apparently)\b',
 'banter':r'\b(you said|he said|she said|i said|replied|asked me|told me|banter)\b',
 'reaction':r'\b(wow|oh no|oh my|unbelievable|what just happened|no way|surprised|shocked)\b',
 'failure':r'\b(failed|missed|crashed|mistake|lost|broke|dropped|defeat)\b',
 'outcome':r'\b(game over|we lost|i lost|did not work|didn.t work|crashed|broke|defeat|missed the|fell down|ended up)\b',
 'tension':r'\b(almost|last second|about to lose|behind|near defeat|one chance|running out)\b',
 'victory':r'\b(we won|i won|victory|saved it|made it|comeback|turned it around|won the)\b',
 'motivation':r'\b(keep going|don.t give up|believe|persevere|courage|you can|never give up|keep trying|resilience)\b',
 'lesson':r'\b(step|lesson|takeaway|means|because|how to|tip|first|second|remember|define|definition|in summary)\b',
 'story':r'\b(when i|one day|we were|i think|my experience|i learned|i believe|then i|in my opinion)\b',
}

def features(text,segments,audio,start,end):
    lower=text.lower();f={name:min(1,len(re.findall(pattern,lower))/.95) for name,pattern in PATTERNS.items()}
    f['clarity']=min(1,len(text.split())/35)*(.9 if text.rstrip().endswith(('.','!','?')) else .55)
    f['hook']=min(1,.2+bool('?' in text[:100])*.45+bool(re.search(r'\b(how|why|secret|mistake|imagine|what if)\b',lower[:100]))*.45)
    f['emotion']=max(f[k] for k in ['reaction','tension','victory','motivation','humor'])
    f['context']=min(1,len(segments)/2)
    coverage=sum(max(0,min(end,s['end'])-max(start,s['start'])) for s in segments)/(end-start)
    values=[s['db'] for s in audio if s['start']<end and s['end']>start]
    f['energy']=min(1,(max(values)-min(values))/25) if values else 0
    f['continuity']=min(1,coverage)*(sum(v>-42 for v in values)/len(values) if values else 1)
    return f

def qualifies(p,f,text):
    if p=='funny_moments':return f['humor']>0 and f['punchline']>0
    if p=='funny_clips':return f['banter']>0 and f['humor']>0
    if p=='reactions':return f['reaction']>0 and f['energy']>.15
    if p=='fail_moments':return f['failure']>0 and f['outcome']>0
    if p=='clutch_moments':
        a=re.search(PATTERNS['tension'],text.lower());b=re.search(PATTERNS['victory'],text.lower())
        return bool(a and b and a.start()<b.start())
    if p=='motivation':return f['motivation']>0
    if p=='key_takeaways':return f['lesson']>0
    if p=='best_talking_moments':return f['continuity']>.55 and (f['story']>0 or f['clarity']>.7)
    return True

def transcript_windows(segments,duration,config,audio):
    output=[];preset=REGISTRY[config.preset_id];target=(config.min_seconds+config.max_seconds)/2
    for i,segment in enumerate(segments):
        options=[]
        for j in range(i,len(segments)):
            length=segments[j]['end']-segment['start']
            if length>config.max_seconds:break
            if length>=config.min_seconds:options.append(j)
        if not options:continue
        j=min(options,key=lambda k:abs(segments[k]['end']-segment['start']-target))
        group=segments[i:j+1];text=' '.join(x['text'] for x in group);start=segment['start'];end=group[-1]['end']
        f=features(text,group,audio,start,end)
        if not qualifies(config.preset_id,f,text):continue
        remaining=max(0,config.max_seconds-(end-start));before=min(config.context_before,remaining/2,start);after=min(config.context_after,remaining-before,duration-end)
        score=sum(f.get(k,0)*weight for k,weight in preset.weights.items())
        signals=[k for k in preset.weights if f.get(k,0)>.3]
        output.append({'start':start-before,'end':end+after,'quote':text,'segments':[x['id'] for x in group],'score':score,'breakdown':{k:round(f.get(k,0),3) for k in preset.weights},'signals':signals,'reason':'Transcript cues: '+', '.join(signals)+'.','source':'local_signals','limitations':['Local language cues are estimates, not emotion recognition.','No visual outcome or facial expression is inferred.']})
    return output

class SemanticPick(BaseModel):
    index:int=Field(ge=0)
    relevance:float=Field(ge=0,le=1)
class SemanticRanking(BaseModel):
    picks:list[SemanticPick]=Field(max_length=30)

def clip_title(quote,fallback):
    sentences=re.split(r'(?<=[.!?])\s+',quote.strip())
    meaningful=next((s for s in sentences if len(s.split())>=6),quote.strip())
    title=meaningful.rstrip('.!?')
    if len(title)>90:title=title[:91].rsplit(' ',1)[0]+'…'
    return title or fallback

def diversify(items,count,duration,balanced=False):
    result=[];remaining=sorted(items,key=lambda x:x['score'],reverse=True)
    if balanced:
        for third in range(3):
            local=[x for x in remaining if int(min(2,x['start']/max(duration,1)*3))==third and all(min(x['end'],r['end'])<=max(x['start'],r['start']) for r in result)]
            contained=[x for x in local if x['end']<=(third+1)*duration/3]
            found=next(iter(contained or local),None)
            if found and len(result)<count and all(min(found['end'],x['end'])<=max(found['start'],x['start']) for x in result):result.append(found)
    for item in remaining:
        if len(result)>=count:break
        if all(min(item['end'],x['end'])<=max(item['start'],x['start']) for x in result):result.append(item)
    return result

def process_analysis(job):
    from . import main
    from .ai import generate_json
    rid=job['target_id'];run=run_detail(rid);config=PresetConfig.model_validate_json(run['config_json']);preset=REGISTRY[config.preset_id]
    if run['status'] in {'ready','no_matches','unsupported'}:return
    with db() as c:
        c.execute("UPDATE preset_runs SET status='analyzing',progress=10,error=NULL WHERE id=?",(rid,))
        asset=main.get(c,'assets',run['asset_id']);segments=rows(c.execute('SELECT * FROM segments WHERE asset_id=? ORDER BY start',(asset['id'],)))
    reason=None
    if preset.video_only and asset['media_kind']!='video':reason='Cinematic requires video frames. Choose a speech or utility preset for this audio source.'
    if 'transcript' in preset.signals and not segments:reason='Import matching SRT/VTT or finish transcription before using this preset.'
    if config.language!='en' and config.preset_id not in {'best_highlights','shorts_reels','cinematic','remove_silence'}:reason='This preset currently requires English transcript cues. Choose Best Highlights, Shorts / Reels or a visual / utility preset for this source language.'
    if reason:
        with db() as c:c.execute("UPDATE preset_runs SET status='unsupported',progress=100,capability_report_json=?,completed_at=CURRENT_TIMESTAMP WHERE id=?",(json.dumps({'message':reason}),rid))
        return
    report={'message':'Analysis complete','signals':preset.signals,'ai_ranking':'not_requested'};items=[]
    if config.preset_id=='remove_silence':
        edl,gaps=silence_edl(asset['media_path'],asset['duration'],config.silence_db,config.silence_min,config.silence_padding)
        saved=sum(b-a for a,b in gaps);report.update(edl=edl,removed_seconds=round(saved,2),retained_seconds=round(sum(x['end']-x['start'] for x in edl),2),message='Review retained ranges before rendering. Quiet music may also be removed.')
        if edl and saved>.1 and sum(x['end']-x['start'] for x in edl)>.5:items=[{'start':0,'end':asset['duration'],'quote':'','segments':[],'score':1,'breakdown':{'removed_seconds':saved},'signals':['ffmpeg_silencedetect'],'reason':f'{saved:.1f} seconds of quiet gaps removed; {len(edl)} retained ranges.','source':'local_signals','limitations':['Silence detection cannot distinguish quiet music from pauses.'],'edl':edl}]
    elif config.preset_id=='cinematic':
        frames=cached_signals(asset,'visual');report['sample_interval_seconds']=5
        for f in frames:
            start=f['start'];end=min(asset['duration'],start+(config.min_seconds+config.max_seconds)/2)
            if end-start<config.min_seconds:continue
            group=[x for x in frames if start<=x['start']<end]
            breakdown={'exposure':sum(max(0,1-abs(x['brightness']-.5)*2) for x in group)/len(group),'sharpness':min(1,sum(x['sharpness'] for x in group)/len(group)*8),'controlled_motion':sum(max(0,1-x['change']*3) for x in group)/len(group)}
            if breakdown['exposure']<.2 or breakdown['sharpness']<.12:continue
            score=sum(breakdown[k]*v for k,v in preset.weights.items())
            items.append({'start':start,'end':end,'quote':'','segments':[],'score':score,'breakdown':breakdown,'signals':['sampled_video_frames'],'reason':'Balanced exposure, image detail and controlled frame changes in sampled frames.','source':'local_signals','limitations':['Five-second sampling can miss fast cuts. No subject tracking or aesthetic judgment.']})
    else:
        audio=cached_signals(asset,'audio') if 'audio' in preset.signals else []
        items=transcript_windows(segments,asset['duration'],config,audio)
        if config.use_ai and items:
            report['ai_ranking']='unavailable'
            # Only eligible windows are sent. Models cannot invent timings or bypass evidence gates.
            shortlist=diversify(items,30,asset['duration'],True)
            with db() as c:rules=[r['text'] for r in c.execute("SELECT text FROM brand_rules WHERE status='approved' LIMIT 20")]
            payload=json.dumps({'source_language':config.language,'approved_brand_rules':rules,'windows':[{'index':i,'evidence':x['quote'][:400],'signals':x['signals']} for i,x in enumerate(shortlist)]})
            response,provider=generate_json('Rank these source windows for '+preset.name+': '+preset.description+'. Return JSON {"picks":[{"index":0,"relevance":0.8}]}. Use only supplied indices. Score relevance to this specific preset; no invented events.',payload)
            try:
                ranking=SemanticRanking.model_validate(response) if response else None
                seen=set()
                for pick in ranking.picks if ranking else []:
                    if pick.index>=len(shortlist) or pick.index in seen:continue
                    seen.add(pick.index);x=shortlist[pick.index];x['score']=.65*x['score']+.35*pick.relevance;x['breakdown']['semantic_relevance']=pick.relevance;x['source']=provider
                if seen:
                    # Once a valid model selection exists, unreviewed keyword scores
                    # must not outrank its choices. All selected windows passed gates.
                    items=[shortlist[index] for index in sorted(seen)]
                    report['ai_ranking']='used'
            except ValueError:pass
            if report['ai_ranking']=='unavailable':
                for item in items:item['limitations'].append('AI ranking was unavailable or returned no valid selections; these results use local evidence scoring.')
        # Actual comparable preset metrics only; old historical results stay untouched.
        with db() as c:groups=rows(c.execute('SELECT pc.id, SUM(m.likes+m.comments+m.shares+m.saves) engagement,SUM(m.impressions) impressions FROM preset_candidates pc JOIN preset_runs pr ON pr.id=pc.run_id JOIN metrics m ON m.clip_id=pc.clip_id WHERE pr.preset_id=? AND m.platform=? AND m.period=\'lifetime\' AND m.source=\'actual\' AND m.impressions>0 GROUP BY pc.clip_id',(config.preset_id,config.platform)))
        if len(groups)>=3:
            rate=(sum(g['engagement'] for g in groups)+9)/(sum(g['impressions'] for g in groups)+300);adjustment=min(.04,max(-.04,(rate-.03)*.5))
            for item in items:item['score']=max(0,min(1,item['score']+adjustment));item['breakdown']['feedback_adjustment']=adjustment;item['reason']+=f' {len(groups)} comparable published clips; smoothed engagement {rate:.1%}, adjustment {adjustment:+.3f}.'
    threshold=preset.threshold+{'only_best':.17,'balanced':0,'find_more':-.12}[config.intensity]
    items=[x for x in items if x['score']>=threshold]
    selected=diversify(items,config.count,asset['duration'],config.preset_id=='best_highlights')
    with db() as c:
        c.execute('BEGIN IMMEDIATE')
        # A restarted analysis replaces no historical recommendations; writes commit once.
        if c.execute('SELECT 1 FROM preset_candidates WHERE run_id=?',(rid,)).fetchone():return
        for i,item in enumerate(selected):
            cid=uuid.uuid4().hex;pcid=uuid.uuid4().hex;title=clip_title(item['quote'],preset.name+f' {i+1}')
            c.execute('INSERT INTO clips(id,asset_id,start,end,title,reason,quote,score,source,suggested_angle,evidence,base_score,preset_id) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)',(cid,asset['id'],item['start'],item['end'],title,item['reason'],item['quote'],round(item['score']*5,2),item['source'],'Teach It' if config.preset_id=='key_takeaways' else 'Tell It',json.dumps(item['segments']),item['score']*5,config.preset_id))
            evidence={'segments':item['segments'],'signals':item['signals'],'limitations':item['limitations'],'source_mode':item['source']}
            c.execute('INSERT INTO preset_candidates(id,run_id,clip_id,score,confidence,score_breakdown_json,evidence_json,reason,edl_json) VALUES (?,?,?,?,?,?,?,?,?)',(pcid,rid,cid,round(item['score'],3),'high' if item['score']>.78 else 'moderate',json.dumps(item['breakdown']),json.dumps(evidence),item['reason'],json.dumps(item.get('edl',[]))))
            c.execute(
                """INSERT OR REPLACE INTO clip_candidates (id, project_id, preset_run_id, clip_id, start_time, end_time, title, score, selection_reason, source_evidence, status, edl_json)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'proposed', ?)""",
                (pcid, asset['id'], rid, cid, item['start'], item['end'], title, round(item['score'], 3), item['reason'], json.dumps(evidence), json.dumps(item.get('edl', [])))
            )
        if not selected:report['message']='No qualifying moments for these settings. Try a different preset or lower the intensity; no clips were manufactured.'
        c.execute('UPDATE preset_runs SET status=?,progress=100,capability_report_json=?,completed_at=CURRENT_TIMESTAMP WHERE id=?',('ready' if selected else 'no_matches',json.dumps(report),rid))
    main.audit(asset['id'],'Preset Scout','analyze_preset',{'preset':config.preset_id,'run_id':rid,'candidates':len(selected)})

def process_render(job):
    from . import main
    from .media import render_variant
    with db() as c:
        item=dict(c.execute('SELECT * FROM preset_candidates WHERE id=?',(job['target_id'],)).fetchone());clip=main.get(c,'clips',item['clip_id']);asset=main.get(c,'assets',clip['asset_id']);run=dict(c.execute('SELECT * FROM preset_runs WHERE id=?',(item['run_id'],)).fetchone());segments=rows(c.execute('SELECT * FROM segments WHERE asset_id=? ORDER BY start',(asset['id'],)))
        if item['render_status']=='rendered' and item['output_path'] and Path(item['output_path']).is_file():return
        c.execute("UPDATE preset_candidates SET render_status='rendering',error=NULL WHERE id=?",(item['id'],))
    min_render_free = min(int(os.getenv('MIN_FREE_MB', '30')) * 1024**2, 30 * 1024**2)
    if main.directory_size(DATA_DIR)>int(os.getenv('STORAGE_QUOTA_MB','5000'))*1024**2 or shutil.disk_usage(DATA_DIR).free<min_render_free:raise ValueError('Free disk space before rendering.')
    config=PresetConfig.model_validate_json(run['config_json']);edl=json.loads(item['edl_json']);audio_edl=edl and asset['media_kind']=='audio';dest=main.EXPORTS/(clip['id']+('.m4a' if audio_edl else '.mp4'))
    if edl:render_edl(asset['media_path'],dest,edl,asset['media_kind']=='video',config.aspect_ratio,segments,config.burn_subtitles and bool(segments))
    else:render_variant(asset['media_path'],dest,clip['start'],clip['end'],asset['media_kind']=='video','',REGISTRY[config.preset_id].name,segments,config.burn_subtitles and bool(segments),config.aspect_ratio)
    from .media import generate_thumbnail, probe_output
    dur = max(0, clip['end'] - clip['start'])
    thumb_path = None
    if dest.suffix.lower() == '.mp4':
        thumb_dest = main.EXPORTS / (clip['id'] + '.jpg')
        thumb_path = generate_thumbnail(dest, thumb_dest, timestamp=min(0.5, dur / 2))
    with db() as c:
        c.execute("UPDATE preset_candidates SET render_status='rendered',output_path=? WHERE id=?",(str(dest),item['id']))
        c.execute("UPDATE clips SET render_status='rendered',output_path=? WHERE id=?",(str(dest),clip['id']))
        c.execute(
            """INSERT OR REPLACE INTO rendered_clips (id, project_id, candidate_id, preset_run_id, clip_id, title, file_path, thumbnail_path, duration, aspect_ratio, status)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'rendered')""",
            (clip['id'], asset['id'], item['id'], item['run_id'], clip['id'], clip['title'], str(dest), thumb_path, dur, config.aspect_ratio),
        )
