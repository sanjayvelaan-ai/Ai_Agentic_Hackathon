import json,subprocess,time
from pathlib import Path
import pytest
from app.db import db
from app.presets import PRESETS,features,qualifies,diversify
from test_workflow import upload,wait_job

def analyze(client,asset,preset,**options):
    r=client.post(f'/api/assets/{asset}/presets/analyze',json={'preset_id':preset,'use_ai':False,**options})
    assert r.status_code==202,r.text
    wait_job(client,r.json()['job_id'])
    rid=r.json()['id'];return rid,client.get(f'/api/preset-runs/{rid}').json(),client.get(f'/api/preset-runs/{rid}/candidates').json()

@pytest.fixture
def mixed_subtitles():
    lines=['This is a funny joke. Here is the absurd setup.',
    'The punchline is hilarious. Just kidding, that made me laugh.',
    'Keep going. You can persevere, never give up. I learned courage.',
    'When I started, my experience taught me to keep trying.',
    'First step: learn the definition. This means choosing a useful tip.',
    'The second lesson explains how to do it, because this step matters.',
    'We were almost about to lose. One chance, running out of time.',
    'We won the game. At the last second we turned it around, victory.']
    def stamp(s):return f'00:{s//60:02}:{s%60:02},000'
    return '\n\n'.join(f'{i+1}\n{stamp(i*12)} --> {stamp((i+1)*12)}\n{text}' for i,text in enumerate(lines))

def test_registry_and_validation(client):
    defs=client.get('/api/presets').json()
    assert len(defs)==12 and len({x['id'] for x in defs})==12
    assert next(x for x in defs if x['id']=='cinematic')['video_only']
    assert client.post('/api/assets/missing/presets/analyze',json={'preset_id':'invented'}).status_code==422
    assert client.post('/api/assets/missing/presets/analyze',json={'preset_id':'key_takeaways','min_seconds':60,'max_seconds':15}).status_code==422

def test_distinct_presets_and_clutch_evidence(client,media_file,mixed_subtitles):
    aid=upload(client,media_file,mixed_subtitles)
    _,r,funny=analyze(client,aid,'funny_moments',count=1,min_seconds=15,max_seconds=25)
    _,_,lessons=analyze(client,aid,'key_takeaways',count=1,min_seconds=15,max_seconds=25)
    _,_,clutch=analyze(client,aid,'clutch_moments',count=1,min_seconds=15,max_seconds=25)
    assert funny and lessons and clutch
    assert funny[0]['start']<25 and lessons[0]['start']>40 and clutch[0]['start']>65
    assert funny[0]['run_id']!=lessons[0]['run_id']
    assert 'victory' in clutch[0]['quote'].lower()
    assert len(client.get('/api/clips').json())==3
    # The legacy discover cache must not return candidates from a preset run.
    legacy=client.post(f'/api/assets/{aid}/discover').json()['candidates']
    assert all(c.get('preset_id') is None for c in legacy)

def test_no_fabricated_outcomes_or_reactions(client,media_file,subtitles):
    aid=upload(client,media_file,subtitles)
    for preset in ['clutch_moments','fail_moments','reactions','funny_clips']:
        _,run,items=analyze(client,aid,preset)
        assert run['status']=='no_matches' and not items
    _,_,talk=analyze(client,aid,'best_talking_moments')
    assert talk

def test_highlights_diversity_and_config(client,media_file,mixed_subtitles):
    aid=upload(client,media_file,mixed_subtitles)
    _,_,items=analyze(client,aid,'best_highlights',count=3,min_seconds=15,max_seconds=25,context_before=0,context_after=0)
    assert len(items)==3
    ordered=sorted(items,key=lambda x:x['start'])
    assert all(a['end']<=b['start'] for a,b in zip(ordered,ordered[1:]))
    assert len({int(min(2,x['start']/96*3)) for x in items})==3
    _,_,one=analyze(client,aid,'best_highlights',count=1,min_seconds=30,max_seconds=50)
    assert len(one)==1 and one[0]['end']-one[0]['start']>=30

def test_cinematic_real_frames_and_audio_unsupported(client,media_file,subtitles,tmp_path):
    aid=upload(client,media_file,subtitles)
    _,run,items=analyze(client,aid,'cinematic',count=1)
    assert run['status']=='ready' and items
    assert 'sampled_video_frames' in items[0]['evidence_json']
    with db() as c:assert c.execute("SELECT 1 FROM media_analysis_cache WHERE asset_id=? AND kind='visual'",(aid,)).fetchone()
    audio=tmp_path/'audio.wav'
    subprocess.run(['ffmpeg','-v','error','-y','-i',str(media_file),'-vn',str(audio)],check=True,capture_output=True)
    r=client.post('/api/assets',files={'media':('audio.wav',audio.read_bytes(),'audio/wav')}).json();wait_job(client,r['job_id'])
    _,run,_=analyze(client,r['asset_id'],'cinematic')
    assert run['status']=='unsupported'

