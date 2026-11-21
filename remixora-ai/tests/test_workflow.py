import hashlib
import io
import json
import subprocess
import time
from datetime import datetime,timedelta,timezone
from pathlib import Path
import pytest
from app.db import db,init_db
from app.main import app,process_job
from app.jobs import DurableWorker,enqueue
from app.media import parse_subtitles,time_seconds
from app.ai import infer_rules,apply_rules

def wait_job(client,job_id):
    deadline=time.monotonic()+100
    while time.monotonic()<deadline:
        job=next(j for j in client.get('/api/jobs').json() if j['id']==job_id)
        if job['status'] in {'completed','failed'}:
            assert job['status']=='completed',job
            return job
        time.sleep(.2)
    raise AssertionError('Job timed out')

def upload(client,media_file,subtitles):
    response=client.post('/api/assets',files={'media':('source.mp4',media_file.read_bytes(),'video/mp4'),'transcript':('source.srt',subtitles.encode(),'text/plain')})
    assert response.status_code==202,response.text
    result=response.json();wait_job(client,result['job_id'])
    return result['asset_id']

def new_source(original):
    import uuid
    asset_id=uuid.uuid4().hex
    with db() as c:
        asset=dict(c.execute('SELECT * FROM assets WHERE id=?',(original,)).fetchone())
        c.execute('INSERT INTO assets(id,filename,media_path,media_kind,duration,status) VALUES (?,?,?,?,?,?)',(asset_id,'future.mp4',asset['media_path'],'video',asset['duration'],'ready'))
        c.execute('INSERT INTO segments(asset_id,start,end,text) SELECT ?,start,end,text FROM segments WHERE asset_id=?',(asset_id,original))
    return asset_id

def test_persistent_end_to_end(client,media_file,subtitles,tmp_path):
    asset=upload(client,media_file,subtitles)
    discovered=client.post(f'/api/assets/{asset}/discover')
    assert discovered.status_code==200,discovered.text
    clips=discovered.json()['candidates'];assert len(clips)==3
    segments=client.get(f'/api/assets/{asset}/transcript').json()
    for clip in clips:
        evidence=json.loads(clip['evidence'])
        assert clip['quote']==' '.join(s['text'] for s in segments if s['id'] in evidence)
        assert 15<=clip['end']-clip['start']<=60
    first=clips[0]
    drafts=client.post(f'/api/clips/{first["id"]}/remix').json()['copies']
    assert len(drafts)==9 and len({c['content'] for c in drafts})==9
    draft=next(c for c in drafts if c['platform']=='instagram')
    before=draft['content'];revised=before.split('\n#')[0]
    edited=client.patch(f'/api/copies/{draft["id"]}',json={'content':revised}).json()
    rule=next(r for r in edited['proposed_rules'] if 'hashtags' in r['text'])
    assert rule['status']=='pending'
    assert client.post(f'/api/brand-rules/{rule["id"]}/approve').status_code==200
    next_drafts=client.post(f'/api/clips/{clips[1]["id"]}/remix').json()['copies']
    assert all('#' not in c['content'] for c in next_drafts)
    assert any(rule['id'] in c['rules_used'] for c in next_drafts)
    schedule={'copy_id':draft['id'],'scheduled_at':(datetime.now(timezone.utc)+timedelta(days=3)).isoformat(),'timezone':'Asia/Kolkata'}
    assert client.post('/api/calendar',json=schedule).status_code==409
    assert client.post(f'/api/copies/{draft["id"]}/approve').status_code==200
    scheduled=client.post('/api/calendar',json=schedule)
    assert scheduled.status_code==200,scheduled.text
    assert client.post('/api/calendar',json=schedule).status_code==409
    schedule['timezone']='Invalid/Zone'
    assert client.post('/api/calendar',json=schedule).status_code==400
    init_db()
    assert client.get('/api/calendar').json()[0]['id']==scheduled.json()['id']
    # Actual FFmpeg exports must decode and have distinct bytes.
    outputs=[]
    for angle in ['Teach It','Tell It']:
        r=client.post(f'/api/clips/{first["id"]}/variants',json={'angle':angle,'headline':angle+': a clear first step','subtitles':True})
        assert r.status_code==202,r.text
        wait_job(client,r.json()['job_id'])
        output=client.get(f'/api/variants/{r.json()["id"]}/download')
        assert output.status_code==200
        path=tmp_path/(angle+'.mp4');path.write_bytes(output.content);outputs.append(output.content)
        subprocess.run(['ffmpeg','-v','error','-i',str(path),'-f','null','-'],check=True,capture_output=True,timeout=60)
    assert hashlib.sha256(outputs[0]).digest()!=hashlib.sha256(outputs[1]).digest()
    # Baseline two future sources, then actual metrics must adjust both later sources.
    baseline=client.post(f'/api/assets/{new_source(asset)}/discover').json()['candidates']
    import_csv='clip_id,platform,angle,impressions,views,likes,comments,shares,saves,period\n'
    for clip in clips:
        for angle,likes in [('Teach It',350),('Tell It',10),('Challenge It',5)]:
            import_csv+=f'{clip["id"]},instagram,{angle},1000,700,{likes},5,5,5,lifetime\n'
    result=client.post('/api/analytics/import',files={'csv_file':('metrics.csv',import_csv)},data={'source':'actual'})
    assert result.status_code==200,result.text
    assert result.json()['imported']==9
    again=client.post('/api/analytics/import',files={'csv_file':('metrics.csv',import_csv)},data={'source':'actual'}).json()
    assert again['imported']==0 and again['duplicates']==9
    for _ in range(2):
        after=client.post(f'/api/assets/{new_source(asset)}/discover').json()['candidates']
        assert any(c['adjustment']!=0 for c in after)
        assert [(c['title'],c['score']) for c in after]!=[(c['title'],c['score']) for c in baseline]
    historical=client.post(f'/api/assets/{asset}/discover').json()['candidates']
    assert all(c['adjustment']==0 for c in historical)
    assert client.get('/api/export').status_code==200

