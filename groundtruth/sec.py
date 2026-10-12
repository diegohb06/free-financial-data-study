"""SEC EDGAR access: declared User-Agent, rate limit, cache every response."""

import json
import os
import threading
import time
from pathlib import Path

import requests

# The SEC asks every automated client to identify itself with a contact address.
# Set it yourself, for example: export SEC_USER_AGENT="Your Name you@example.com"
USER_AGENT_VARIABLE = "SEC_USER_AGENT"
CACHE_DIR = Path(__file__).resolve().parent.parent / "cache" / "sec"
MIN_INTERVAL = 0.2  # seconds between requests: 5 per second, half the SEC limit of 10

_last_request = 0.0
_pace = threading.Lock()  # requests may run in parallel, but start at most 5 per second
_session = requests.Session()  # one connection, reused


def user_agent() -> str:
    """The User-Agent declared to the SEC, from the environment. Only needed for downloads."""
    value = os.environ.get(USER_AGENT_VARIABLE, "").strip()
    if not value:
        raise RuntimeError(
            f"Set the {USER_AGENT_VARIABLE} environment variable to your name and email before "
            'downloading from the SEC, for example: export SEC_USER_AGENT="Your Name you@example.com"'
        )
    return value


def _cache_path(url: str) -> Path:
    name = url.split("://", 1)[1].replace("/", "__")
    return CACHE_DIR / name


def get_text(url: str, cache_dir: Path | None = None) -> str:
    """Return the body at url, from the local cache when present."""
    global _last_request
    path = (cache_dir or CACHE_DIR) / _cache_path(url).name
    if path.exists():
        return path.read_text()

    agent = user_agent()
    with _pace:
        wait = MIN_INTERVAL - (time.monotonic() - _last_request)
        if wait > 0:
            time.sleep(wait)
        _last_request = time.monotonic()
    response = _session.get(url, headers={"User-Agent": agent}, timeout=60)
    response.raise_for_status()

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(response.text)
    return response.text


def get_json(url: str, cache_dir: Path | None = None) -> dict:
    return json.loads(get_text(url, cache_dir))


def ticker_to_cik() -> dict[str, int]:
    """Map ticker -> CIK from the SEC's own ticker file."""
    data = get_json("https://www.sec.gov/files/company_tickers.json")
    return {row["ticker"]: int(row["cik_str"]) for row in data.values()}


def company_facts(cik: int) -> dict:
    """All XBRL facts a company has filed (one request per company)."""
    return get_json(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json")
