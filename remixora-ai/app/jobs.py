"""A SQLite-backed single worker; interrupted jobs are resumed at startup."""
import json
import threading
import uuid
from .db import db

class DurableWorker:
    def __init__(self, handler):
        self.handler=handler
        self.stop=threading.Event()
        self.thread=None

    def start(self):
        with db() as c:
            interrupted=c.execute("SELECT kind,target_id,attempts FROM jobs WHERE status='running' AND kind IN ('preset_analyze','preset_render')").fetchall()
            c.execute("UPDATE jobs SET status=CASE WHEN attempts<3 THEN 'queued' ELSE 'failed' END,error='Interrupted; recovered on startup' WHERE status='running'")
            for row in interrupted:
                status='queued' if row['attempts']<3 else 'failed'
                error=None if status=='queued' else 'Processing was interrupted three times. Start a new analysis or render.'
                if row['kind']=='preset_analyze':
                    c.execute("UPDATE preset_runs SET status=?,error=? WHERE id=? AND status NOT IN ('ready','no_matches','unsupported')",(status,error,row['target_id']))
                else:
                    c.execute("UPDATE preset_candidates SET render_status=?,error=? WHERE id=? AND render_status!='rendered'",(status,error,row['target_id']))
        self.stop.clear()
        self.thread=threading.Thread(target=self.run,daemon=True,name='remixora-media-worker')
        self.thread.start()

    def close(self):
        self.stop.set()
        if self.thread:self.thread.join(timeout=610)

    def run(self):
        while not self.stop.is_set():
            with db() as c:
                c.execute('BEGIN IMMEDIATE')
                row=c.execute("SELECT * FROM jobs WHERE status='queued' ORDER BY created_at,rowid LIMIT 1").fetchone()
                if row:
                    c.execute("UPDATE jobs SET status='running',attempts=attempts+1,error=NULL,updated_at=CURRENT_TIMESTAMP WHERE id=?",(row['id'],))
            if not row:
                self.stop.wait(.3)
                continue
            try:
                self.handler(dict(row),json.loads(row['payload']))
                with db() as c:c.execute("UPDATE jobs SET status='completed',updated_at=CURRENT_TIMESTAMP WHERE id=?",(row['id'],))
            except Exception as ex:
                # Do not store subprocess command lines, API keys or transcript text.
                message=str(ex)[:240] if isinstance(ex,ValueError) else 'Processing failed. Check local tools and retry; '+type(ex).__name__
                with db() as c:
                    c.execute("UPDATE jobs SET status='failed',error=?,updated_at=CURRENT_TIMESTAMP WHERE id=?",(message,row['id']))
                    if row['kind']=='preset_analyze':c.execute("UPDATE preset_runs SET status='failed',error=? WHERE id=?",(message,row['target_id']))
                    elif row['kind']=='preset_render':c.execute("UPDATE preset_candidates SET render_status='failed',error=? WHERE id=?",(message,row['target_id']))
                    elif row['kind']=='ingest':c.execute("UPDATE assets SET status='failed',error=? WHERE id=?",(message,row['target_id']))
                    elif row['kind']=='variant':c.execute("UPDATE variants SET status='failed',error=? WHERE id=?",(message,row['target_id']))
                    elif row['kind']=='render':c.execute("UPDATE clips SET render_status='failed' WHERE id=?",(row['target_id'],))
                    elif row['kind']=='workflow':c.execute("UPDATE workflows SET stage='failed',error=?,message='Fix the issue and retry this workflow',updated_at=CURRENT_TIMESTAMP WHERE id=?",(message,row['target_id']))

def enqueue(kind,target_id,payload=None,connection=None):
    if connection is None:
        with db() as c:
            c.execute('BEGIN IMMEDIATE')
            return enqueue(kind,target_id,payload,connection=c)
    existing=connection.execute("SELECT id FROM jobs WHERE kind=? AND target_id=? AND status IN ('queued','running')",(kind,target_id)).fetchone()
    if existing:return existing['id']
    job_id=uuid.uuid4().hex
    connection.execute('INSERT INTO jobs(id,kind,target_id,payload) VALUES (?,?,?,?)',(job_id,kind,target_id,json.dumps(payload or {})))
    return job_id
