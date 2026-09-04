"""
End-to-end refresh: scrape -> features -> scoring -> review mining, writing timestamped
files under data/ and appending to data/run_log.json (which is what the dashboard's
"last refreshed" indicator reads).

This is what the dashboard's Refresh button calls.
"""

import json
import traceback
from datetime import datetime
from pathlib import Path

from feature_engineering import engineer_features, save_processed
from myntra_scraper import PILOT_CATEGORIES, run as run_scraper
from review_mining import mine_opportunities, save_raw_reviews
from scoring import score

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RUN_LOG_PATH = PROJECT_ROOT / "data" / "run_log.json"


def _load_run_log() -> dict:
    if RUN_LOG_PATH.exists():
        with open(RUN_LOG_PATH, encoding="utf-8") as f:
            return json.load(f)
    return {"runs": []}


def _save_run_log(log: dict):
    RUN_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(RUN_LOG_PATH, "w", encoding="utf-8") as f:
        json.dump(log, f, indent=2, ensure_ascii=False)


def run_pipeline(categories: dict = None, headless: bool = False,
                 status_callback=None, mine_reviews: bool = True):
    categories = categories or PILOT_CATEGORIES
    run_ts = datetime.now().strftime("%Y-%m-%d_%H%M")
    log = _load_run_log()
    entry = {
        "run_ts": run_ts,
        "started_at": datetime.now().isoformat(),
        "categories": list(categories.keys()),
        "phases": {},
    }

    def notify(msg):
        print(msg)
        if status_callback:
            status_callback(msg)

    try:
        notify(f"Scraping {len(categories)} categories across their price tiers...")
        raw_results = run_scraper(categories=categories, headless=headless,
                                  run_ts=run_ts, status_callback=status_callback)
        entry["phases"]["scrape"] = "success"
    except Exception as e:
        entry["phases"]["scrape"] = f"failed: {e}"
        entry["completed_at"] = datetime.now().isoformat()
        log["runs"].append(entry)
        _save_run_log(log)
        traceback.print_exc()
        raise

    notify("Engineering features...")
    processed_by_category = {}
    for key, raw in raw_results.items():
        if "error" in raw:
            continue
        processed = engineer_features(raw)
        save_processed(processed, run_ts)
        processed_by_category[key] = processed
    entry["phases"]["features"] = "success" if processed_by_category else "no data"

    notify("Scoring sub-categories and ranking opportunities...")
    try:
        scores = score(processed_by_category, run_ts=run_ts)
        entry["phases"]["scoring"] = "success"
    except Exception as e:
        entry["phases"]["scoring"] = f"failed: {e}"
        scores = None
        traceback.print_exc()

    if scores and mine_reviews:
        notify("Mining customer reviews for top opportunities...")
        try:
            reviews = mine_opportunities(scores, processed_by_category,
                                         headless=headless, status_callback=status_callback)
            save_raw_reviews(reviews, run_ts)
            entry["phases"]["review_mining"] = f"success ({len(reviews)} sub-categories)"
        except Exception as e:
            entry["phases"]["review_mining"] = f"failed: {e}"
            traceback.print_exc()
    else:
        entry["phases"]["review_mining"] = "skipped"

    entry["completed_at"] = datetime.now().isoformat()
    log["runs"].append(entry)
    _save_run_log(log)
    notify("Done.")

    return {"run_ts": run_ts, "processed_by_category": processed_by_category, "scores": scores}


if __name__ == "__main__":
    run_pipeline()
