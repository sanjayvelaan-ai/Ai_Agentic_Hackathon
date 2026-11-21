"""Bounded local measurements; energy is not laughter or facial recognition."""
import json, re, subprocess
import numpy as np
from .db import db

def audio_signals(path,duration):
    raw=subprocess.run(['ffmpeg','-v','error','-i',str(path),'-vn','-ac','1','-ar','8000','-f','f32le','pipe:1'],capture_output=True,check=True,timeout=180).stdout
    samples=np.frombuffer(raw,dtype='<f4'); result=[]
    for i in range(0,len(samples),8000):
        block=samples[i:i+8000]
        rms=float(np.sqrt(np.mean(block*block))) if len(block) else 0
        result.append({'start':i/8000,'end':min(duration,(i+8000)/8000),'db':round(20*np.log10(max(rms,1e-6)),2)})
    return result

def visual_signals(path,duration):
    raw=subprocess.run(['ffmpeg','-v','error','-i',str(path),'-an','-vf','fps=1/5,scale=160:90','-pix_fmt','gray','-f','rawvideo','-threads','2','pipe:1'],capture_output=True,check=True,timeout=180).stdout
    result=[];previous=None
    for i in range(min(len(raw)//14400,360)):
        frame=np.frombuffer(raw[i*14400:(i+1)*14400],dtype=np.uint8).reshape(90,160).astype(float)/255
        edge=float(np.mean(np.abs(np.diff(frame,axis=1)))+np.mean(np.abs(np.diff(frame,axis=0))))
        motion=float(np.mean(np.abs(frame-previous))) if previous is not None else 0
        result.append({'start':i*5,'end':min(duration,(i+1)*5),'brightness':round(float(frame.mean()),4),'sharpness':round(edge,4),'change':round(motion,4)})
        previous=frame
    return result

def cached_signals(asset,kind):
    from pathlib import Path
    p=Path(asset['media_path']);fingerprint=f'{p.stat().st_size}:{p.stat().st_mtime_ns}:v1'
    with db() as c:r=c.execute('SELECT data FROM media_analysis_cache WHERE asset_id=? AND kind=? AND fingerprint=?',(asset['id'],kind,fingerprint)).fetchone()
    if r:return json.loads(r['data'])
    value=visual_signals(p,asset['duration']) if kind=='visual' else audio_signals(p,asset['duration'])
    with db() as c:
        c.execute('INSERT OR REPLACE INTO media_analysis_cache VALUES (?,?,?,?,CURRENT_TIMESTAMP)',(asset['id'],kind,fingerprint,json.dumps(value)))
    return value

def silence_edl(path,duration,threshold=-38,minimum=.8,padding=.2):
    proc=subprocess.run(['ffmpeg','-hide_banner','-i',str(path),'-af',f'silencedetect=noise={threshold}dB:d={minimum}','-f','null','-'],capture_output=True,text=True,check=True,timeout=180)
    gaps=[];start=None
    for line in proc.stderr.splitlines():
        a=re.search(r'silence_start: ([\d.]+)',line);b=re.search(r'silence_end: ([\d.]+)',line)
        if a:start=float(a[1])
        if b and start is not None:
            if float(b[1])-padding>start+padding:gaps.append((start+padding,min(duration,float(b[1])-padding)))
            start=None
    if start is not None and duration>start+padding:gaps.append((start+padding,duration))
    keep=[];cursor=0
    for a,b in gaps:
        if a>cursor+.05:keep.append({'start':cursor,'end':a})
        cursor=max(cursor,b)
    if cursor<duration-.05:keep.append({'start':cursor,'end':duration})
    if len(keep)>200:raise ValueError('More than 200 retained ranges. Increase the minimum silence duration.')
    return keep,gaps

def render_edl(source,dest,edl,is_video,aspect,segments,subtitles):
    import tempfile
    from pathlib import Path
    from .media import render_variant,probe_output
    with tempfile.TemporaryDirectory(dir=Path(dest).parent) as folder:
        folder=Path(folder);files=[];mapped=[];offset=0
        for i,r in enumerate(edl):
            part=folder/f'part-{i}.mp4' if is_video else folder/f'part-{i}.m4a'
            args=['ffmpeg','-v','error','-y','-ss',str(r['start']),'-i',str(source),'-t',str(r['end']-r['start'])]
            args+=['-c:v','libx264','-preset','veryfast','-crf','28','-threads','2'] if is_video else ['-vn']
            subprocess.run(args+['-c:a','aac','-b:a','96k',str(part)],check=True,capture_output=True,timeout=600)
            files.append(f"file '{part.name}'")
            for s in segments:
                a=max(r['start'],s['start']);b=min(r['end'],s['end'])
                if b>a:mapped.append({'start':offset+a-r['start'],'end':offset+b-r['start'],'text':s['text']})
            offset+=r['end']-r['start']
        (folder/'list.txt').write_text('\n'.join(files))
        merged=folder/('merged.mp4' if is_video else 'merged.m4a')
        subprocess.run(['ffmpeg','-v','error','-y','-f','concat','-safe','1','-i',str(folder/'list.txt'),'-c','copy','-movflags','+faststart',str(merged)],capture_output=True,check=True,timeout=600)
        actual,_=probe_output(merged)
        if abs(actual-offset)>max(2,len(edl)*.07):raise ValueError('Silence edit duration does not match the retained timeline.')
        if is_video:render_variant(merged,dest,0,actual,True,'','Remove Silence',mapped,subtitles,aspect)
        else:merged.replace(dest)
