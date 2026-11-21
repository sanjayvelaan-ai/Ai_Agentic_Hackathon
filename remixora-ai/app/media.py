"""Source-aligned transcription, heuristic candidate selection, and safe FFmpeg rendering."""
import gzip
import json
import math
import os
import re
import shutil
import stat
import subprocess
import threading
import urllib.request
from pathlib import Path

_ffmpeg_checked = False
_ffmpeg_lock = threading.Lock()

def ensure_ffmpeg():
    global _ffmpeg_checked
    if _ffmpeg_checked and shutil.which("ffmpeg") and shutil.which("ffprobe"):
        return True

    with _ffmpeg_lock:
        if shutil.which("ffmpeg") and shutil.which("ffprobe"):
            _ffmpeg_checked = True
            return True

        # 1. Check local tools folder (e.g. .tools/ffmpeg/**/bin)
        repo_root = Path(__file__).resolve().parent.parent
        for p in repo_root.glob(".tools/ffmpeg/**/bin"):
            if (p / ("ffmpeg.exe" if os.name == "nt" else "ffmpeg")).exists():
                if str(p) not in os.environ.get("PATH", ""):
                    os.environ["PATH"] = str(p) + os.pathsep + os.environ.get("PATH", "")
                if shutil.which("ffmpeg") and shutil.which("ffprobe"):
                    _ffmpeg_checked = True
                    return True

        # 2. Check /tmp/bin
        tmp_bin = Path("/tmp/bin") if os.name != "nt" else Path(os.environ.get("TEMP", "/tmp")) / "bin"
        tmp_bin.mkdir(parents=True, exist_ok=True)
        if str(tmp_bin) not in os.environ.get("PATH", ""):
            os.environ["PATH"] = str(tmp_bin) + os.pathsep + os.environ.get("PATH", "")

        ffmpeg_bin = tmp_bin / ("ffmpeg.exe" if os.name == "nt" else "ffmpeg")
        ffprobe_bin = tmp_bin / ("ffprobe.exe" if os.name == "nt" else "ffprobe")

        if ffmpeg_bin.exists() and ffprobe_bin.exists():
            _ffmpeg_checked = True
            return True

        # 3. Try static_ffmpeg package if installed
        try:
            import static_ffmpeg
            download_dir = str(tmp_bin)
            static_ffmpeg.add_paths(download_dir=download_dir)
            if shutil.which("ffmpeg") and shutil.which("ffprobe"):
                _ffmpeg_checked = True
                return True
        except Exception:
            pass

        # 4. On Linux (e.g. Vercel serverless / AWS Lambda): download static standalone binaries
        if os.name != "nt":
            base_url = "https://github.com/eugeneware/ffmpeg-static/releases/download/b6.0"
            for name, binary_path in [("ffmpeg", ffmpeg_bin), ("ffprobe", ffprobe_bin)]:
                if not binary_path.exists() or binary_path.stat().st_size < 1000:
                    url = f"{base_url}/{name}-linux-x64.gz"
                    temp_gz = tmp_bin / f"{name}.gz"
                    try:
                        urllib.request.urlretrieve(url, temp_gz)
                        with gzip.open(temp_gz, "rb") as f_in, open(binary_path, "wb") as f_out:
                            shutil.copyfileobj(f_in, f_out)
                        temp_gz.unlink(missing_ok=True)
                        binary_path.chmod(binary_path.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
                    except Exception as ex:
                        print(f"Failed downloading {name}: {ex}")

            if shutil.which("ffmpeg") and shutil.which("ffprobe"):
                _ffmpeg_checked = True
                return True

    return bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))

# Trigger background check on module load
threading.Thread(target=ensure_ffmpeg, daemon=True).start()

TIME_RE = re.compile(r"(?:(\d+):)?(\d+):(\d+)[,.](\d+)")



def time_seconds(value):
    m = TIME_RE.fullmatch(value.strip())
    if not m:
        raise ValueError(f"Invalid timestamp: {value}")
    h, minutes, seconds, frac = m.groups()
    if int(minutes) >= 60 or int(seconds) >= 60:
        raise ValueError('Timestamp minutes and seconds must be below 60')
    return int(h or 0)*3600 + int(minutes)*60 + int(seconds) + float('0.'+frac)


