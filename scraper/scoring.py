"""
Scoring, prioritisation and market-scenario narration — at sub-category level.

A sub-category is one (category x price tier) pair, e.g. running_men / Mid-Range.
Each was scraped independently with Myntra's price slider set to that tier.

For every sub-category we compute:
  demand        normalised log review volume across all sub-categories (proxy for how
                many people actually buy here — reviews, not verified sales)
  focal_share   the focal brand's share of the sub-category's total ratings count
  quadrant      2x2 of demand (high/low) x focal presence (strong/barely), split at the
                median across sub-categories
  priority      demand x (1 - focal_share), ranked, for Opportunity sub-categories only
  scenario      plain-English market read: leader, competitive intensity, focal position

All narration here is generated deterministically from the numbers — no LLM calls — so
a data refresh regenerates it automatically.
"""

import json
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

from config import FOCAL_BRAND

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCORES_DIR = PROJECT_ROOT / "data" / "scores"

MEANINGFUL_SHARE = 0.05      # a brand "matters" in a cell at >=5% of its ratings volume
HHI_CONCENTRATED = 0.25
HHI_MODERATE = 0.15

# Below this many listings on Myntra, a sub-category is too shallow for its percentage
# shares to mean anything (e.g. women's basketball has ~19 listings in total, where a
# single model can read as a 97% "share"). Such cells are flagged and kept visible, but
# are barred from the opportunity ranking so they cannot generate false priorities.
THIN_LISTING_THRESHOLD = 50


def _is_focal(brand) -> bool:
    return bool(brand) and str(brand).strip().lower() == FOCAL_BRAND.strip().lower()


def _weighted_rating(df: pd.DataFrame):
    sub = df.dropna(subset=["adjusted_rating"])
    if sub.empty:
        return None
    w = sub["review_count"].clip(lower=1)
    return float((sub["adjusted_rating"] * w).sum() / w.sum())


def flatten(processed_by_category: dict) -> pd.DataFrame:
    rows = []
    for category, data in processed_by_category.items():
        for sub in data.get("subcategories", []):
            for p in sub.get("products", []):
                rows.append(p)
    return pd.DataFrame(rows)


def brand_table(cell_df: pd.DataFrame) -> list:
    """Per-brand aggregates within one sub-category, ordered by ratings volume."""
    total_reviews = cell_df["review_count"].sum() or 1
    total_listings = len(cell_df) or 1
    out = []
    for brand, bdf in cell_df.groupby("brand"):
        out.append({
            "brand": brand,
            "listing_count": int(len(bdf)),
            "listing_share": float(len(bdf) / total_listings),
            "review_volume": int(bdf["review_count"].sum()),
            "review_share": float(bdf["review_count"].sum() / total_reviews),
            "weighted_rating": _weighted_rating(bdf),
            "avg_discount_pct": float(bdf["discount_pct"].dropna().mean()) if bdf["discount_pct"].notna().any() else None,
            "sponsored_listings": int(bdf["sponsored"].sum()),
            "sponsored_share": float(bdf["sponsored"].mean()),
            "is_focal": _is_focal(brand),
        })
    return sorted(out, key=lambda x: x["review_volume"], reverse=True)


def competition_read(brands: list) -> dict:
    """Herfindahl over brand ratings-share => how concentrated / contestable the cell is.

    `leader` is the genuine #1 brand by ratings volume — which can be the focal brand
    itself in bands it already owns. `top_competitor` is the strongest brand that is
    NOT the focal brand, i.e. the one to actually beat; the two differ wherever the
    focal brand already leads.
    """
    if not brands:
        return {"leader": None, "leader_share": None, "leader_rating": None,
                "leader_listings": None, "leader_is_focal": False,
                "top_competitor": None, "competitor_share": None, "competitor_rating": None,
                "hhi": None, "intensity": None, "meaningful_brands": 0}

    hhi = float(sum(b["review_share"] ** 2 for b in brands))
    meaningful = sum(1 for b in brands if b["review_share"] >= MEANINGFUL_SHARE)

    leader = brands[0]                                    # brands arrive sorted by volume
    non_focal = [b for b in brands if not b["is_focal"]]
    challenger = non_focal[0] if non_focal else None

    if hhi >= HHI_CONCENTRATED:
        intensity = "Concentrated"
    elif hhi >= HHI_MODERATE:
        intensity = "Moderate"
    else:
        intensity = "Fragmented"

    return {
        "leader": leader["brand"],
        "leader_share": leader["review_share"],
        "leader_rating": leader["weighted_rating"],
        "leader_listings": leader["listing_count"],
        "leader_is_focal": bool(leader["is_focal"]),
        "top_competitor": challenger["brand"] if challenger else None,
        "competitor_share": challenger["review_share"] if challenger else None,
        "competitor_rating": challenger["weighted_rating"] if challenger else None,
        "hhi": hhi,
        "intensity": intensity,
        "meaningful_brands": meaningful,
    }


