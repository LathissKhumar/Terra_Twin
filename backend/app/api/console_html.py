"""Render the rich scientific HTML console for the TerraTwin backend server."""

from functools import lru_cache
from pathlib import Path

_HTML_FILE = Path(__file__).parent / "console.html"


@lru_cache(maxsize=4)
def get_console_html(version: str = "0.1.0", environment: str = "production") -> str:
    """Generate the full dark-mode scientific workspace console HTML."""
    raw_html = _HTML_FILE.read_text(encoding="utf-8")
    return raw_html.replace("{{version}}", version).replace("{{environment}}", environment)
