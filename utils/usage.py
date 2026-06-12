import os
import json
import time
import requests
import anthropic
from pathlib import Path
from utils.logger import setup_logger

logger = setup_logger("usage_check")

_CLAUDE_CREDENTIALS = Path.home() / ".claude" / ".credentials.json"
_OAUTH_USAGE_URL = "https://api.anthropic.com/api/oauth/usage"

_cache: dict = {"value": None, "ts": 0.0}
_CACHE_TTL = 300  # 5 minutes — no point checking more often than this


def _get_oauth_token() -> str | None:
    if _CLAUDE_CREDENTIALS.exists():
        try:
            data = json.loads(_CLAUDE_CREDENTIALS.read_text())
            return data.get("claudeAiOauth", {}).get("accessToken")
        except Exception:
            pass
    return None


def _usage_pct_via_oauth(token: str) -> float | None:
    resp = requests.get(
        _OAUTH_USAGE_URL,
        headers={"Authorization": f"Bearer {token}"},
        timeout=10,
    )
    resp.raise_for_status()
    return float(resp.json()["five_hour"]["utilization"])


def _usage_pct_via_api_key() -> float | None:
    client = anthropic.Anthropic()
    raw = client.messages.with_raw_response.count_tokens(
        model="claude-haiku-4-5-20251001",
        messages=[{"role": "user", "content": "x"}],
    )
    limit = int(raw.headers.get("anthropic-ratelimit-tokens-limit", 0))
    remaining = int(raw.headers.get("anthropic-ratelimit-tokens-remaining", 0))
    if limit == 0:
        return None
    return (limit - remaining) / limit * 100


def get_usage_pct() -> float | None:
    """
    Returns current 5-hour token usage as a percentage (0–100), or None on failure.
    Result is cached for 5 minutes to avoid rate-limiting the usage endpoint.

    - OAuth login (claude login): calls /api/oauth/usage and reads five_hour.utilization
    - API key (ANTHROPIC_API_KEY): reads rate-limit headers from count_tokens response
    """
    now = time.monotonic()
    if _cache["value"] is not None and now - _cache["ts"] < _CACHE_TTL:
        return _cache["value"]

    try:
        if os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"):
            result = _usage_pct_via_api_key()
        else:
            token = _get_oauth_token()
            if token:
                result = _usage_pct_via_oauth(token)
            else:
                logger.warning("Usage check skipped: no credentials found (set ANTHROPIC_API_KEY or run `claude login`)")
                return None

        _cache["value"] = result
        _cache["ts"] = now
        return result
    except Exception as e:
        logger.warning(f"Usage check skipped: {e}")
        return None