def scenario_text(comp: dict, focal: dict, tier_label: str) -> dict:
    """Plain-English market read shown under each ranked opportunity."""
    if comp["leader"] is None:
        leader_txt = "No brand has meaningful ratings volume here."
    else:
        share = f"{comp['leader_share']*100:.0f}%"
        rating = f"{comp['leader_rating']:.2f}" if comp["leader_rating"] else "n/a"
        leader_txt = (
            f"{comp['leader']} leads with {share} of all ratings in this band "
            f"({comp['leader_listings']} listings, {rating} weighted rating)."
        )
        if comp["leader_is_focal"] and comp["top_competitor"]:
            leader_txt += (
                f" {FOCAL_BRAND} already owns this band; the nearest challenger is "
                f"{comp['top_competitor']} on {comp['competitor_share']*100:.0f}%."
            )

    if comp["intensity"] == "Concentrated":
        comp_txt = (
            f"Competition is concentrated — a single brand absorbs most demand, "
            f"with {comp['meaningful_brands']} brands holding meaningful share."
        )
    elif comp["intensity"] == "Moderate":
        comp_txt = (
            f"Competition is moderately concentrated across "
            f"{comp['meaningful_brands']} brands with meaningful share."
        )
    elif comp["intensity"] == "Fragmented":
        comp_txt = (
            f"Competition is fragmented — {comp['meaningful_brands']} brands split demand, "
            f"so no incumbent owns the band."
        )
    else:
        comp_txt = "Too little ratings volume to judge competitive intensity."

    if focal["listing_count"] == 0:
        focal_txt = f"{FOCAL_BRAND} has no listings in this price band at all."
    else:
        r = f"{focal['weighted_rating']:.2f}" if focal["weighted_rating"] else "n/a"
        # compare against the strongest brand that isn't the focal brand, so the number
        # stays meaningful in bands the focal brand already leads
        gap = ""
        if focal["weighted_rating"] and comp.get("competitor_rating"):
            d = focal["weighted_rating"] - comp["competitor_rating"]
            gap = f", rating {d:+.2f} vs {comp['top_competitor']}"
        if comp.get("leader_is_focal"):
            focal_txt = (
                f"{FOCAL_BRAND} is the leading brand here with {focal['listing_count']} listings "
                f"and {focal['review_share']*100:.1f}% of ratings volume ({r} weighted rating{gap})."
            )
        else:
            focal_txt = (
                f"{FOCAL_BRAND} is present with {focal['listing_count']} listings but only "
                f"{focal['review_share']*100:.1f}% of ratings volume ({r} weighted rating{gap})."
            )

    return {"leader": leader_txt, "competition": comp_txt, "focal": focal_txt}