def test_media_rejections_and_transcript_repair(client,media_file,subtitles):
    assert client.post('/api/assets',files={'media':('fake.mp4',b'not video','video/mp4')}).status_code==400
    assert client.post('/api/assets',files={'media':('file.exe',b'no','application/octet-stream')}).status_code==400
    assert client.post('/api/assets',headers={'content-length':str(500*1024**2)},content=b'').status_code==413
    asset=upload(client,media_file,subtitles)
    seg=client.get(f'/api/assets/{asset}/transcript').json()
    seg[0]['text']='A repaired transcript segment.'
    assert client.put(f'/api/assets/{asset}/transcript',json={'segments':seg}).status_code==200
    seg[0]['end']=200
    assert client.put(f'/api/assets/{asset}/transcript',json={'segments':seg}).status_code==400
    assert client.post('/api/assets',files={'media':('source.mp4',media_file.read_bytes(),'video/mp4')}).json()['duplicate']

def test_auth_and_cross_origin(client,monkeypatch):
    monkeypatch.setenv('AUTH_USER','creator');monkeypatch.setenv('AUTH_PASSWORD','correct-long-password')
    assert client.get('/api/assets').status_code==401
    assert client.get('/health').status_code==200
    assert client.get('/api/assets',auth=('creator','correct-long-password')).status_code==200
    assert client.post('/api/brand-rules',json={'text':'Avoid hashtags'},auth=('creator','correct-long-password'),headers={'origin':'https://evil.invalid'}).status_code==403
    assert client.get('/static/app.js').status_code==401

@pytest.mark.parametrize('value',['00:60:00,000','00:00:99,000','garbage'])
def test_invalid_timestamps(value):
    with pytest.raises(ValueError):time_seconds(value)

def test_overlap_rejected():
    with pytest.raises(ValueError):parse_subtitles('1\n00:00:00,000 --> 00:00:12,000\nA\n\n2\n00:00:10,000 --> 00:00:15,000\nB')

def test_inferred_rules_are_specific():
    assert 'Avoid hashtags in captions' in infer_rules('Hello #test','Hello')
    assert any('question' in r for r in infer_rules('We learn together.','How can we learn together?'))
    assert any('hype' in r for r in infer_rules('Great!','Great.'))
    assert any('vocabulary' in r for r in infer_rules('We leverage tools.','We use tools.'))
    assert infer_rules('same words','same words')==[]
    assert apply_rules('We leverage tools. “We leverage tools.”',[{'text':'Prefer vocabulary: leverage => use'}])=='We use tools. “We leverage tools.”'

def test_worker_restart_recovery(client):
    from app.main import worker
    worker.close()
    job_id=enqueue('test','target')
    with db() as c:c.execute("UPDATE jobs SET status='running',attempts=1 WHERE id=?",(job_id,))
    calls=[]
    recovery=DurableWorker(lambda job,payload:calls.append(job['id']))
    recovery.start()
    try:
        for _ in range(30):
            with db() as c:job=dict(c.execute('SELECT * FROM jobs WHERE id=?',(job_id,)).fetchone())
            if job['status']=='completed':break
            time.sleep(.1)
        assert job['status']=='completed' and job['attempts']==2 and calls==[job_id]
    finally:recovery.close()