def parse_subtitles(text):
    """Parse basic SRT/VTT to exact time-aligned segments. Reject timestamp-free text."""
    text = text.replace('\r\n', '\n').replace('\r', '\n')
    items = []
    for block in re.split(r"\n\s*\n", text.strip()):
        lines = [x.strip() for x in block.splitlines() if x.strip()]
        found = next((i for i, line in enumerate(lines) if '-->' in line), None)
        if found is None:
            continue
        begin, end = [x.strip().split()[0] for x in lines[found].split('-->',1)]
        try:
            start, stop = time_seconds(begin), time_seconds(end)
        except (ValueError, IndexError) as ex:
            raise ValueError('Invalid subtitle timestamp') from ex
        body = re.sub(r'<[^>]*>', '', ' '.join(lines[found+1:])).strip()
        if 0 <= start < stop and body:
            items.append(dict(start=start, end=stop, text=body))
        else:
            raise ValueError('Subtitle cues must contain text and have increasing timestamps')
    if not items:
        raise ValueError('No valid timestamped captions. Please upload a .srt or .vtt file.')
    items.sort(key=lambda item: item['start'])
    if any(b['start'] < a['end'] for a,b in zip(items,items[1:])):
        raise ValueError('Overlapping subtitle cues must be repaired before import')
    return items


def probe(path):
    with Path(path).open('rb') as media_file:header=media_file.read(32)
    binary_media=(header[:4]==b'\x1aE\xdf\xa3' or (header[:4]==b'RIFF' and header[8:12]==b'WAVE') or header[:3]==b'ID3' or (len(header)>1 and header[0]==255 and header[1]&224==224) or header[4:8] in {b'ftyp',b'moov',b'mdat',b'free',b'wide'})
    if not binary_media:raise ValueError('File content is not a supported binary media container')
    proc = subprocess.run([
      'ffprobe','-v','error','-protocol_whitelist','file,pipe','-show_entries','format=duration,format_name:stream=codec_type,codec_name',
      '-of','json',str(path)], capture_output=True,text=True,timeout=20,check=True)
    data = json.loads(proc.stdout)
    duration = float(data['format']['duration'])
    kind = 'video' if any(s.get('codec_type') == 'video' for s in data.get('streams',[])) else 'audio'
    if not math.isfinite(duration) or duration <= 0 or duration > float(os.getenv('MAX_DURATION_SECONDS','1800')):
        raise ValueError('Media duration exceeds configured limit or is invalid.')
    if not any(s.get('codec_type')=='audio' for s in data.get('streams', [])):
        raise ValueError('Please upload a media file with an audio stream.')
    allowed={'h264','hevc','vp8','vp9','av1','mpeg4','mpeg2video','mjpeg','prores','aac','mp3','opus','vorbis','flac','alac','pcm_s16le','pcm_s24le','pcm_s32le','pcm_f32le','pcm_u8','wmav2'}
    if any(s.get('codec_name') not in allowed for s in data.get('streams',[]) if s.get('codec_type') in {'audio','video'}):
        raise ValueError('Unsupported media codec; convert to H.264/AAC or WAV')
    return duration, kind


def transcribe(path):
    backend=os.getenv('TRANSCRIPTION_BACKEND','none')
    if backend=='none':
        raise RuntimeError('Local transcription is disabled. Import a source-matched SRT or VTT.')
    if backend=='whisper.cpp':
        return transcribe_cpp(path)
    try:
        from faster_whisper import WhisperModel
    except ImportError as ex:
        raise RuntimeError('Transcription dependency not installed. Upload a matching .srt/.vtt transcript or install requirements-transcription.txt.') from ex
    model = WhisperModel(os.getenv('WHISPER_MODEL','tiny'), device='cpu',compute_type='int8', cpu_threads=2, local_files_only=True)
    segments, _ = model.transcribe(str(path), beam_size=1, vad_filter=True)
    output = [dict(start=float(s.start),end=float(s.end),text=s.text.strip()) for s in segments if s.end>s.start and s.text.strip()]
    if not output:
        raise RuntimeError('No intelligible speech detected; please supply a transcript.')
    return output


