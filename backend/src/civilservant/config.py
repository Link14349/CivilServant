from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = PROJECT_ROOT / ".data"
DATABASE_PATH = DATA_DIR / "civilservant.db"
FRONTEND_DIST = PROJECT_ROOT / "frontend" / "dist"
PROMPT_DIR = Path(__file__).resolve().parent / "prompts"

DEFAULT_API_BASE = "https://api.deepseek.com"
DEFAULT_MODEL = "deepseek-v4-flash"

