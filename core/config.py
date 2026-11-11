"""Shim: re-export root config/ for KingAI-parity modules expecting `core.config`."""
from config import *  # noqa: F401,F403
from config import DATA_ROOT, DATA_DIR, APP_NAME, APP_VERSION, PROJECT_ROOT  # noqa: F401

OPENROUTER_BASE_URL = 'https://openrouter.ai/api/v1'