@pytest.mark.parametrize('aspect,expected',[('9:16',(720,1280)),('1:1',(720,720)),('16:9',(1280,720))])
def test_render_aspects_and_edits(client,media_file,mixed_subtitles,aspect,expected,tmp_path):
    aid=upload(client,media_file,mixed_subtitles)
    rid,_,items=analyze(client,aid,'key_takeaways',count=1,min_seconds=15,max_seconds=25,aspect_ratio=aspect)
    cid=items[0]['clip_id'];pcid=items[0]['id']
    edited=client.patch(f'/api/clips/{cid}/bounds',json={'start':48,'end':68})
    assert edited.status_code==200,edited.text
    new=edited.json()['clip_id'];assert new!=cid
    rendered=client.post(f'/api/preset-runs/{rid}/render-selected',json={'candidate_ids':[pcid]})
    assert rendered.status_code==202,rendered.text
    for jid in rendered.json()['job_ids']:
        wait_job(client,jid);assert client.get('/api/render-jobs/'+jid).json()['download_url']
    response=client.get(f'/api/clips/{new}/download');assert response.status_code==200
    output=tmp_path/'render.mp4';output.write_bytes(response.content)
    info=json.loads(subprocess.run(['ffprobe','-v','error','-show_entries','format=duration:stream=width,height','-of','json',str(output)],capture_output=True,text=True,check=True).stdout)
    stream=next(x for x in info['streams'] if 'width' in x)
    assert (stream['width'],stream['height'])==expected
    assert abs(float(info['format']['duration'])-20)<.2
    assert client.post(f'/api/preset-runs/{rid}/render-selected',json={'candidate_ids':[pcid]}).json()['job_ids']==[]
    assert client.patch(f'/api/clips/{new}/bounds',json={'start':80,'end':200}).status_code==400

@pytest.mark.parametrize('video',[False,True])
def test_remove_silence_real_concatenation(client,tmp_path,video):
    path=tmp_path/('silence.mp4' if video else 'silence.wav')
    args=['ffmpeg','-v','error','-y']
    if video:args+=['-f','lavfi','-i','testsrc2=size=320x180:rate=12']
    args+=['-f','lavfi','-i',r"aevalsrc=if(between(t\,3\,7)\,0\,0.3*sin(2*PI*440*t)):s=16000:d=10"]
    if video:args+=['-t','10','-c:v','libx264','-preset','ultrafast','-c:a','aac']
    subprocess.run(args+[str(path)],check=True,capture_output=True)
    r=client.post('/api/assets',files={'media':(path.name,path.read_bytes(),'video/mp4' if video else 'audio/wav')}).json();wait_job(client,r['job_id'])
    rid,run,items=analyze(client,r['asset_id'],'remove_silence',burn_subtitles=False)
    assert run['status']=='ready'
    report=json.loads(run['capability_report_json']);assert 3<report['removed_seconds']<4.1
    rr=client.post(f'/api/preset-runs/{rid}/render-selected',json={'candidate_ids':[items[0]['id']]}).json()
    for jid in rr['job_ids']:wait_job(client,jid)
    out=client.get('/api/clips/'+items[0]['clip_id']+'/download');assert out.status_code==200
    p=tmp_path/('output.mp4' if video else 'output.m4a');p.write_bytes(out.content)
    info=json.loads(subprocess.run(['ffprobe','-v','error','-show_entries','format=duration','-of','json',str(p)],check=True,capture_output=True,text=True).stdout)
    assert 5.8<float(info['format']['duration'])<7
    subprocess.run(['ffmpeg','-v','error','-i',str(p),'-f','null','-'],check=True,capture_output=True)

def test_preset_authentication(client,monkeypatch):
    monkeypatch.setenv('AUTH_USER','creator');monkeypatch.setenv('AUTH_PASSWORD','test-authentication-password')
    assert client.get('/api/presets').status_code==401
    assert client.get('/api/clips/missing/download').status_code==401
    assert client.get('/api/presets',auth=('creator','test-authentication-password')).status_code==200