def candidates(segments, duration, count=3, target_seconds=24, maximum_seconds=60, objective='shorts'):
    """A labeled heuristic fallback; not represented as a prediction of virality."""
    if not segments:
        return []
    windows=[]
    for pos in range(len(segments)):
        start=segments[pos]['start']
        if start > duration - 8:
            break
        chosen=[]
        for segment in segments[pos:]:
            if segment['end']-start>maximum_seconds:
                break
            chosen.append(segment)
            if segment['end']-start>=target_seconds:
                break
        if not chosen:
            continue
        end=min(duration,chosen[-1]['end'])
        if end-start<15:
            continue
        quote=' '.join(s['text'] for s in chosen)
        words=quote.lower().split()
        signals=['how','why','mistake','learn','tip','because','lesson','first','three','important','instead']
        hits=sum(1 for word in signals if word in words)
        if objective=='informative':hits+=sum(word in words for word in ['example','explain','step','because','means'])
        score = min(5.0, 1.5+hits*.35 + min(len(words)/75,1.5) + (0.4 if '?' in quote else 0))
        windows.append(dict(start=start,end=end,quote=quote,score=round(score,2),
         title=re.split(r'(?<=[.!?])\s+',quote)[0][:110] or 'Interesting moment',
         reason=f"Contains {hits} useful language cues and a {round(end-start)}-second self-contained segment. Review context before publishing.",source='heuristic'))
    windows.sort(key=lambda x:x['score'],reverse=True)
    selected=[]
    for item in windows:
        if all(min(item['end'],x['end'])-max(item['start'],x['start']) < 0.3*min(item['end']-item['start'], x['end']-x['start']) for x in selected):
            selected.append(item)
        if len(selected)>=count:break
    return selected


def render(source, dest, start, end, is_video):
    if start < 0 or end <= start:
        raise ValueError('Invalid clip timestamps')
    args=['ffmpeg','-hide_banner','-loglevel','error','-y','-ss',str(start),'-i',str(source),'-t',str(end-start)]
    if is_video:
        args+=['-vf','scale=720:1280:force_original_aspect_ratio=decrease,pad=720:1280:(ow-iw)/2:(oh-ih)/2,setsar=1','-c:v','libx264','-preset','veryfast','-crf','28','-threads','2','-c:a','aac','-b:a','96k','-movflags','+faststart',str(dest)]
    else:
        args+=['-vn','-c:a','aac','-b:a','96k',str(dest)]
    subprocess.run(args,check=True,capture_output=True,text=True,timeout=int(os.getenv('FFMPEG_TIMEOUT_SECONDS','600')))
    if not Path(dest).is_file() or Path(dest).stat().st_size < 500:
        raise RuntimeError('FFmpeg did not produce a valid export.')
    _duration,_kind=probe_output(dest)
    if abs(_duration-(end-start))>3:
        raise RuntimeError('Export duration differs materially from requested clip.')


def probe_output(path):
    proc=subprocess.run(['ffprobe','-v','error','-show_entries','format=duration:stream=codec_type','-of','json',str(path)],capture_output=True,text=True,timeout=15,check=True)
    d=json.loads(proc.stdout)
    return float(d['format']['duration']), 'video' if any(s.get('codec_type')=='video' for s in d.get('streams',[])) else 'audio'


def generate_thumbnail(media_path, thumb_path, timestamp=1.0):
    """Safely extract a single preview frame as JPEG from a video file."""
    try:
        media_path = Path(media_path)
        thumb_path = Path(thumb_path)
        if not media_path.is_file():
            return None
        thumb_path.parent.mkdir(parents=True, exist_ok=True)
        # Verify media has video stream
        proc = subprocess.run([
            'ffprobe', '-v', 'error', '-show_entries', 'stream=codec_type', '-of', 'json', str(media_path)
        ], capture_output=True, text=True, timeout=10)
        data = json.loads(proc.stdout)
        has_video = any(s.get('codec_type') == 'video' for s in data.get('streams', []))
        if not has_video:
            return None
        args = [
            'ffmpeg', '-hide_banner', '-loglevel', 'error', '-y',
            '-ss', str(max(0.1, timestamp)), '-i', str(media_path),
            '-vframes', '1', '-q:v', '2',
            '-vf', 'scale=480:-1',
            str(thumb_path)
        ]
        subprocess.run(args, capture_output=True, text=True, timeout=15, check=True)
        if thumb_path.is_file() and thumb_path.stat().st_size > 100:
            return str(thumb_path)
    except Exception:
        pass
    return None


def classify_angle(quote):
    """Simple content-role classifier for deterministic feedback-based re-ranking."""
    q=quote.lower()
    educational=sum(term in q for term in ['how','why','step','tip','lesson','first','learn','because'])
    challenge=sum(term in q for term in ['mistake','wrong','instead','however','but','myth','actually'])
    story=sum(term in q for term in ['when i','we were','i felt','one day','my experience','then i','once'])
    if challenge>max(educational,story):return 'Challenge It'
    if story>educational:return 'Tell It'
    return 'Teach It'


