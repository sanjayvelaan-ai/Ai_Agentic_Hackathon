import json
import shutil
import time
from pathlib import Path
import pytest
from app.db import db
from app.youtube import canonical_youtube_url,json3_segments
from test_workflow import upload,wait_job

@pytest.mark.parametrize('url',[
    'https://www.youtube.com/watch?v=BaW_jenozKc&t=30',
    'https://youtu.be/BaW_jenozKc',
    'https://www.youtube.com/live/BaW_jenozKc',
    'youtu.be/BaW_jenozKc',
    'https://youtube.com/shorts/BaW_jenozKc',
    'https://m.youtube.com/watch?v=BaW_jenozKc',
])
def test_canonical_youtube(url):assert canonical_youtube_url(url)=='https://www.youtube.com/watch?v=BaW_jenozKc'

@pytest.mark.parametrize('url',[
    'http://youtube.com/watch?v=BaW_jenozKc','https://youtube.com.evil.invalid/watch?v=BaW_jenozKc',
    'https://127.0.0.1/watch?v=BaW_jenozKc','file:///etc/passwd','https://youtube.com@localhost/watch?v=BaW_jenozKc',
    'https://youtube.com/playlist?list=123','https://youtube.com:8443/watch?v=BaW_jenozKc',
    'https://youtu.be/../../../secret','https://youtube.com/watch?v=--exec',
])
def test_reject_unsafe_or_nonvideo_urls(url):
    with pytest.raises(ValueError):canonical_youtube_url(url)

def test_rolling_captions():
    data={'events':[{'tStartMs':0,'dDurationMs':3000,'segs':[{'utf8':'First lesson'}]},
                    {'tStartMs':2000,'dDurationMs':3000,'segs':[{'utf8':'First lesson with context'}]},
                    {'tStartMs':4000,'dDurationMs':3000,'segs':[{'utf8':'First lesson with context and examples'}]}]}
    cues=json3_segments(data,6)
    assert cues==[{'start':0,'end':2,'text':'First lesson'},{'start':2,'end':4,'text':'with context'},{'start':4,'end':6,'text':'and examples'}]

def test_automated_upload_arranges_and_renders(client,media_file,subtitles):
    asset=upload(client,media_file,subtitles)
    result=client.post(f'/api/assets/{asset}/workflow',json={'objective':'informative','clip_count':2,'target_seconds':30})
    assert result.status_code==202,result.text
    wait_job(client,result.json()['job_id'])
    flow=client.get('/api/workflows').json()[0]
    assert flow['stage']=='complete' and flow['progress']==100
    clips=client.get('/api/clips').json()
    assert len(clips)==2 and len(client.get('/api/copies').json())==18
    variants=client.get('/api/variants').json()
    assert len(variants)==2 and all(v['status']=='rendered' for v in variants)
    assert all(v['angle']=='Teach It' for v in variants)
    assert client.post(f'/api/assets/{asset}/workflow',json={}).json()['existing']

def test_youtube_pipeline_with_actual_media_fixture(client,media_file,subtitles,monkeypatch):
    from app import workflow
    from app.media import parse_subtitles
    monkeypatch.setattr(workflow.importlib.util,'find_spec',lambda name:True)
    def fixture_download(url,folder,language):
        path=Path(folder)/'source.mp4';shutil.copyfile(media_file,path)
        return {'path':str(path),'title':'YouTube adapter test fixture','segments':parse_subtitles(subtitles),'transcript_source':'youtube_captions'}
    monkeypatch.setattr(workflow,'download_youtube',fixture_download)
    result=client.post('/api/youtube',json={'url':'https://youtu.be/BaW_jenozKc','rights_confirmed':True,'auto_render':False,'clip_count':1})
    assert result.status_code==202,result.text
    wait_job(client,result.json()['job_id'])
    flow=client.get('/api/workflows').json()[0]
    assert flow['stage']=='complete' and flow['transcript_source']=='youtube_captions'
    assert len(client.get('/api/clips').json())==1
    assert len(client.get('/api/copies').json())==9
    assert not client.get('/api/variants').json()

def test_missing_transcript_resumes_same_project(client,media_file,subtitles):
    r=client.post('/api/assets',files={'media':('test.mp4',media_file.read_bytes(),'video/mp4')}).json()
    wait_job(client,r['job_id'])
    flow=client.post(f'/api/assets/{r["asset_id"]}/workflow',json={'auto_render':False}).json()
    wait_job(client,flow['job_id'])
    assert client.get('/api/workflows').json()[0]['stage']=='needs_transcript'
    assert client.post(f'/api/workflows/{flow["id"]}/resume').status_code==409
    assert client.post(f'/api/assets/{r["asset_id"]}/transcript',files={'transcript':('test.srt',subtitles)}).status_code==200
    resumed=client.post(f'/api/workflows/{flow["id"]}/resume').json()
    wait_job(client,resumed['job_id'])
    assert client.get('/api/workflows').json()[0]['stage']=='complete'
    assert len(client.get('/api/assets').json())==1