def score(processed_by_category: dict, run_ts: str = None) -> dict:
    run_ts = run_ts or datetime.now().strftime("%Y-%m-%d_%H%M")
    master = flatten(processed_by_category)
    if master.empty:
        raise ValueError("No products to score")

    # sub-category totals reported by Myntra (for transparency on sample coverage)
    reported = {}
    for category, data in processed_by_category.items():
        for sub in data.get("subcategories", []):
            reported[(category, sub["price_tier"])] = {
                "total_count_reported": sub.get("total_count_reported"),
                "price_min": sub.get("price_min"),
                "price_max": sub.get("price_max"),
                "pages_scraped": sub.get("pages_scraped"),
                "sku_listings": sub.get("sku_listings"),
            }

    rows = []
    for (category, tier), cell_df in master.groupby(["category", "price_tier"]):
        brands = brand_table(cell_df)
        comp = competition_read(brands)

        focal_df = cell_df[cell_df["brand"].apply(_is_focal)]
        total_reviews = int(cell_df["review_count"].sum())
        focal_reviews = int(focal_df["review_count"].sum())
        focal_info = {
            "listing_count": int(len(focal_df)),
            "review_volume": focal_reviews,
            "review_share": (focal_reviews / total_reviews) if total_reviews else 0.0,
            "listing_share": (len(focal_df) / len(cell_df)) if len(cell_df) else 0.0,
            "weighted_rating": _weighted_rating(focal_df) if not focal_df.empty else None,
        }

        meta = reported.get((category, tier), {})
        reported_n = meta.get("total_count_reported")
        rows.append({
            "category": category,
            "price_tier": tier,
            "subcategory": f"{category}|{tier}",
            "price_min": meta.get("price_min"),
            "price_max": meta.get("price_max"),
            "total_count_reported": reported_n,
            "pages_scraped": meta.get("pages_scraped"),
            "sku_listings": meta.get("sku_listings"),
            "is_thin": bool(reported_n is not None and reported_n < THIN_LISTING_THRESHOLD),
            "total_listings": int(len(cell_df)),
            "total_review_volume": total_reviews,
            "focal_listing_count": focal_info["listing_count"],
            "focal_review_volume": focal_info["review_volume"],
            "focal_share": focal_info["review_share"],
            "focal_listing_share": focal_info["listing_share"],
            "focal_weighted_rating": focal_info["weighted_rating"],
            "demand_raw": float(np.log1p(total_reviews)),
            "market_leader": comp["leader"],
            "leader_share": comp["leader_share"],
            "leader_rating": comp["leader_rating"],
            "leader_is_focal": comp["leader_is_focal"],
            "top_competitor": comp["top_competitor"],
            "competitor_share": comp["competitor_share"],
            "competitor_rating": comp["competitor_rating"],
            "competition_hhi": comp["hhi"],
            "competition_intensity": comp["intensity"],
            "meaningful_brands": comp["meaningful_brands"],
            "scenario": scenario_text(comp, focal_info, tier),
            "brands": brands,
        })

    cells = pd.DataFrame(rows)

    dmin, dmax = cells["demand_raw"].min(), cells["demand_raw"].max()
    cells["demand_norm"] = 0.5 if dmax == dmin else (cells["demand_raw"] - dmin) / (dmax - dmin)

    demand_median = cells["demand_norm"].median()
    share_median = cells["focal_share"].median()

    def quadrant(row):
        # Strict ">" on share: the focal brand is absent from many cells, so the median
        # can itself be 0 — ">=" would then read "absent" as "strong presence".
        high_demand = row["demand_norm"] > demand_median
        strong = row["focal_share"] > share_median
        if high_demand and strong:
            return "Defend"            # high demand, strong presence
        if high_demand and not strong:
            return "Opportunity"       # high demand, barely present  <- the grow list
        if not high_demand and strong:
            return "Maintain"          # low demand, strong presence
        return "Deprioritise"          # low demand, barely present

    cells["quadrant"] = cells.apply(quadrant, axis=1)
    # thin cells keep their quadrant (so they stay visible on the matrix) but are barred
    # from the ranking, where a 19-listing niche would otherwise outrank a real market
    cells["priority_score"] = np.where(
        (cells["quadrant"] == "Opportunity") & (~cells["is_thin"]),
        cells["demand_norm"] * (1 - cells["focal_share"]),
        np.nan,
    )
    cells["priority_rank"] = cells["priority_score"].rank(ascending=False, method="min")

    overall_reviews = int(cells["total_review_volume"].sum())
    overall_focal = int(cells["focal_review_volume"].sum())

    result = {
        "run_ts": run_ts,
        "focal_brand": FOCAL_BRAND,
        "categories": sorted(cells["category"].unique().tolist()),
        "thresholds": {"demand_median": float(demand_median), "share_median": float(share_median)},
        "summary": {
            "n_categories": int(cells["category"].nunique()),
            "n_subcategories": int(len(cells)),
            "n_opportunities": int((cells["quadrant"] == "Opportunity").sum()),
            "focal_overall_share": (overall_focal / overall_reviews) if overall_reviews else 0.0,
            "total_review_volume": overall_reviews,
        },
        "focal_concentration_index": {
            cat: data.get("focal_concentration_index")
            for cat, data in processed_by_category.items()
        },
        # paid placement is only visible on unfiltered category pages, so it is held per
        # category rather than per sub-category (see myntra_scraper.scrape_ad_landscape)
        "ad_landscape": {
            cat: data.get("ad_landscape")
            for cat, data in processed_by_category.items()
        },
        "cells": cells.to_dict(orient="records"),
    }

    SCORES_DIR.mkdir(parents=True, exist_ok=True)
    out_path = SCORES_DIR / f"scores_{run_ts}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False, default=str)
    print(f"    saved -> {out_path}")
    return result