def test_invalid_csv_atomic(client):
    r=client.post('/api/analytics/import',files={'csv_file':('bad.csv','clip_id,platform\nunknown,instagram')})
    assert r.status_code==400
    assert client.get('/api/insights').json()['groups']==[]

def test_provider_failover(monkeypatch,client):
    import httpx
    from app.ai import generate_json
    monkeypatch.setenv('AI_PROVIDER','auto');monkeypatch.setenv('GEMINI_API_KEY','test-not-real');monkeypatch.setenv('GEMINI_MODEL','configured-model')
    monkeypatch.setenv('OLLAMA_URL','http://127.0.0.1:11434/v1');monkeypatch.setenv('OLLAMA_MODEL','local-model')
    calls=[]
    def post(self,url,**kwargs):
        calls.append(url)
        if 'googleapis' in url:return httpx.Response(429,headers={'retry-after':'0'},request=httpx.Request('POST',url))
        return httpx.Response(200,json={'choices':[{'message':{'content':'{"ok":true}'}}]},request=httpx.Request('POST',url))
    monkeypatch.setattr(httpx.Client,'post',post)
    result,provider=generate_json('unit failover','bounded context')
    assert result=={'ok':True} and provider=='ollama' and len(calls)==3
    assert generate_json('unit failover','bounded context')==(result,provider)
    assert len(calls)==3


def test_backup_restore(client,tmp_path):
    from scripts.backup import backup,restore
    from app.db import DATA_DIR
    client.post('/api/brand-rules',json={'text':'Avoid hashtags in captions'})
    saved=backup(DATA_DIR,tmp_path/'backup')
    restored=restore(saved,tmp_path/'restored')
    import sqlite3
    from contextlib import closing
    with closing(sqlite3.connect(restored/'remixora.sqlite3')) as c:
        assert c.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        assert c.execute('SELECT COUNT(*) FROM brand_rules').fetchone()[0]==1
    with pytest.raises(ValueError):restore(saved,restored)


def test_three_sequential_audio_uploads_and_missing_transcript(client,tmp_path):
    import wave
    for n in range(3):
        path=tmp_path/f'{n}.wav'
        with wave.open(str(path),'wb') as out:
            out.setnchannels(1);out.setsampwidth(2);out.setframerate(8000)
            out.writeframes(bytes([n,0])*8000*(n+2))
        r=client.post('/api/assets',files={'media':(path.name,path.read_bytes(),'audio/wav')})
        assert r.status_code==202,r.text
        wait_job(client,r.json()['job_id'])
    assert len(client.get('/api/assets').json())==3
    assert all(a['status']=='transcript_required' for a in client.get('/api/assets').json())


def test_storage_quota_rejection(client,media_file,monkeypatch):
    monkeypatch.setenv('STORAGE_QUOTA_MB','1')
    assert client.post('/api/assets',files={'media':('source.mp4',media_file.read_bytes(),'video/mp4')}).status_code==507


def test_profile_controls_change_new_copy():
    from app.ai import make_copies
    clip={'quote':'Here is a practical lesson about thoughtful editing and why it matters.'}
    normal=make_copies(clip,[])
    personal=make_copies(clip,[],{'hashtags':False,'sentence_length':'short','cta_pattern':'Share one lesson from your own work.'})
    assert normal!=personal and all('#' not in x[2] for x in personal)
    assert all('Share one lesson' in x[2] for x in personal)


def test_synthetic_import_cannot_be_mislabeled_actual(client,media_file,subtitles):
    asset=upload(client,media_file,subtitles)
    client.post(f'/api/assets/{asset}/discover')
    sample=client.get('/api/analytics/sample')
    assert sample.status_code==200
    result=client.post('/api/analytics/import',files={'csv_file':('SYNTHETIC.csv',sample.content)},data={'source':'actual'})
    assert result.status_code==200
    assert all(g['source']=='synthetic' for g in result.json()['insights']['groups'])
    future=client.post(f'/api/assets/{new_source(asset)}/discover').json()['candidates']
    assert all(c['adjustment']==0 for c in future)


def test_reject_text_playlists_without_network(client):
    r=client.post('/api/assets',files={'media':('pretend.mp4',b'#EXTM3U\nhttps://example.invalid/private','video/mp4')})
    assert r.status_code==400
    assert 'binary media container' in r.json()['detail']


def test_storage_diagnostics_tolerates_disappearing_sqlite_sidecars(tmp_path,monkeypatch):
    from app.main import directory_size
    stable=tmp_path/'data.mp4';stable.write_bytes(b'123456')
    vanished=tmp_path/'remixora.sqlite3-shm'
    monkeypatch.setattr(Path,'rglob',lambda self,pattern:iter([stable,vanished]))
    assert directory_size(tmp_path)==6
