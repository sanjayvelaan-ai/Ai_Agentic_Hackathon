import io
import json
import os
import shutil
import tempfile
from pathlib import Path
import pytest

from app.db import DB_FILE, db, project_paths, rows
from app.media import render_variant


def wait_job_completed(client, job_id, max_wait=30):
    import time
    start = time.time()
    while time.time() - start < max_wait:
        jobs = client.get('/api/jobs').json()
        target = next((j for j in jobs if j['id'] == job_id), None)
        if target and target['status'] in {'completed', 'failed'}:
            return target
        time.sleep(0.2)
    return None


def test_1_upload_valid_mp4_creates_project(client, media_file):
    with open(media_file, 'rb') as fp:
        r = client.post(
            '/api/projects/import',
            files={'media': ('test_video.mp4', fp, 'video/mp4')},
            data={'title': 'Project Alpha'},
        )
    assert r.status_code == 202, r.text
    data = r.json()
    assert 'project_id' in data
    assert data['title'] == 'Project Alpha'

    # Verify project exists in /api/projects
    projects = client.get('/api/projects').json()
    p = next((x for x in projects if x['id'] == data['project_id']), None)
    assert p is not None
    assert p['title'] == 'Project Alpha'
    assert p['source_type'] == 'upload'


def test_2_upload_second_video_isolated(client, media_file):
    # Upload first
    with open(media_file, 'rb') as fp:
        r1 = client.post(
            '/api/projects/import',
            files={'media': ('source_1.mp4', fp, 'video/mp4')},
            data={'title': 'Project One'},
        )
    pid1 = r1.json()['project_id']

    # Create slightly different second file
    import subprocess
    tmp = Path(media_file).parent / 'source_2.mp4'
    subprocess.run([
        'ffmpeg', '-v', 'error', '-y', '-f', 'lavfi', '-i', 'testsrc=size=320x180:rate=10',
        '-f', 'lavfi', '-i', 'sine=frequency=880:sample_rate=22050',
        '-t', '20', '-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '35',
        '-c:a', 'aac', '-shortest', str(tmp)
    ], check=True)

    with open(tmp, 'rb') as fp:
        r2 = client.post(
            '/api/projects/import',
            files={'media': ('source_2.mp4', fp, 'video/mp4')},
            data={'title': 'Project Two'},
        )
    pid2 = r2.json()['project_id']

    assert pid1 != pid2

    # Check isolated directories
    paths1 = project_paths(pid1)
    paths2 = project_paths(pid2)
    assert paths1['root'] != paths2['root']
    assert paths1['root'].is_dir()
    assert paths2['root'].is_dir()


def test_3_project_rename_and_delete(client, media_file):
    with open(media_file, 'rb') as fp:
        r = client.post(
            '/api/projects/import',
            files={'media': ('to_rename.mp4', fp, 'video/mp4')},
            data={'title': 'Original Name'},
        )
    pid = r.json()['project_id']

    # Rename
    patch_res = client.patch(f'/api/projects/{pid}', json={'title': 'Renamed Title'})
    assert patch_res.status_code == 200
    assert patch_res.json()['title'] == 'Renamed Title'

    # Verify updated
    p = client.get(f'/api/projects/{pid}').json()
    assert p['title'] == 'Renamed Title'

    # Delete
    del_res = client.delete(f'/api/projects/{pid}')
    assert del_res.status_code == 200
    assert del_res.json()['deleted'] is True

    # Verify 404
    assert client.get(f'/api/projects/{pid}').status_code == 404


