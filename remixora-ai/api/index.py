import os
import sys
import urllib.parse
from pathlib import Path

# Ensure remixora-ai is in python path
parent_dir = Path(__file__).resolve().parent.parent
if str(parent_dir) not in sys.path:
    sys.path.insert(0, str(parent_dir))

if "PYTHONPATH" in os.environ:
    if str(parent_dir) not in os.environ["PYTHONPATH"]:
        os.environ["PYTHONPATH"] = str(parent_dir) + os.pathsep + os.environ["PYTHONPATH"]
else:
    os.environ["PYTHONPATH"] = str(parent_dir)

from app.db import init_db
from app.main import app as _fastapi_app, worker
from app.media import ensure_ffmpeg

init_db()
worker.start()
ensure_ffmpeg()


async def app(scope, receive, send):
    if scope.get("type") == "http":
        query_string = scope.get("query_string", b"").decode("latin1")
        if query_string:
            params = urllib.parse.parse_qs(query_string, keep_blank_values=True)
            if "__path" in params and params["__path"]:
                raw_path = params.pop("__path")[0]
                scope["path"] = "/" + raw_path.lstrip("/")
                new_query = urllib.parse.urlencode(params, doseq=True)
                scope["query_string"] = new_query.encode("latin1")
        elif scope.get("path") in {"/api/index.py", "/api/index"}:
            scope["path"] = "/"
    await _fastapi_app(scope, receive, send)
