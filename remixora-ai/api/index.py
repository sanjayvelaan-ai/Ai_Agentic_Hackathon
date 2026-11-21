import sys
import urllib.parse
from pathlib import Path

# Ensure app package is importable
current_dir = Path(__file__).resolve().parent
parent_dir = current_dir.parent
if str(parent_dir) not in sys.path:
    sys.path.insert(0, str(parent_dir))

from app.main import app as _fastapi_app

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



