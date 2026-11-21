"""Explicit one-time model setup. Nothing is downloaded during an upload."""
import os
from pathlib import Path
root=Path(__file__).resolve().parents[1]
os.environ['HF_HOME']=str(root/'.models'/'cache')
os.environ['HF_HUB_DISABLE_TELEMETRY']='1'
from huggingface_hub import snapshot_download
from faster_whisper import WhisperModel
path=snapshot_download('Systran/faster-whisper-tiny',local_dir=str(root/'.models'/'whisper-tiny'),allow_patterns=['config.json','model.bin','tokenizer.json','vocabulary.*'],max_workers=2)
model=WhisperModel(path,device='cpu',compute_type='int8',cpu_threads=2,local_files_only=True)
config=root/'.env.local'
if config.exists():
    from dotenv import set_key
    set_key(config,'TRANSCRIPTION_BACKEND','faster-whisper')
    set_key(config,'WHISPER_MODEL',str(Path(path).resolve()).replace('\\','/'))
else:config.write_text('AI_PROVIDER=none\nTRANSCRIPTION_BACKEND=faster-whisper\nWHISPER_MODEL='+str(Path(path).resolve()).replace('\\','/')+'\n')
print('Local CPU speech model installed and configured. Restart REMIXORA to enable it.')
