"""Assemble original Windows TTS narration with exact per-paragraph subtitle timing."""
import json
import subprocess
from pathlib import Path

root=Path(__file__).resolve().parents[1];demo=root/'demo'
paragraphs=json.loads((demo/'narration.json').read_text(encoding='utf-8-sig'))
def ts(seconds):
    ms=round(seconds*1000)
    return f'{ms//3600000:02}:{ms//60000%60:02}:{ms//1000%60:02},{ms%1000:03}'
subtitles=[];elapsed=0;concat=[]
for i,text in enumerate(paragraphs):
    path=demo/f'part-{i:02}.wav'
    duration=float(subprocess.check_output(['ffprobe','-v','error','-show_entries','format=duration','-of','default=nw=1:nk=1',str(path)]))
    subtitles.append(f'{i+1}\n{ts(elapsed)} --> {ts(elapsed+duration)}\n{text}')
    elapsed+=duration;concat.append(f"file '{path.name}'")
(demo/'source.srt').write_text('\n\n'.join(subtitles),encoding='utf-8')
(demo/'concat.txt').write_text('\n'.join(concat))
subprocess.run(['ffmpeg','-v','error','-y','-f','concat','-safe','0','-i',str(demo/'concat.txt'),'-c:a','pcm_s16le',str(demo/'narration.wav')],check=True)
(demo/'title.txt').write_text('REMIXORA\nThoughtful content, reimagined\n\nORIGINAL SCRIPT / SYNTHETIC NARRATION',encoding='utf-8')
subprocess.run(['ffmpeg','-v','error','-y','-f','lavfi','-i','color=c=0x1b2034:s=1280x720:r=12','-i','narration.wav','-vf',"drawtext=textfile=title.txt:fontcolor=0xc7b7f4:fontsize=38:line_spacing=24:x=(w-text_w)/2:y=(h-text_h)/2",'-c:v','libx264','-preset','ultrafast','-crf','28','-c:a','aac','-b:a','96k','-shortest','-movflags','+faststart','original-demo.mp4'],cwd=demo,check=True)
print(json.dumps({'source':str(demo/'original-demo.mp4'),'duration_seconds':round(elapsed,2),'segments':len(paragraphs),'synthetic_narration':True}))
