"""Runs only in a bounded subprocess. No shell commands, cookies or arbitrary URLs."""
import json
import math
import os
import shutil
import sys
from pathlib import Path
from .youtube import canonical_youtube_url,json3_segments,safe_download_error

def run(url,folder,language):
    from yt_dlp import YoutubeDL
    from .media import probe
    url=canonical_youtube_url(url);folder=Path(folder)
    limit=int(os.getenv('MAX_UPLOAD_MB','150'))*1024**2
    class Quiet:
        def debug(self,*args):pass
        def warning(self,*args):pass
        def error(self,*args):pass
    def progress(info):
        if info.get('downloaded_bytes',0)>limit:raise ValueError('size limit')
        total=sum(p.stat().st_size for p in folder.iterdir() if p.is_file())
        if total>limit*2.1:raise ValueError('size limit')
    opts={'quiet':True,'logger':Quiet(),'noplaylist':True,'cachedir':False,'socket_timeout':20,'retries':1,'fragment_retries':1,
          'js_runtimes':{'node':{}},'remote_components':set(),'allowed_extractors':['youtube'],'restrictfilenames':True,
          'max_filesize':limit,'concurrent_fragment_downloads':1,'progress_hooks':[progress],
          'outtmpl':str(folder/'source.%(ext)s'),'format':'bv[height<=720][ext=mp4]+ba[ext=m4a]/b[height<=720][ext=mp4]/b[height<=720]',
          'merge_output_format':'mp4','overwrites':True,'continuedl':False}
    with YoutubeDL(opts) as ydl:
        info=ydl.extract_info(url,download=False)
        duration=float(info.get('duration') or 0)
        if info.get('is_live') or info.get('live_status')=='is_upcoming' or not math.isfinite(duration) or not 0<duration<=int(os.getenv('MAX_DURATION_SECONDS','1800')):raise ValueError('duration limit')
        if info.get('has_drm'):raise ValueError('unavailable protected media')
        if info.get('filesize',0) and info['filesize']>limit:raise ValueError('size limit')
        downloaded=ydl.extract_info(url,download=True)
    media=next((p for p in folder.glob('source.*') if p.suffix in {'.mp4','.webm','.mkv'}),None)
    if not media or media.stat().st_size>limit:raise ValueError('size limit or no playable download')
    actual,kind=probe(media)
    captions=[];provenance='none';caption_language=None
    manual=info.get('subtitles') or {};automatic=info.get('automatic_captions') or {}
    for catalog,is_auto in [(manual,False),(automatic,True)]:
        choices=[k for k in catalog if k==language or k.startswith(language+'-')]
        if choices:
            caption_language=choices[0];provenance='youtube_auto_captions' if is_auto else 'youtube_captions';break
    if caption_language:
        try:
            subopts={**opts,'skip_download':True,'writesubtitles':provenance=='youtube_captions','writeautomaticsub':provenance=='youtube_auto_captions','subtitleslangs':[caption_language],'subtitlesformat':'json3','ignoreerrors':False}
            with YoutubeDL(subopts) as ydl:ydl.extract_info(url,download=True)
            subtitle=next(folder.glob('*.json3'),None)
            if subtitle and subtitle.stat().st_size<=2_000_000:captions=json3_segments(json.loads(subtitle.read_text(encoding='utf-8')),actual)
        except Exception:captions=[]
    result={'path':str(media.resolve()),'title':str(info.get('title') or 'YouTube source')[:200],'duration':actual,'kind':kind,'segments':captions,'transcript_source':provenance if captions else 'none','url':url}
    (folder/'result.json').write_text(json.dumps(result),encoding='utf-8')

if __name__=='__main__':
    try:run(*sys.argv[1:4])
    except Exception as ex:
        (Path(sys.argv[2])/'error.json').write_text(json.dumps({'error':safe_download_error(ex)}))
        sys.exit(1)