def test_youtube_requires_rights_and_valid_options(client):
    assert client.post('/api/youtube',json={'url':'https://youtu.be/BaW_jenozKc'}).status_code==400
    assert client.post('/api/youtube',json={'url':'https://youtu.be/BaW_jenozKc','rights_confirmed':True,'clip_count':50}).status_code==422
    assert client.post('/api/youtube',json={'url':'https://localhost/test','rights_confirmed':True}).status_code==400
    caps=client.get('/api/capabilities').json()
    assert caps['api_key_required'] is False and caps['ai_configured'] is False

def test_speech_rounding_stays_inside_source(client,media_file,monkeypatch):
    from app import main
    monkeypatch.setattr(main,'transcribe',lambda path:[{'start':0,'end':96.2,'text':'A source-aligned speech test.'}])
    result=client.post('/api/assets',files={'media':('speech.mp4',media_file.read_bytes(),'video/mp4')}).json()
    wait_job(client,result['job_id'])
    asset=client.get('/api/assets').json()[0]
    segments=client.get(f'/api/assets/{asset["id"]}/transcript').json()
    assert asset['status']=='ready'
    assert segments[-1]['end']==asset['duration']

def test_paused_project_can_resume_after_local_speech_setup(client,media_file,subtitles,monkeypatch):
    from app import main
    from app.media import parse_subtitles
    source=client.post('/api/assets',files={'media':('speech.mp4',media_file.read_bytes(),'video/mp4')}).json()
    wait_job(client,source['job_id'])
    flow=client.post(f'/api/assets/{source["asset_id"]}/workflow',json={'auto_render':False}).json()
    wait_job(client,flow['job_id'])
    assert client.get('/api/workflows').json()[0]['stage']=='needs_transcript'
    monkeypatch.setenv('TRANSCRIPTION_BACKEND','faster-whisper')
    monkeypatch.setattr(main,'transcribe',lambda path:parse_subtitles(subtitles))
    resumed=client.post(f'/api/workflows/{flow["id"]}/resume')
    assert resumed.status_code==202,resumed.text
    wait_job(client,resumed.json()['job_id'])
    assert client.get('/api/workflows').json()[0]['stage']=='complete'
    assert len(client.get('/api/assets').json())==1

def test_restricted_youtube_error_is_actionable(client,monkeypatch):
    from app import workflow
    monkeypatch.setattr(workflow.importlib.util,'find_spec',lambda name:True)
    def fail(*args):raise ValueError('YouTube restricted this video. Upload your original file.')
    monkeypatch.setattr(workflow,'download_youtube',fail)
    r=client.post('/api/youtube',json={'url':'https://youtu.be/BaW_jenozKc','rights_confirmed':True}).json()
    for _ in range(60):
        flow=client.get('/api/workflows').json()[0]
        if flow['stage']=='failed':break
        time.sleep(.1)
    assert flow['stage']=='failed' and 'Upload your original' in flow['error']


def test_valid_model_selection_precedes_heuristic_ranking(client,media_file,subtitles,monkeypatch):
    from app import main
    asset=upload(client,media_file,subtitles)
    monkeypatch.setattr(main,'generate_json',lambda *args:({'clips':[{'first':2,'last':3,'title':'Model selected story','reason':'A complete source-grounded story.'}]},'gemini'))
    result=client.post(f'/api/assets/{asset}/discover').json()
    assert result['candidates'][0]['source']=='gemini'
    assert result['candidates'][0]['start']==24


def test_replan_preserves_previous_project_and_source_evidence(client,media_file,subtitles):
    aid=upload(client,media_file,subtitles)
    first=client.post(f'/api/assets/{aid}/workflow',json={'auto_render':False,'clip_count':1}).json()
    wait_job(client,first['job_id'])
    original=client.get('/api/clips').json()[0]
    revised=client.post(f'/api/workflows/{first["id"]}/replan')
    assert revised.status_code==202,revised.text
    wait_job(client,revised.json()['job_id'])
    assert len(client.get('/api/workflows').json())==2
    assert original in client.get('/api/clips').json()
    old=client.get(f'/api/assets/{aid}/transcript').json()
    new=client.get('/api/assets/'+revised.json()['asset_id']+'/transcript').json()
    assert [(s['start'],s['end'],s['text']) for s in old]==[(s['start'],s['end'],s['text']) for s in new]