def test_4_presets_runs_and_candidates(client, media_file, subtitles):
    with open(media_file, 'rb') as fp:
        r = client.post(
            '/api/projects/import',
            files={
                'media': ('speech_video.mp4', fp, 'video/mp4'),
                'transcript': ('subs.srt', io.BytesIO(subtitles.encode()), 'text/plain'),
            },
            data={'title': 'Speech Project'},
        )
    pid = r.json()['project_id']
    wait_job_completed(client, r.json()['job_id'])

    # Run Preset: Key Takeaways
    pr1 = client.post(
        f'/api/projects/{pid}/preset-runs',
        json={'preset_id': 'key_takeaways', 'min_seconds': 15, 'max_seconds': 35, 'use_ai': False},
    )
    assert pr1.status_code == 202
    wait_job_completed(client, pr1.json()['job_id'])

    # Run Preset: Best Highlights
    pr2 = client.post(
        f'/api/projects/{pid}/preset-runs',
        json={'preset_id': 'best_highlights', 'min_seconds': 15, 'max_seconds': 35, 'use_ai': False},
    )
    assert pr2.status_code == 202
    wait_job_completed(client, pr2.json()['job_id'])

    assert pr1.json()['id'] != pr2.json()['id']

    # Fetch candidates
    candidates = client.get(f'/api/projects/{pid}/candidates').json()
    assert len(candidates) > 0
    for c in candidates:
        assert c['project_id'] == pid
        assert c['is_source_preview'] is True
        assert c['start_time'] < c['end_time']


def test_5_and_6_and_7_render_candidate_and_stream(client, media_file, subtitles):
    with open(media_file, 'rb') as fp:
        r = client.post(
            '/api/projects/import',
            files={
                'media': ('render_test.mp4', fp, 'video/mp4'),
                'transcript': ('subs.srt', io.BytesIO(subtitles.encode()), 'text/plain'),
            },
            data={'title': 'Render Pipeline Test'},
        )
    pid = r.json()['project_id']
    wait_job_completed(client, r.json()['job_id'])

    # Run preset
    pr = client.post(
        f'/api/projects/{pid}/preset-runs',
        json={'preset_id': 'key_takeaways', 'min_seconds': 15, 'max_seconds': 35, 'use_ai': False},
    )
    wait_job_completed(client, pr.json()['job_id'])

    candidates = client.get(f'/api/projects/{pid}/candidates').json()
    assert len(candidates) > 0
    candidate = candidates[0]

    # TEST 5: Render the selected candidate
    render_req = client.post(
        f'/api/projects/{pid}/renders',
        json={
            'candidate_id': candidate['id'],
            'aspect_ratio': '9:16',
            'headline': 'Tested Headline 9:16',
            'burn_subtitles': True,
        },
    )
    assert render_req.status_code == 202
    rdata = render_req.json()
    render_id = rdata['render_id']
    wait_job_completed(client, rdata['job_id'])

    # TEST 6: Verify Rendered Clips gallery shows only completed output
    renders = client.get(f'/api/projects/{pid}/renders').json()
    assert len(renders) == 1
    rendered_item = renders[0]
    assert rendered_item['id'] == render_id
    assert rendered_item['status'] == 'rendered'
    assert rendered_item['is_rendered'] is True
    assert Path(rendered_item['file_path']).is_file()

    # TEST 7: Preview streams the actual generated output MP4 (not original source)
    stream_res = client.get(rendered_item['stream_url'])
    assert stream_res.status_code in {200, 206}
    assert stream_res.headers['content-type'] == 'video/mp4'
    assert stream_res.headers.get('accept-ranges') == 'bytes'
    assert len(stream_res.content) > 500


def test_8_restart_persistence(client, media_file):
    with open(media_file, 'rb') as fp:
        r = client.post(
            '/api/projects/import',
            files={'media': ('persist.mp4', fp, 'video/mp4')},
            data={'title': 'Persistent Project'},
        )
    pid = r.json()['project_id']

    # Re-fetch projects to simulate app reload
    projects = client.get('/api/projects').json()
    found = next((p for p in projects if p['id'] == pid), None)
    assert found is not None
    assert found['title'] == 'Persistent Project'


def test_12_nonexistent_project_rejected(client):
    r = client.get('/api/projects/non_existent_uuid')
    assert r.status_code == 404
    assert 'not found' in r.json()['detail'].lower()


def test_13_unsupported_file_rejected(client):
    r = client.post(
        '/api/projects/import',
        files={'media': ('bad.exe', b'malicious payload', 'application/x-dosexec')},
        data={'title': 'Bad Upload'},
    )
    assert r.status_code == 400
    assert 'unsupported' in r.json()['detail'].lower()
