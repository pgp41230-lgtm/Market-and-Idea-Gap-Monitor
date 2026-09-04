"""Loads the newest completed pipeline run for the dashboard."""

import json
import re
import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scraper"))

DATA = PROJECT_ROOT / "data"
RUN_LOG = DATA / "run_log.json"
PROCESSED = DATA / "processed"
SCORES = DATA / "scores"
REVIEWS = DATA / "reviews"

PRETTY_CATEGORY = {
    "running": "Running", "basketball": "Basketball", "training": "Training / Gym",
    "casual": "Casual Sneakers", "football": "Football", "hiking": "Hiking / Outdoor",
    "walking": "Walking", "badminton": "Badminton",
}


def pretty_category(key: str) -> str:
    if not key:
        return "-"
    base, _, gender = key.rpartition("_")
    if not base:
        return key.replace("_", " ").title()
    return f"{PRETTY_CATEGORY.get(base, base.title())} — {gender.title()}"


def pretty_subcategory(category: str, tier: str) -> str:
    return f"{pretty_category(category)} · {tier}"


def latest_run_ts() -> str:
    """Newest run that produced a scores file (works even if run_log is missing).

    Ordered by file modification time, not filename: run ids are not all the same shape
    (a label like `2026-09-05_PILOT` sorts after `2026-09-05_0143` alphabetically even
    though it is older), so a lexicographic sort can silently serve stale data.
    """
    files = list(SCORES.glob("scores_*.json"))
    if not files:
        return None
    newest = max(files, key=lambda p: p.stat().st_mtime)
    return newest.name.replace("scores_", "").replace(".json", "")


def load_scores(run_ts: str) -> dict:
    p = SCORES / f"scores_{run_ts}.json"
    if not p.exists():
        return None
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def load_processed(run_ts: str, categories: list) -> dict:
    out = {}
    for cat in categories:
        p = PROCESSED / f"{cat}_{run_ts}.json"
        if p.exists():
            with open(p, encoding="utf-8") as f:
                out[cat] = json.load(f)
    return out


def load_raw_reviews(run_ts: str) -> dict:
    p = REVIEWS / f"raw_reviews_{run_ts}.json"
    if not p.exists():
        return {}
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def load_review_analysis(run_ts: str) -> dict:
    """Claude-authored pros/cons per sub-category. Falls back to the most recent
    analysis file so a fresh data refresh still shows the last written interpretation."""
    exact = REVIEWS / f"analysis_{run_ts}.json"
    if exact.exists():
        with open(exact, encoding="utf-8") as f:
            return json.load(f)
    candidates = sorted(REVIEWS.glob("analysis_*.json"))
    if not candidates:
        return {}
    with open(candidates[-1], encoding="utf-8") as f:
        return json.load(f)


def run_completed_at(run_ts: str) -> str:
    if not RUN_LOG.exists():
        return None
    with open(RUN_LOG, encoding="utf-8") as f:
        log = json.load(f)
    for r in reversed(log.get("runs", [])):
        if r.get("run_ts") == run_ts:
            return r.get("completed_at")
    return None


def products_for(processed: dict, category: str, tier: str) -> pd.DataFrame:
    data = processed.get(category)
    if not data:
        return pd.DataFrame()
    for sub in data.get("subcategories", []):
        if sub["price_tier"] == tier:
            return pd.DataFrame(sub.get("products", []))
    return pd.DataFrame()


def load_bundle():
    run_ts = latest_run_ts()
    if not run_ts:
        return None, None, None
    scores = load_scores(run_ts)
    if not scores:
        return None, None, None
    processed = load_processed(run_ts, scores.get("categories", []))
    return run_ts, scores, processed
