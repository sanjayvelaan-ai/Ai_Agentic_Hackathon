import sys
from pathlib import Path

# Ensure app package is importable
current_dir = Path(__file__).resolve().parent
parent_dir = current_dir.parent
if str(parent_dir) not in sys.path:
    sys.path.insert(0, str(parent_dir))

from app.main import app as _fastapi_app

async def app(scope, receive, send):
    if scope.get("type") == "http":
        headers = dict(scope.get("headers", []))
        for header_key in [b"x-matched-path", b"x-forwarded-uri", b"x-original-url"]:
            if header_key in headers:
                orig = headers[header_key].decode("utf-8")
                if orig:
                    scope["path"] = orig
                    break
        path = scope.get("path", "")
        if path.startswith("/api/index.py"):
            scope["path"] = path[len("/api/index.py"):] or "/"
        elif path.startswith("/api/index"):
            scope["path"] = path[len("/api/index"):] or "/"
    await _fastapi_app(scope, receive, send)

