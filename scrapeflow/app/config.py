import os


def _int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


# Auth: comma-separated list of valid API keys, e.g. API_KEYS=key1,key2
API_KEYS = {k.strip() for k in os.environ.get("API_KEYS", "").split(",") if k.strip()}

# Browser
CHROME_BIN = os.environ.get("CHROME_BIN", "")
CHROMEDRIVER = os.environ.get("CHROMEDRIVER", "")
PROXY_URL = os.environ.get("PROXY_URL", "")  # optional, e.g. http://user:pass@host:port
USER_AGENT = os.environ.get(
    "USER_AGENT",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/130.0.0.0 Safari/537.36",
)

# Limits
PAGE_TIMEOUT = _int("PAGE_TIMEOUT", 30)
WAIT_TIMEOUT = _int("WAIT_TIMEOUT", 15)
MAX_WORKERS = _int("MAX_WORKERS", 3)  # concurrent browsers
MAX_STEPS = _int("MAX_STEPS", 50)
MAX_SLEEP = _int("MAX_SLEEP", 10)
JOB_TTL_SECONDS = _int("JOB_TTL_SECONDS", 3600)
MAX_LINKS = _int("MAX_LINKS", 200)
MAX_TEXT_CHARS = _int("MAX_TEXT_CHARS", 200_000)

# Safety: set ALLOW_PRIVATE_NETWORKS=1 only for local testing
ALLOW_PRIVATE_NETWORKS = os.environ.get("ALLOW_PRIVATE_NETWORKS", "0") == "1"
