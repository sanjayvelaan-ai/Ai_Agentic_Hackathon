"""Exercise the deployed local HTTP app with the original, labeled narrated demo."""
import hashlib
import json
import time
from pathlib import Path
import httpx

root=Path(__file__).resolve().parents[1]
report={'fixture':'Original script with explicitly labeled synthetic narration','source_seconds':309.46}
with httpx.Client(base_url='http://127.0.0.1:8000',timeout=120) as c:
    def call(method,path,**kwargs):
        response=c.request(method,path,**kwargs);response.raise_for_status();return response.json()
    def wait(job_id):
        started=time.monotonic()
        while time.monotonic()-started<180:
            jobs=call('GET','/api/jobs');job=next(j for j in jobs if j['id']==job_id)
            if job['status']=='completed':return round(time.monotonic()-started,2)
            if job['status']=='failed':raise RuntimeError(job['error'])
            time.sleep(.3)
        raise RuntimeError('Job timeout')
    started=time.monotonic()
    with (root/'demo/original-demo.mp4').open('rb') as media,(root/'demo/source.srt').open('rb') as transcript:
        result=call('POST','/api/assets',files={'media':('DEMO - synthetic narration.mp4',media,'video/mp4'),'transcript':('demo.srt',transcript,'text/plain')})
    if result.get('job_id'):wait(result['job_id'])
    report['ingest_seconds']=round(time.monotonic()-started,2)
    asset=result['asset_id'];report['asset_id']=asset
    picks=call('POST',f'/api/assets/{asset}/discover')['candidates']
    assert len(picks)==3
    report['clips']=[{'id':p['id'],'start':p['start'],'end':p['end'],'source':p['source']} for p in picks]
    copies=call('POST',f'/api/clips/{picks[0]["id"]}/remix')['copies']
    assert len(copies)==9
    report['drafts']=len(copies);report['exports']=[]
    for angle in ['Teach It','Tell It']:
        v=call('POST',f'/api/clips/{picks[0]["id"]}/variants',json={'angle':angle,'headline':angle+': '+picks[0]['title'][:75],'subtitles':True})
        elapsed=wait(v['job_id']) if v.get('job_id') else 0
        response=c.get(f'/api/variants/{v["id"]}/download');response.raise_for_status()
        report['exports'].append({'variant_id':v['id'],'angle':angle,'render_seconds':elapsed,'bytes':len(response.content),'sha256':hashlib.sha256(response.content).hexdigest()})
    assert report['exports'][0]['sha256']!=report['exports'][1]['sha256']
    report['health']=call('GET','/health')
(root/'test-results').mkdir(exist_ok=True)
(root/'test-results/live-smoke.json').write_text(json.dumps(report,indent=2))
print(json.dumps(report,indent=2))
