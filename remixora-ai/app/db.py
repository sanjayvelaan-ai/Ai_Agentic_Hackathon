import os
import shutil
import sqlite3
from contextlib import contextmanager, closing
from pathlib import Path

DATA_DIR = Path(os.getenv("DATA_DIR", "./data")).resolve()
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_FILE = DATA_DIR / "remixora.sqlite3"

# Structured project storage root
STORAGE_DIR = DATA_DIR / "storage"
PROJECTS_DIR = STORAGE_DIR / "projects"
PROJECTS_DIR.mkdir(parents=True, exist_ok=True)


def project_paths(project_id: str) -> dict[str, Path]:
    """Return isolated storage directories for a project."""
    base = PROJECTS_DIR / project_id
    paths = {
        "root": base,
        "sources": base / "sources",
        "thumbnails": base / "thumbnails",
        "transcripts": base / "transcripts",
        "preset_runs": base / "preset-runs",
        "renders": base / "renders",
        "exports": base / "exports",
        "temp": base / "temp",
    }
    for p in paths.values():
        p.mkdir(parents=True, exist_ok=True)
    return paths


SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS projects (
  id TEXT PRIMARY KEY,
  owner_id TEXT,
  title TEXT NOT NULL,
  thumbnail_path TEXT,
  status TEXT NOT NULL DEFAULT 'ready',
  source_type TEXT NOT NULL DEFAULT 'upload',
  duration REAL NOT NULL DEFAULT 0,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS media_sources (
  id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  source_type TEXT NOT NULL,
  original_name TEXT NOT NULL,
  source_url TEXT,
  storage_path TEXT NOT NULL,
  duration REAL NOT NULL DEFAULT 0,
  media_type TEXT NOT NULL DEFAULT 'video',
  status TEXT NOT NULL DEFAULT 'ready',
  created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS clip_candidates (
  id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  preset_run_id TEXT,
  clip_id TEXT,
  start_time REAL NOT NULL,
  end_time REAL NOT NULL,
  title TEXT NOT NULL,
  score REAL NOT NULL DEFAULT 0,
  selection_reason TEXT NOT NULL,
  source_evidence TEXT NOT NULL DEFAULT '{}',
  status TEXT NOT NULL DEFAULT 'proposed',
  edl_json TEXT DEFAULT '[]',
  created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS rendered_clips (
  id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  candidate_id TEXT,
  preset_run_id TEXT,
  clip_id TEXT,
  title TEXT,
  file_path TEXT NOT NULL,
  thumbnail_path TEXT,
  duration REAL NOT NULL DEFAULT 0,
  aspect_ratio TEXT NOT NULL DEFAULT '9:16',
  status TEXT NOT NULL DEFAULT 'rendered',
  error TEXT,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_projects_updated ON projects(updated_at);
CREATE INDEX IF NOT EXISTS ix_media_sources_project ON media_sources(project_id);
CREATE INDEX IF NOT EXISTS ix_clip_candidates_project ON clip_candidates(project_id);
CREATE INDEX IF NOT EXISTS ix_clip_candidates_run ON clip_candidates(preset_run_id);
CREATE INDEX IF NOT EXISTS ix_rendered_clips_project ON rendered_clips(project_id);

CREATE TABLE IF NOT EXISTS assets (
 id TEXT PRIMARY KEY, filename TEXT NOT NULL, media_path TEXT NOT NULL,
 media_kind TEXT NOT NULL, duration REAL NOT NULL, status TEXT NOT NULL,
 error TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS segments (
 id INTEGER PRIMARY KEY AUTOINCREMENT, asset_id TEXT NOT NULL REFERENCES assets(id),
 start REAL NOT NULL, end REAL NOT NULL, text TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS clips (
 id TEXT PRIMARY KEY, asset_id TEXT NOT NULL REFERENCES assets(id),
 start REAL NOT NULL, end REAL NOT NULL, title TEXT NOT NULL,
 reason TEXT NOT NULL, quote TEXT NOT NULL, score REAL NOT NULL,
 source TEXT NOT NULL, suggested_angle TEXT NOT NULL DEFAULT 'Teach It', output_path TEXT, render_status TEXT DEFAULT 'not_rendered'
);
CREATE TABLE IF NOT EXISTS copies (
 id TEXT PRIMARY KEY, clip_id TEXT NOT NULL REFERENCES clips(id), platform TEXT NOT NULL,
 angle TEXT NOT NULL, content TEXT NOT NULL, source TEXT NOT NULL,
 updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS edits (
 id TEXT PRIMARY KEY, copy_id TEXT NOT NULL REFERENCES copies(id),
 original TEXT NOT NULL, revised TEXT NOT NULL, created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS brand_rules (
 id TEXT PRIMARY KEY, text TEXT NOT NULL, evidence_edit_id TEXT REFERENCES edits(id),
 status TEXT NOT NULL DEFAULT 'pending', created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS calendar (
 id TEXT PRIMARY KEY, copy_id TEXT NOT NULL REFERENCES copies(id),
 scheduled_at TEXT NOT NULL, timezone TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'scheduled_in_app'
);
CREATE TABLE IF NOT EXISTS metrics (
 id INTEGER PRIMARY KEY AUTOINCREMENT, clip_id TEXT NOT NULL REFERENCES clips(id),
 platform TEXT NOT NULL, angle TEXT NOT NULL, impressions INTEGER, likes INTEGER NOT NULL,
 comments INTEGER NOT NULL, shares INTEGER NOT NULL, saves INTEGER NOT NULL, source TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS agent_events (
 id INTEGER PRIMARY KEY AUTOINCREMENT, asset_id TEXT, agent TEXT NOT NULL,
 action TEXT NOT NULL, result TEXT NOT NULL, created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS ix_segments_asset ON segments(asset_id);
CREATE INDEX IF NOT EXISTS ix_clips_asset ON clips(asset_id);
CREATE INDEX IF NOT EXISTS ix_metrics_platform_angle ON metrics(platform, angle);
"""


def init_db():
    # Make safe backup of DB file if it exists and backup does not exist yet
    if DB_FILE.is_file():
        bak = DB_FILE.with_suffix(".sqlite3.bak")
        if not bak.is_file():
            try:
                shutil.copy2(DB_FILE, bak)
            except Exception:
                pass

    with closing(sqlite3.connect(DB_FILE)) as conn:
        with conn:
            conn.executescript(SCHEMA)
            migrate(conn)


def migrate(conn):
    """Additive migrations preserve existing starter records, projects, and exports."""
    additions = {
        'projects': {'source_type': "TEXT DEFAULT 'upload'", 'duration': 'REAL DEFAULT 0'},
        'assets': {'project_id': 'TEXT', 'checksum': 'TEXT', 'probe_json': "TEXT DEFAULT '{}'", 'source_url': 'TEXT', 'transcript_source': "TEXT DEFAULT 'imported_or_local'"},
        'clips': {'project_id': 'TEXT', 'preset_id': 'TEXT', 'evidence': "TEXT DEFAULT '[]'", 'rubric': "TEXT DEFAULT '{}'", 'base_score': 'REAL DEFAULT 0', 'adjustment': 'REAL DEFAULT 0', 'performance_revision': 'INTEGER DEFAULT 0'},
        'workflows': {'project_id': 'TEXT'},
        'preset_runs': {'project_id': 'TEXT'},
        'copies': {'approved': 'INTEGER DEFAULT 0', 'rules_used': "TEXT DEFAULT '[]'", 'brand_revision': 'INTEGER DEFAULT 0'},
        'edits': {'diff': "TEXT DEFAULT ''"},
        'calendar': {'caption': "TEXT DEFAULT ''", 'utc_at': "TEXT DEFAULT ''"},
        'metrics': {'views': 'INTEGER DEFAULT 0', 'published_at': 'TEXT', 'period': "TEXT DEFAULT 'lifetime'", 'fingerprint': 'TEXT', 'watch_time': 'REAL'},
    }
    all_tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    for table, columns in additions.items():
        if table not in all_tables:
            continue
        existing = {r[1] for r in conn.execute(f'PRAGMA table_info({table})')}
        for name, definition in columns.items():
            if name not in existing:
                conn.execute(f'ALTER TABLE {table} ADD COLUMN {name} {definition}')

    conn.executescript('''
    CREATE TABLE IF NOT EXISTS revisions (name TEXT PRIMARY KEY, value INTEGER NOT NULL DEFAULT 0);
    INSERT OR IGNORE INTO revisions VALUES ('brand',0),('performance',0);
    CREATE TABLE IF NOT EXISTS profile (id INTEGER PRIMARY KEY CHECK(id=1), content TEXT NOT NULL);
    INSERT OR IGNORE INTO profile VALUES (1,'{}');
    CREATE TABLE IF NOT EXISTS jobs (
      id TEXT PRIMARY KEY, kind TEXT NOT NULL, target_id TEXT NOT NULL, payload TEXT NOT NULL,
      status TEXT NOT NULL DEFAULT 'queued', attempts INTEGER NOT NULL DEFAULT 0,
      error TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP, updated_at TEXT DEFAULT CURRENT_TIMESTAMP);
    CREATE UNIQUE INDEX IF NOT EXISTS ix_jobs_active ON jobs(kind,target_id) WHERE status IN ('queued','running');
    CREATE TABLE IF NOT EXISTS variants (
      id TEXT PRIMARY KEY, clip_id TEXT NOT NULL REFERENCES clips(id), angle TEXT NOT NULL,
      headline TEXT NOT NULL, subtitles INTEGER NOT NULL, status TEXT DEFAULT 'queued', output_path TEXT,
      error TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP, UNIQUE(clip_id,angle,headline,subtitles));
    CREATE TABLE IF NOT EXISTS provider_cache (key TEXT PRIMARY KEY, content TEXT NOT NULL, provider TEXT NOT NULL, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE IF NOT EXISTS workflows (
      id TEXT PRIMARY KEY, asset_id TEXT REFERENCES assets(id), project_id TEXT, source_url TEXT,
      options TEXT NOT NULL, stage TEXT NOT NULL DEFAULT 'queued', progress INTEGER NOT NULL DEFAULT 0,
      message TEXT NOT NULL DEFAULT 'Waiting for the media worker', error TEXT,
      created_at TEXT DEFAULT CURRENT_TIMESTAMP, updated_at TEXT DEFAULT CURRENT_TIMESTAMP);
    CREATE UNIQUE INDEX IF NOT EXISTS ix_workflow_asset ON workflows(asset_id) WHERE asset_id IS NOT NULL;
    CREATE UNIQUE INDEX IF NOT EXISTS ix_metrics_fingerprint ON metrics(fingerprint);
    PRAGMA user_version=4;
    ''')

    from .presets import migrate as migrate_presets
    migrate_presets(conn)

    # Backfill projects from existing assets
    existing_projects = {r[0] for r in conn.execute("SELECT id FROM projects")}
    for row in conn.execute("SELECT id, filename, media_path, media_kind, duration, status, source_url, created_at FROM assets"):
        aid = row[0]
        if aid not in existing_projects:
            title = row[1] or "Untitled Project"
            src_type = "youtube" if row[6] else "upload"
            dur = float(row[4] or 0)
            conn.execute(
                "INSERT OR IGNORE INTO projects (id, title, thumbnail_path, status, source_type, duration, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?)",
                (aid, title, None, row[5] or 'ready', src_type, dur, row[7], row[7])
            )
            conn.execute(
                "INSERT OR IGNORE INTO media_sources (id, project_id, source_type, original_name, source_url, storage_path, duration, media_type, status, created_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (aid, aid, src_type, row[1], row[6], row[2], dur, row[3], row[5], row[7])
            )
            existing_projects.add(aid)

    # Link project_id across existing records
    conn.execute("UPDATE assets SET project_id = id WHERE project_id IS NULL")
    conn.execute("UPDATE clips SET project_id = asset_id WHERE project_id IS NULL")
    conn.execute("UPDATE workflows SET project_id = asset_id WHERE project_id IS NULL AND asset_id IS NOT NULL")

    # Check if preset_runs has project_id column
    pr_cols = {r[1] for r in conn.execute("PRAGMA table_info(preset_runs)")}
    if 'project_id' not in pr_cols:
        conn.execute("ALTER TABLE preset_runs ADD COLUMN project_id TEXT")
    conn.execute("UPDATE preset_runs SET project_id = asset_id WHERE project_id IS NULL AND asset_id IS NOT NULL")

    # Backfill clip_candidates from preset_candidates and clips
    cand_count = conn.execute("SELECT COUNT(*) FROM clip_candidates").fetchone()[0]
    if cand_count == 0:
        conn.execute("""
            INSERT OR IGNORE INTO clip_candidates (
                id, project_id, preset_run_id, clip_id, start_time, end_time, title, score, selection_reason, source_evidence, status, edl_json, created_at
            )
            SELECT
                pc.id,
                COALESCE(pr.project_id, pr.asset_id, cl.asset_id),
                pc.run_id,
                pc.clip_id,
                cl.start,
                cl.end,
                cl.title,
                COALESCE(pc.score, cl.score, 0),
                COALESCE(pc.reason, cl.reason, ''),
                COALESCE(pc.evidence_json, cl.evidence, '{}'),
                COALESCE(pc.status, 'proposed'),
                COALESCE(pc.edl_json, '[]'),
                COALESCE(pr.started_at, CURRENT_TIMESTAMP)
            FROM preset_candidates pc
            LEFT JOIN preset_runs pr ON pr.id = pc.run_id
            LEFT JOIN clips cl ON cl.id = pc.clip_id
            WHERE cl.id IS NOT NULL
        """)

    # Backfill rendered_clips from clips with render_status = 'rendered'
    conn.execute("""
        INSERT OR IGNORE INTO rendered_clips (
            id, project_id, candidate_id, preset_run_id, clip_id, title, file_path, thumbnail_path, duration, aspect_ratio, status, created_at
        )
        SELECT
            c.id,
            COALESCE(c.project_id, c.asset_id),
            c.id,
            c.preset_id,
            c.id,
            c.title,
            c.output_path,
            NULL,
            MAX(0, c.end - c.start),
            '9:16',
            'rendered',
            CURRENT_TIMESTAMP
        FROM clips c
        WHERE c.render_status = 'rendered' AND c.output_path IS NOT NULL
    """)

    # Also backfill rendered_clips from variants with status = 'rendered'
    conn.execute("""
        INSERT OR IGNORE INTO rendered_clips (
            id, project_id, candidate_id, preset_run_id, clip_id, title, file_path, thumbnail_path, duration, aspect_ratio, status, created_at
        )
        SELECT
            v.id,
            COALESCE(c.project_id, c.asset_id),
            v.clip_id,
            NULL,
            v.clip_id,
            v.headline,
            v.output_path,
            NULL,
            MAX(0, c.end - c.start),
            '9:16',
            'rendered',
            v.created_at
        FROM variants v
        JOIN clips c ON c.id = v.clip_id
        WHERE v.status = 'rendered' AND v.output_path IS NOT NULL
    """)


@contextmanager
def db():
    conn = sqlite3.connect(DB_FILE, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=30000")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def rows(cursor):
    return [dict(item) for item in cursor.fetchall()]
