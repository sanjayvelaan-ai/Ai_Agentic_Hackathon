"""Consistent SQLite snapshot plus media. Stop ingestion/rendering while backing up."""
import argparse
import json
import shutil
import sqlite3
from contextlib import closing
from pathlib import Path

def backup(source,destination):
    source=Path(source).resolve();destination=Path(destination).resolve()
    if destination==source or destination.is_relative_to(source):raise ValueError('Backup must be outside the data directory')
    if destination.exists():raise ValueError('Choose a new backup directory')
    destination.mkdir(parents=True)
    with closing(sqlite3.connect(source/'remixora.sqlite3')) as live,closing(sqlite3.connect(destination/'remixora.sqlite3')) as copy:
        if live.execute("SELECT COUNT(*) FROM jobs WHERE status IN ('queued','running')").fetchone()[0]:raise ValueError('Wait until the job queue is idle')
        live.backup(copy)
        assert copy.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
    for folder in ['uploads','exports']:
        if (source/folder).exists():shutil.copytree(source/folder,destination/folder)
    (destination/'backup.json').write_text(json.dumps({'schema':2,'source':str(source)}))
    return destination

def restore(source,destination):
    source=Path(source).resolve();destination=Path(destination).resolve()
    if destination.exists():raise ValueError('Restore requires a new, empty destination path; never overwrite live data')
    shutil.copytree(source,destination)
    with closing(sqlite3.connect(destination/'remixora.sqlite3')) as c:
        for table,col,folder in [('assets','media_path','uploads'),('clips','output_path','exports'),('variants','output_path','exports')]:
            for row_id,path in c.execute(f'SELECT id,{col} FROM {table} WHERE {col} IS NOT NULL').fetchall():
                c.execute(f'UPDATE {table} SET {col}=? WHERE id=?',(str(destination/folder/Path(path).name),row_id))
        assert c.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        c.commit()
    return destination

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['backup','restore']);parser.add_argument('source');parser.add_argument('destination');args=parser.parse_args()
    print((backup if args.action=='backup' else restore)(args.source,args.destination))
