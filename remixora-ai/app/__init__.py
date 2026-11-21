from pathlib import Path
from dotenv import load_dotenv

# Server-only configuration; inherited environment takes precedence.
load_dotenv(Path(__file__).resolve().parents[1] / ".env.local", override=False)
