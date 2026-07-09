import logging
import os
import secrets

from dotenv import load_dotenv

load_dotenv()

# Configure logging early so all modules inherit it.
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Auth / session
SECRET_KEY = os.getenv("SECRET_KEY", secrets.token_hex(32))
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")

# Database
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./agenticvisualizer.db")

# OpenRouter configuration
MODEL_NAME = os.getenv("MODEL_NAME", "openai/gpt-4o-mini")
REFEREE_MODEL_NAME = os.getenv("REFEREE_MODEL_NAME", "~anthropic/claude-sonnet-latest")
OPENROUTER_BASE_URL = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")

# Optional OpenRouter attribution headers
SITE_URL = os.getenv("SITE_URL", "http://localhost:8000")
SITE_NAME = os.getenv("SITE_NAME", "AgenticVisualizer")

MAX_TURNS_DEFAULT = int(os.getenv("MAX_TURNS_DEFAULT", "8"))
MIN_TURNS_DEFAULT = int(os.getenv("MIN_TURNS_DEFAULT", "2"))
REQUEST_TIMEOUT = float(os.getenv("REQUEST_TIMEOUT", "25.0"))

# Token budgets for LLM calls. Increase these if you use a reasoning model, because
# reasoning tokens count against the same budget as the final answer.
AGENT_MAX_TOKENS = int(os.getenv("AGENT_MAX_TOKENS", "120"))
REFEREE_MAX_TOKENS = int(os.getenv("REFEREE_MAX_TOKENS", "400"))

logger.info(
    "Config loaded: base_url=%s model=%s referee_model=%s api_key=%s timeout=%s agent_tokens=%s referee_tokens=%s",
    OPENROUTER_BASE_URL,
    MODEL_NAME,
    REFEREE_MODEL_NAME,
    f"{OPENROUTER_API_KEY[:6]}...{OPENROUTER_API_KEY[-4:]}" if len(OPENROUTER_API_KEY) > 12 else "<not-set>",
    REQUEST_TIMEOUT,
    AGENT_MAX_TOKENS,
    REFEREE_MAX_TOKENS,
)
