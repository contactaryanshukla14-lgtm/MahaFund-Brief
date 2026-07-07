import os
from dotenv import load_dotenv

load_dotenv()

# ── Models ─────────────────────────────────────────────────────────────
GEMINI_MODEL = "gemini-2.5-flash-lite"
GROQ_MODEL = "llama-3.3-70b-versatile"

# ── Retry / Rate-Limit ─────────────────────────────────────────────────
MAX_RETRIES = 3
RETRY_BASE_DELAY_SECONDS = 15          # exponential backoff: 15 → 30 → 60

# ── Inter-agent delays (protects Free Tier burst limits) ───────────────
INTER_AGENT_DELAY_SECONDS = 10

# ── Document Extraction ────────────────────────────────────────────────
MAX_PDFS_PER_PROJECT = 2
TARGET_PDF_TYPES = ["RERA Certificate", "CA Certificate", "Financial Statement", "Form 3", "Form 5"]

# ── Browser / Network ─────────────────────────────────────────────────
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)
CAPTCHA_WAIT_TIMEOUT_MS = 15_000       # max wait for MahaRERA canvas
CAPTCHA_MAX_ATTEMPTS = 3               # retry misread CAPTCHAs
NETWORK_TIMEOUT_SECONDS = 30           # curl_cffi / httpx timeout
PAGE_LOAD_WAIT_MS = 5000               # post-navigation settle time

# ── Debug ──────────────────────────────────────────────────────────────
DEBUG_BROWSER = os.getenv("DEBUG_BROWSER", "0") == "1"
