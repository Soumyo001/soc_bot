from pathlib import Path
from typing import Optional
import os

DATA_DIR = Path("data")
DATA_DIR.mkdir(parents=True, exist_ok=True)
ADMIN_FILE = DATA_DIR / "admins.json"

def load_env(name: str, default: Optional[str] = None) -> Optional[str]:
    v = os.environ.get(name)
    return v.strip() if v else default

BOT_TOKEN = load_env("BOT_TOKEN")
API_KEY = load_env("API_KEY")  # for ingest authentication

if not BOT_TOKEN:
    raise SystemExit("BOT_TOKEN is required (from BotFather). Put it in environment variables")