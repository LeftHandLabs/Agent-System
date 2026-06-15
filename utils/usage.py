import re
import shutil
import subprocess
import time
from utils.logger import setup_logger

logger = setup_logger("usage_check")

_cache: dict = {"value": None, "ts": 0.0}
_CACHE_TTL = 300  # 5 minutes


_CLAUDE_FALLBACK_PATHS = [
    "~/.local/bin/claude",
    "/usr/local/bin/claude",
    "/usr/bin/claude",
]


def _find_claude_bin() -> str | None:
    found = shutil.which("claude")
    if found:
        return found
    for path in _CLAUDE_FALLBACK_PATHS:
        if shutil.os.path.isfile(path):
            return path
    return None


def _usage_pct_via_claude_cli() -> float | None:
    claude_bin = _find_claude_bin()
    if not claude_bin:
        logger.warning("Could not read API usage: `claude` not found; proceeding anyway.")
        return None

    result = subprocess.run(
        [claude_bin, "--print"],
        input="/usage",
        capture_output=True,
        text=True,
        timeout=15,
    )
    match = re.search(r"Current session:\s+(\d+(?:\.\d+)?)%\s+used", result.stdout)
    if match:
        return float(match.group(1))
    return None


def get_usage_pct() -> float | None:
    """
    Returns current 5-hour session usage as a percentage (0–100), or None on failure.
    Result is cached for 5 minutes.
    """
    now = time.monotonic()
    if _cache["value"] is not None and now - _cache["ts"] < _CACHE_TTL:
        return _cache["value"]

    try:
        result = _usage_pct_via_claude_cli()
        if result is None:
            logger.warning("Could not read API usage; proceeding anyway.")
            return None
        _cache["value"] = result
        _cache["ts"] = now
        return result
    except Exception as e:
        logger.warning(f"Could not read API usage; proceeding anyway. ({e})")
        return None
