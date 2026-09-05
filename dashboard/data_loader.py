"""Loads the newest completed pipeline run for the dashboard."""

import json
import re
import sys
from datetime import datetime
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


def _parse_run_ts(run_ts: str):
    """Run ids are timestamps (2026-09-05_0134); anything else is a hand-made label
    and is treated as oldest so it can never win against a real run."""
    try:
        return datetime.strptime(run_ts, "%Y-%m-%d_%H%M")
    except (ValueError, TypeError):
        return datetime.min


def latest_run_ts() -> str:
    """Newest run that has a scores file on disk.

    Ordered by the timestamp encoded in the run id, NOT by file mtime and NOT
    alphabetically. mtime is useless once the repo is deployed — a git clone stamps
    every file with the same checkout time — and a lexicographic sort puts a label like
    `2026-09-05_PILOT` above the newer `2026-09-05_0134`. Both would silently serve
    stale data to anyone opening the hosted app.
    """
    ids = [p.name.replace("scores_", "").replace(".json", "")
           for p in SCORES.glob("scores_*.json")]
    if not ids:
        return None
    return max(ids, key=_parse_run_ts)


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
    candidates = list(REVIEWS.glob("analysis_*.json"))
    if not candidates:
        return {}
    newest = max(candidates,
                 key=lambda p: _parse_run_ts(p.name.replace("analysis_", "").replace(".json", "")))
    with open(newest, encoding="utf-8") as f:
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


def data_fingerprint() -> str:
    """A cheap signature of the data on disk, used as a cache key.

    Streamlit only clears @st.cache_data when the process restarts, not when the script
    reruns. On a hosted deploy the code updates on every push while the process lives on,
    so a cache with no data-dependent key keeps serving whatever was loaded at first boot
    — the app showed refreshed wording next to stale numbers. Keying on file names and
    sizes means any change to the data busts the cache. Sizes rather than mtimes, because
    a git clone stamps every file with the same checkout time.
    """
    parts = []
    for folder, pattern in ((SCORES, "scores_*.json"), (REVIEWS, "analysis_*.json")):
        for p in sorted(folder.glob(pattern)):
            try:
                parts.append(f"{p.name}:{p.stat().st_size}")
            except OSError:
                continue
    return "|".join(parts)


def load_bundle():
    run_ts = latest_run_ts()
    if not run_ts:
        return None, None, None
    scores = load_scores(run_ts)
    if not scores:
        return None, None, None
    processed = load_processed(run_ts, scores.get("categories", []))
    return run_ts, scores, processed
