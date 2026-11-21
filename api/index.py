import sys
import urllib.parse
from pathlib import Path

# Ensure remixora-ai is in python path
root = Path(__file__).resolve().parent.parent / "remixora-ai"
if str(root) not in sys.path:
    sys.path.insert(0, str(root))

from app.main import app as _fastapi_app

async def app(scope, receive, send):
    if scope.get("type") == "http":
        headers = dict(scope.get("headers", []))
        if b"x-now-route-matches" in headers:
            raw_matches = headers[b"x-now-route-matches"].decode("utf-8")
            parts = dict(p.split("=", 1) for p in raw_matches.split("&") if "=" in p)
            if "1" in parts:
                matched = urllib.parse.unquote(parts["1"])
                scope["path"] = "/" + matched.lstrip("/")
        elif scope.get("path") in {"/api/index.py", "/api/index"}:
            scope["path"] = "/"
    await _fastapi_app(scope, receive, send)


