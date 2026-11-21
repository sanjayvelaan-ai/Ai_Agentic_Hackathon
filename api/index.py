import sys
from pathlib import Path

# Ensure remixora-ai is in python path
root = Path(__file__).resolve().parent.parent / "remixora-ai"
if str(root) not in sys.path:
    sys.path.insert(0, str(root))

from app.main import app
