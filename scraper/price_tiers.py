"""Phase 3 — Price tiers.

Uses a fixed (category, gender) -> tier-boundary lookup table supplied by the user
(data/price_tier_table.json, parsed from Footwear_Price_Tiers.xlsx) rather than
percentile-derived boundaries. Tiers: Entry-Level / Mid-Range / Premium / Pro-Tier.
"""

import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
TABLE_PATH = PROJECT_ROOT / "data" / "price_tier_table.json"

TIER_LABELS = ["Entry-Level", "Mid-Range", "Premium", "Pro-Tier"]

_table_cache = None


def _load_table() -> dict:
    global _table_cache
    if _table_cache is None:
        with open(TABLE_PATH, encoding="utf-8") as f:
            _table_cache = json.load(f)
    return _table_cache


def get_price_tiers(category_key: str) -> dict:
    """category_key e.g. 'running_men'. Returns the same shape compute_price_tiers used to,
    so downstream code (scoring.py, dashboard) doesn't need to change: {"boundaries": [...]}"""
    table = _load_table()
    tiers = table.get(category_key)
    if tiers is None:
        return None
    boundaries = []
    for t in tiers:
        lo, hi = t["min"], t["max"]
        range_str = f"Rs {lo:,}+" if hi is None else f"Rs {lo:,} - {hi:,}"
        boundaries.append({"label": t["label"], "min": lo, "max": hi, "range_str": range_str})
    return {"boundaries": boundaries}


def assign_tier(price, tier_info: dict) -> str:
    if tier_info is None or price is None:
        return None
    for band in tier_info["boundaries"]:
        lo, hi = band["min"], band["max"]
        if hi is None or (lo <= price < hi):
            return band["label"]
    return tier_info["boundaries"][-1]["label"]


def tier_range_label(tier_info: dict, label: str) -> str:
    if tier_info is None:
        return label
    for band in tier_info["boundaries"]:
        if band["label"] == label:
            return band["range_str"]
    return label
