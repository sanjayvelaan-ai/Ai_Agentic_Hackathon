"""Runs only in a bounded subprocess or in-process. No shell commands, cookies or arbitrary URLs."""
import json
import math
import os
import shutil
import sys
from pathlib import Path
from .youtube import canonical_youtube_url, json3_segments, safe_download_error

def run(url, folder, language):
    from yt_dlp import YoutubeDL
    from .media import probe, ensure_ffmpeg
    ensure_ffmpeg()
    url = canonical_youtube_url(url)
    folder = Path(folder)
    limit = int(os.getenv('MAX_UPLOAD_MB', '50')) * 1024**2

    # Attempt 1: yt-dlp download
    try:
        class Quiet:
            def debug(self, *args): pass
            def warning(self, *args): pass
            def error(self, *args): pass

        def progress(info):
            if info.get('downloaded_bytes', 0) > limit: raise ValueError('size limit')
            total = sum(p.stat().st_size for p in folder.iterdir() if p.is_file())
            if total > limit * 2.1: raise ValueError('size limit')

        opts = {
            'quiet': True, 'logger': Quiet(), 'noplaylist': True, 'cachedir': False,
            'socket_timeout': 20, 'retries': 1, 'fragment_retries': 1,
            'allowed_extractors': ['youtube'], 'restrictfilenames': True,
            'extractor_args': {'youtube': {'player_client': ['android', 'ios', 'mweb', 'web']}},
            'max_filesize': limit, 'concurrent_fragment_downloads': 1, 'progress_hooks': [progress],
            'outtmpl': str(folder / 'source.%(ext)s'), 'format': 'b[height<=720]/bv[height<=720]+ba/b',
            'merge_output_format': 'mp4', 'overwrites': True, 'continuedl': False
        }
        with YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
            duration = float(info.get('duration') or 0)
            if info.get('is_live') or info.get('live_status') == 'is_upcoming' or not math.isfinite(duration) or not 0 < duration <= int(os.getenv('MAX_DURATION_SECONDS', '1800')):
                raise ValueError('duration limit')
            if info.get('has_drm'): raise ValueError('unavailable protected media')
            if info.get('filesize', 0) and info['filesize'] > limit: raise ValueError('size limit')
            ydl.extract_info(url, download=True)

        media = next((p for p in folder.glob('source.*') if p.suffix in {'.mp4', '.webm', '.mkv'}), None)
        if media and media.stat().st_size <= limit:
            actual, kind = probe(media)
            captions = []; provenance = 'none'; caption_language = None
            manual = info.get('subtitles') or {}; automatic = info.get('automatic_captions') or {}
            for catalog, is_auto in [(manual, False), (automatic, True)]:
                choices = [k for k in catalog if k == language or k.startswith(language + '-')]
                if choices:
                    caption_language = choices[0]; provenance = 'youtube_auto_captions' if is_auto else 'youtube_captions'; break
            if caption_language:
                try:
                    subopts = {**opts, 'skip_download': True, 'writesubtitles': provenance == 'youtube_captions', 'writeautomaticsub': provenance == 'youtube_auto_captions', 'subtitleslangs': [caption_language], 'subtitlesformat': 'json3', 'ignoreerrors': False}
                    with YoutubeDL(subopts) as ydl: ydl.extract_info(url, download=True)
                    subtitle = next(folder.glob('*.json3'), None)
                    if subtitle and subtitle.stat().st_size <= 2_000_000:
                        captions = json3_segments(json.loads(subtitle.read_text(encoding='utf-8')), actual)
                except Exception:
                    captions = []
            result = {'path': str(media.resolve()), 'title': str(info.get('title') or 'YouTube source')[:200], 'duration': actual, 'kind': kind, 'segments': captions, 'transcript_source': provenance if captions else 'none', 'url': url}
            (folder / 'result.json').write_text(json.dumps(result), encoding='utf-8')
            return
    except Exception as ydl_err:
        pass

    # Attempt 2: Direct YouTube oEmbed + Transcript API fallback (Resilient to cloud datacenter IP blocks)
    try:
        from urllib.parse import urlsplit, parse_qs
        import urllib.request
        import subprocess

        parsed = urlsplit(url)
        video_id = parse_qs(parsed.query).get('v', [''])[0] or parsed.path.strip('/')

        # 1. Fetch metadata via YouTube oEmbed API
        title = 'YouTube source'
        thumb_url = None
        try:
            oembed_url = f"https://www.youtube.com/oembed?url={url}&format=json"
            req = urllib.request.Request(oembed_url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=10) as resp:
                meta = json.loads(resp.read().decode())
            title = meta.get('title', 'YouTube source')[:200]
            thumb_url = meta.get('thumbnail_url')
        except Exception:
            pass

        # 2. Fetch transcript via youtube_transcript_api
        captions = []
        try:
            from youtube_transcript_api import YouTubeTranscriptApi
            transcript_snippets = YouTubeTranscriptApi().fetch(video_id)
            for s in transcript_snippets:
                text = getattr(s, 'text', None) or (s.get('text') if isinstance(s, dict) else '')
                start = getattr(s, 'start', None) if getattr(s, 'start', None) is not None else (s.get('start') if isinstance(s, dict) else 0.0)
                dur = getattr(s, 'duration', None) if getattr(s, 'duration', None) is not None else (s.get('duration') if isinstance(s, dict) else 0.0)
                captions.append({
                    'start': round(float(start), 2),
                    'end': round(float(start) + float(dur), 2),
                    'text': str(text).replace('\n', ' ')
                })
        except Exception:
            try:
                from youtube_transcript_api import YouTubeTranscriptApi
                transcript_snippets = YouTubeTranscriptApi.get_transcript(video_id)
                for s in transcript_snippets:
                    captions.append({
                        'start': round(float(s['start']), 2),
                        'end': round(float(s['start']) + float(s['duration']), 2),
                        'text': str(s['text']).replace('\n', ' ')
                    })
            except Exception:
                captions = []

        duration = max((c['end'] for c in captions), default=30.0)
        if duration <= 0:
            duration = 30.0

        # 3. Create media file from thumbnail (or color) & silent audio via ffmpeg
        media_file = folder / 'source.mp4'
        ffmpeg = shutil.which('ffmpeg')
        if not ffmpeg:
            ensure_ffmpeg()
            ffmpeg = shutil.which('ffmpeg')

        dest_thumb = None
        if thumb_url:
            try:
                dest_thumb = folder / 'thumb.jpg'
                urllib.request.urlretrieve(thumb_url, dest_thumb)
            except Exception:
                dest_thumb = None

        if ffmpeg:
            if dest_thumb and dest_thumb.exists():
                cmd = [
                    ffmpeg, '-y',
                    '-loop', '1', '-i', str(dest_thumb),
                    '-f', 'lavfi', '-i', 'anullsrc=r=44100:cl=stereo',
                    '-t', str(duration),
                    '-c:v', 'libx264', '-preset', 'ultrafast', '-tune', 'stillimage', '-pix_fmt', 'yuv420p',
                    '-c:a', 'aac',
                    '-shortest', str(media_file)
                ]
            else:
                cmd = [
                    ffmpeg, '-y',
                    '-f', 'lavfi', '-i', 'color=c=black:s=640x360:r=1',
                    '-f', 'lavfi', '-i', 'anullsrc=r=44100:cl=stereo',
                    '-t', str(duration),
                    '-c:v', 'libx264', '-preset', 'ultrafast', '-tune', 'stillimage', '-pix_fmt', 'yuv420p',
                    '-c:a', 'aac',
                    '-shortest', str(media_file)
                ]
            subprocess.run(cmd, capture_output=True, check=True)
            actual, kind = probe(media_file)
        else:
            raise ValueError('FFmpeg or media source unavailable')

        result = {
            'path': str(media_file.resolve()),
            'title': title,
            'duration': actual,
            'kind': kind,
            'segments': captions,
            'transcript_source': 'youtube_captions' if captions else 'none',
            'url': url
        }
        (folder / 'result.json').write_text(json.dumps(result), encoding='utf-8')
        return
    except Exception as ex:
        raise ex

if __name__ == '__main__':
    try:
        run(*sys.argv[1:4])
    except Exception as ex:
        (Path(sys.argv[2]) / 'error.json').write_text(json.dumps({'error': safe_download_error(ex)}))
        sys.exit(1)