def test_review_gates_and_language_capability(client,media_file,mixed_subtitles):
    aid=upload(client,media_file,mixed_subtitles)
    rid,_,items=analyze(client,aid,'key_takeaways',count=1)
    candidate=items[0]['id']
    assert client.patch('/api/preset-candidates/'+candidate,json={'status':'rejected'}).status_code==200
    assert client.post(f'/api/preset-runs/{rid}/render-selected',json={'candidate_ids':[candidate]}).status_code==409
    assert client.patch('/api/preset-candidates/'+candidate,json={'status':'proposed'}).status_code==200
    assert client.post(f'/api/preset-runs/{rid}/render-selected',json={'candidate_ids':['unrelated']}).status_code==404
    _,run,items=analyze(client,aid,'funny_moments',language='ta')
    assert run['status']=='unsupported' and not items
    assert 'English' in run['capability_report_json']

def test_bounded_ai_ranking_and_approved_rules(client,media_file,mixed_subtitles,monkeypatch):
    aid=upload(client,media_file,mixed_subtitles)
    with db() as c:
        c.execute("INSERT INTO brand_rules(id,text,status) VALUES ('approved','Keep explanations practical','approved'),('pending','Unapproved secret style','pending')")
    def model(instruction,content):
        payload=json.loads(content)
        assert payload['approved_brand_rules']==['Keep explanations practical']
        return {'picks':[{'index':0,'relevance':.7},{'index':9999,'relevance':1}]},'gemini'
    monkeypatch.setattr('app.ai.generate_json',model)
    _,_,items=analyze(client,aid,'key_takeaways',count=1,use_ai=True)
    assert items and items[0]['source']=='gemini'
    assert 'semantic_relevance' in items[0]['score_breakdown_json']
    assert 'lesson' in items[0]['quote'].lower() or 'step' in items[0]['quote'].lower()

def test_remaining_presets_use_real_audio_and_transcript(client,tmp_path):
    path=tmp_path/'delivery.wav'
    subprocess.run(['ffmpeg','-v','error','-y','-f','lavfi','-i',r'aevalsrc=(0.02+0.3*between(t\,8\,16))*sin(2*PI*440*t):s=16000:d=24',str(path)],check=True,capture_output=True)
    transcript='1\n00:00:00,000 --> 00:00:12,000\nOh my god! I cannot believe this funny joke. You said that was a mistake. The punchline made me laugh.\n\n2\n00:00:12,000 --> 00:00:24,000\nWe lost and it did not work, we failed. Keep going, never give up. How do we learn the lesson? First, keep trying.'
    r=client.post('/api/assets',files={'media':(path.name,path.read_bytes(),'audio/wav'),'transcript':('delivery.srt',transcript,'text/plain')}).json();wait_job(client,r['job_id'])
    for preset in ['reactions','fail_moments','funny_clips','motivation','shorts_reels']:
        _,run,items=analyze(client,r['asset_id'],preset,min_seconds=20,max_seconds=25,count=1)
        assert run['status']=='ready' and items,(preset,run)
        assert 0<=items[0]['start']<items[0]['end']<=24
        if preset=='reactions':assert json.loads(items[0]['score_breakdown_json'])['energy']>.15
    assert len(client.get('/api/export').json()['preset_runs'])==5

def test_preset_restart_recovery_and_atomic_queue(client,media_file,mixed_subtitles):
    from app.main import worker
    from app.jobs import DurableWorker,enqueue
    from app.presets import PresetConfig
    aid=upload(client,media_file,mixed_subtitles)
    rid,_,items=analyze(client,aid,'key_takeaways',count=1)
    worker.close()
    with db() as c:
        c.execute("UPDATE preset_runs SET status='analyzing' WHERE id=?",(rid,))
        c.execute("UPDATE preset_candidates SET render_status='rendering' WHERE id=?",(items[0]['id'],))
        c.execute("INSERT INTO jobs(id,kind,target_id,status,attempts,payload) VALUES ('exhausted','preset_analyze',?,'running',3,'{}'),('resumable','preset_render',?,'running',1,'{}')",(rid,items[0]['id']))
    recovered=[]
    recovery=DurableWorker(lambda job,payload:recovered.append(job['id']))
    recovery.start()
    try:
        deadline=time.monotonic()+3
        while not recovered and time.monotonic()<deadline:time.sleep(.05)
        assert recovered==['resumable']
        assert client.get(f'/api/preset-runs/{rid}').json()['status']=='failed'
        assert client.get(f'/api/preset-runs/{rid}/candidates').json()[0]['render_status']=='queued'
    finally:recovery.close()
    with pytest.raises(ValueError):
        with db() as c:
            enqueue('preset_analyze','rolled-back',connection=c)
            raise ValueError('Simulated transaction failure')
    with db() as c:assert not c.execute("SELECT 1 FROM jobs WHERE target_id='rolled-back'").fetchone()
