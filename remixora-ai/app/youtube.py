"""Strict YouTube URL ingestion, with an isolated and time-bounded downloader."""
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlsplit,parse_qs

def canonical_youtube_url(value):
    try:
        value=value.strip()
        if value.startswith(('youtube.com/','www.youtube.com/','m.youtube.com/','youtu.be/','www.youtu.be/')):value='https://'+value
        url=urlsplit(value)
        if url.scheme!='https' or url.username or url.password or url.port not in {None,443}:raise ValueError()
        host=(url.hostname or '').lower()
        if host in {'youtu.be','www.youtu.be'}:video_id=url.path.strip('/')
        elif host in {'youtube.com','www.youtube.com','m.youtube.com'}:
            if url.path=='/watch':video_id=parse_qs(url.query).get('v',[''])[0]
            else:
                match=re.fullmatch(r'/(?:shorts|embed|live)/([A-Za-z0-9_-]{11})/?',url.path)
                video_id=match[1] if match else ''
        else:raise ValueError()
        if not re.fullmatch(r'[A-Za-z0-9_-]{11}',video_id):raise ValueError()
    except ValueError:raise ValueError('Paste an HTTPS YouTube watch, Shorts or youtu.be link to a single video.')
    return 'https://www.youtube.com/watch?v='+video_id

def json3_segments(data,duration):
    """Normalize rolling automatic captions into ordered, non-overlapping cues."""
    cues=[];previous=''
    for event in data.get('events',[]):
        text=' '.join(''.join(s.get('utf8','') for s in event.get('segs',[])).split())
        if not text or not event.get('dDurationMs'):continue
        start=max(0,float(event.get('tStartMs',0))/1000)
        end=min(duration,start+float(event['dDurationMs'])/1000)
        if text==previous:continue
        original=text
        if previous and text.startswith(previous+' '):text=text[len(previous):].strip()
        previous=original
        if start<end:cues.append({'start':start,'end':end,'text':text})
    cues.sort(key=lambda s:s['start'])
    cleaned=[]
    for i,cue in enumerate(cues):
        if i+1<len(cues):cue['end']=min(cue['end'],cues[i+1]['start'])
        if cue['end']>cue['start']:cleaned.append(cue)
    return cleaned

def download_youtube(url,folder,language='en'):
    url=canonical_youtube_url(url);folder=Path(folder).resolve();folder.mkdir(parents=True,exist_ok=True)
    try:
        result=subprocess.run([sys.executable,'-m','app.youtube_worker',url,str(folder),language],capture_output=True,text=True,timeout=600)
    except subprocess.TimeoutExpired:raise ValueError('YouTube import timed out. Try again or upload your original file.')
    if result.returncode or not (folder/'result.json').is_file():
        if (folder/'error.json').is_file():raise ValueError(json.loads((folder/'error.json').read_text())['error'])
        raise ValueError('YouTube import could not run. Check yt-dlp, Node.js, FFmpeg and your connection in System Health.')
    return json.loads((folder/'result.json').read_text(encoding='utf-8'))

def safe_download_error(error):
    message=str(error).lower()
    if 'duration limit' in message:return 'This video exceeds the configured duration limit. Upload a shorter source.'
    if 'size limit' in message or 'filesize' in message:return 'This download exceeds the configured media size limit. Upload a smaller source.'
    if any(x in message for x in ['sign in','bot','403','429','private','unavailable','age','members','premium']):
        return 'YouTube restricted this video or request. Use a publicly accessible video you may repurpose, or upload your original file. No cookies or access bypass are used.'
    return 'YouTube could not provide this media. Check connectivity, update yt-dlp, or upload your original file.'