def transcribe_cpp(path):
    import tempfile
    executable=os.getenv('WHISPER_CPP_BIN','whisper-cli')
    model=os.getenv('WHISPER_CPP_MODEL','')
    if not model or not Path(model).is_file():
        raise RuntimeError('Configure a pre-downloaded whisper.cpp model or import subtitles')
    with tempfile.TemporaryDirectory() as folder:
        wav=Path(folder)/'audio.wav'
        subprocess.run(['ffmpeg','-v','error','-y','-i',str(path),'-ar','16000','-ac','1',str(wav)],check=True,capture_output=True,timeout=300)
        subprocess.run([executable,'-m',model,'-f',str(wav),'-t','2','-osrt','-of',str(Path(folder)/'transcript')],check=True,capture_output=True,timeout=1200)
        return parse_subtitles((Path(folder)/'transcript.srt').read_text(encoding='utf-8'))


def render_variant(source,dest,start,end,is_video,headline,angle,segments,subtitles=True,aspect_ratio='9:16'):
    """Distinct opening cards and source-aligned ASS captions, CPU-only FFmpeg."""
    import tempfile
    import textwrap
    if not (0 <= start < end):raise ValueError('Invalid clip boundaries')
    def ass_time(t):
        cs=round(max(0,t)*100)
        return f'{cs//360000}:{cs//6000%60:02}:{cs//100%60:02}.{cs%100:02}'
    def safe(text):
        return text.replace('\\','/').replace('{','(').replace('}',')').replace('\n',' ')
    header='''[Script Info]
ScriptType: v4.00+
PlayResX: 720
PlayResY: 1280
[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Head,Arial,43,&H00FFFFFF,&H00FFFFFF,&H00251B18,&H00251B18,-1,0,0,0,100,100,0,0,3,16,0,8,50,50,130,1
Style: Sub,Arial,32,&H00FFFFFF,&H00FFFFFF,&H00201913,&H00201913,-1,0,0,0,100,100,0,0,3,8,0,2,45,45,200,1
Style: Brand,Arial,22,&H00E3F3A3,&H00FFFFFF,&H00201913,&H00201913,0,0,0,0,100,100,2,0,1,1,0,8,30,30,55,1
[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
'''
    width,height={'9:16':(720,1280),'1:1':(720,720),'16:9':(1280,720)}[aspect_ratio]
    header=header.replace('PlayResX: 720',f'PlayResX: {width}').replace('PlayResY: 1280',f'PlayResY: {height}')
    if height==720:header=header.replace(',45,45,200,1',',45,45,60,1')
    lines=[f'Dialogue: 0,0:00:00.00,{ass_time(end-start)},Brand,,0,0,0,,REMIXORA / {safe(angle).upper()}']
    wrapped='\\N'.join(textwrap.wrap(safe(headline),28)[:4])
    lines.append(f'Dialogue: 1,0:00:00.00,{ass_time(min(5,end-start))},Head,,0,0,0,,{wrapped}')
    if subtitles:
        for segment in segments:
            a=max(start,segment['start']);b=min(end,segment['end'])
            if a>=b:continue
            chunks=textwrap.wrap(safe(segment['text']),65)
            for i,chunk in enumerate(chunks):
                t0=a-start+(b-a)*i/len(chunks);t1=a-start+(b-a)*(i+1)/len(chunks)
                lines.append(f'Dialogue: 2,{ass_time(t0)},{ass_time(t1)},Sub,,0,0,0,,{chunk}')
    with tempfile.TemporaryDirectory(dir=Path(dest).parent) as folder:
        (Path(folder)/'captions.ass').write_text(header+'\n'.join(lines),encoding='utf-8')
        args=['ffmpeg','-hide_banner','-loglevel','error','-y']
        if is_video:args+=['-ss',str(start),'-i',str(Path(source).resolve())]
        else:args+=['-f','lavfi','-i','color=c=0x141625:s=720x1280:r=24','-ss',str(start),'-i',str(Path(source).resolve()),'-map','0:v','-map','1:a']
        filt=f'scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=0x101321,setsar=1,ass=captions.ass'
        temp=Path(folder)/'output.mp4'
        args+=['-t',str(end-start),'-vf',filt,'-r','24','-c:v','libx264','-preset','veryfast','-crf','28','-threads','2','-c:a','aac','-b:a','96k','-movflags','+faststart',str(temp.resolve())]
        subprocess.run(args,cwd=folder,check=True,capture_output=True,timeout=int(os.getenv('FFMPEG_TIMEOUT_SECONDS','600')))
        actual,_=probe_output(temp)
        if abs(actual-(end-start))>2:raise ValueError('Export duration validation failed')
        temp.replace(dest)
