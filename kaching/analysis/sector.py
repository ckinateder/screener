"""Which sector ETF to compare a stock against (Chart Checklist #10).

Suggestion order: Yahoo industry map, then sector map (both in sector_etfs.json, editable).
A per-ticker override, set in the app, wins over both.
"""
import json
from pathlib import Path

_MAPS = json.loads((Path(__file__).parent / "sector_etfs.json").read_text(encoding="utf-8"))
NOT_STOCKS = {"ETF", "MUTUALFUND", "INDEX"}  # they *are* the fund; a sector ETF check doesn't apply


def suggest_etf(info: dict | None) -> tuple[str, str] | None:
    """(etf, "industry" | "sector") from the stock's Yahoo classification, or None."""
    if not info or info.get("quote_type") in NOT_STOCKS:
        return None
    if etf := _MAPS["industry"].get(info.get("industry") or ""):
        return etf, "industry"
    if etf := _MAPS["sector"].get(info.get("sector") or ""):
        return etf, "sector"
    return None


def resolve_etf(override: str | None, info: dict | None) -> dict | None:
    """{etf, source, suggested}: the override if set, else the suggestion. None when n/a."""
    if info and info.get("quote_type") in NOT_STOCKS:
        return None
    suggestion = suggest_etf(info)
    suggested = suggestion[0] if suggestion else None
    if override:
        return {"etf": override, "source": "override", "suggested": suggested}
    if suggestion:
        return {"etf": suggestion[0], "source": suggestion[1], "suggested": suggested}
    return None
