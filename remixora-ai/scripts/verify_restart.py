import json
from pathlib import Path
import httpx
root=Path(__file__).resolve().parents[1]
with httpx.Client(base_url='http://127.0.0.1:8000',timeout=10) as c:
    health=c.get('/health').json();assert health['status']=='ok' and health['worker_alive']
    status=c.get('/api/status').json();assert status['counts']['assets']>=1 and status['counts']['clips']>=3 and status['counts']['copies']>=9
    calendar=c.get('/api/calendar').json();assert any(i['status']=='scheduled_in_app' for i in calendar)
    rules=c.get('/api/brand-rules').json();assert any(r['status']=='pending' and r['evidence_edit_id'] for r in rules)
    variants=c.get('/api/variants').json();assert sum(v['status']=='rendered' for v in variants)>=2
    for variant in variants:
        if variant['status']=='rendered':assert c.get(f'/api/variants/{variant["id"]}/download').status_code==200
    sample=c.get('/api/analytics/sample');assert sample.status_code==200 and 'synthetic' in sample.text
    result={'health':health,'persistent_counts':status['counts'],'schedule_survived':True,'edit_evidence_survived':True,'exports_available':True}
(root/'test-results/restart.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
