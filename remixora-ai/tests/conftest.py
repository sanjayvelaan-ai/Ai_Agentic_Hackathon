import os
import tempfile
from pathlib import Path

_test_data=tempfile.TemporaryDirectory(prefix='remixora-tests-')
os.environ['DATA_DIR']=_test_data.name
os.environ['AI_PROVIDER']='none'
os.environ['TRANSCRIPTION_BACKEND']='none'
root=Path(__file__).resolve().parents[1]
bins=list((root/'.tools'/'ffmpeg').glob('*/bin'))
if bins:os.environ['PATH']=str(bins[0])+os.pathsep+os.environ['PATH']

import pytest
from fastapi.testclient import TestClient
from app.main import app, attempts
from app.db import DB_FILE

@pytest.fixture
def client(monkeypatch):
    monkeypatch.delenv('AUTH_USER',raising=False);monkeypatch.delenv('AUTH_PASSWORD',raising=False)
    attempts.clear()
    for suffix in ['', '-wal','-shm']:
        try:
            Path(str(DB_FILE)+suffix).unlink(missing_ok=True)
        except OSError:
            pass
    with TestClient(app) as client:yield client

@pytest.fixture(scope='session')
def media_file(tmp_path_factory):
    import subprocess
    folder=tmp_path_factory.mktemp('media')
    video=folder/'source.mp4'
    subprocess.run(['ffmpeg','-v','error','-y','-f','lavfi','-i','testsrc2=size=320x180:rate=12','-f','lavfi','-i','sine=frequency=440:sample_rate=22050','-t','96','-c:v','libx264','-preset','ultrafast','-crf','35','-c:a','aac','-shortest',str(video)],check=True,capture_output=True,timeout=60)
    return video

@pytest.fixture
def subtitles():
    # Synthetic structural test fixture, not a real speech transcription.
    lines=['How can we learn the first important lesson? Because clear steps help people learn.',
           'First choose one useful tip and explain why it matters to your audience.',
           'When I started, we were working in a small room. One day I felt ready.',
           'Then I shared my experience. We were learning together and I felt understood.',
           'This is a mistake. The myth is wrong. Instead try the opposite, but review context.',
           'Actually that claim is wrong. However, the mistake is assuming more is always better.',
           'How do we learn another useful lesson? First focus on clarity because it matters.',
           'Here is an important tip. Explain why the first step helps people learn.']
    def ts(s):return f'00:{s//60:02}:{s%60:02},000'
    return '\n\n'.join(f'{i+1}\n{ts(i*12)} --> {ts((i+1)*12)}\n{text}' for i,text in enumerate(lines))
