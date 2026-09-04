"""
Targeted customer-review mining for the prioritised opportunity sub-categories.

For each opportunity we pull real review text for:
  - the sub-category's top 3 products by ratings volume (whoever makes them)
  - the focal brand's own best-selling product in that same sub-category

Myntra's reviews page (/reviews/{productId}) serves a fixed 12 reviews per product
regardless of how many the product actually has (verified on products with 341 and
2,319 total ratings — both capped at 12, with no pagination, load-more or infinite
scroll available). Where a product has colour variants, each variant is a separate
productId with its own independent 12, so we pool across variants to deepen the sample.

This module only COLLECTS review text. The pros/cons interpretation is written by
Claude reading the pooled reviews, not by an external LLM API.
"""

import json
import random
import time
from pathlib import Path

import pandas as pd
from playwright.sync_api import Page, TimeoutError as PWTimeoutError, sync_playwright

from config import FOCAL_BRAND

PROJECT_ROOT = Path(__file__).resolve().parent.parent
REVIEWS_DIR = PROJECT_ROOT / "data" / "reviews"

TARGET_REVIEWS_PER_PRODUCT = 24
MAX_PAGES_PER_PRODUCT = 2          # own page + at most one colour variant
DELAY_RANGE = (2.0, 4.0)


def _delay():
    time.sleep(random.uniform(*DELAY_RANGE))


def _fetch_reviews(page: Page, style_id) -> dict:
    url = f"https://www.myntra.com/reviews/{style_id}"
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=25000)
        page.wait_for_timeout(1200)
        data = page.evaluate("() => window.__myx && window.__myx.reviewsData || null")
        colours = page.evaluate(
            "() => window.__myx && window.__myx.pdpData && window.__myx.pdpData.colours || null"
        )
    except PWTimeoutError:
        return {"reviews": [], "colours": []}
    if not data:
        return {"reviews": [], "colours": []}
    reviews = [
        {"text": r.get("review", "").strip(), "rating": r.get("userRating")}
        for r in (data.get("reviews") or [])
        if r.get("review")
    ]
    return {"reviews": reviews, "colours": colours or []}


def scrape_product_reviews(page: Page, style_id, budget: list) -> dict:
    pooled, visited, queue, pages = [], set(), [style_id], 0
    while queue and pages < MAX_PAGES_PER_PRODUCT and budget[0] > 0:
        sid = queue.pop(0)
        if sid in visited:
            continue
        visited.add(sid)
        res = _fetch_reviews(page, sid)
        pooled.extend(res["reviews"])
        pages += 1
        budget[0] -= 1
        _delay()
        if len(pooled) >= TARGET_REVIEWS_PER_PRODUCT:
            break
        for c in res.get("colours") or []:
            if c.get("styleId") and c["styleId"] not in visited:
                queue.append(c["styleId"])
    return {"reviews": pooled[:TARGET_REVIEWS_PER_PRODUCT], "pages_visited": pages}


def _product_payload(row: dict) -> dict:
    return {
        "listing_id": row["listing_id"],
        "brand": row["brand"],
        "title": row["title"],
        "url": row["url"],
        "image_url": row.get("image_url"),
        "price": row.get("price"),
        "rating": row.get("rating"),
        "review_count": row.get("review_count"),
    }


def mine_opportunities(scores: dict, processed_by_category: dict,
                       top_n_cells: int = 4, page_budget: int = 30,
                       headless: bool = False, status_callback=None) -> dict:
    cells = [c for c in scores["cells"] if c["quadrant"] == "Opportunity"]
    cells = sorted(cells, key=lambda c: c.get("priority_rank") or 999)[:top_n_cells]
    if not cells:
        return {}

    # index products by (category, tier)
    index = {}
    for category, data in processed_by_category.items():
        for sub in data.get("subcategories", []):
            index[(category, sub["price_tier"])] = pd.DataFrame(sub.get("products", []))

    budget = [page_budget]
    results = {}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        ctx = browser.new_context(
            viewport={"width": 1400, "height": 900},
            user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                        "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"),
        )
        page = ctx.new_page()

        for cell in cells:
            if budget[0] <= 0:
                break
            category, tier = cell["category"], cell["price_tier"]
            df = index.get((category, tier))
            if df is None or df.empty:
                continue
            key = f"{category}|{tier}"
            if status_callback:
                status_callback(f"Mining reviews: {category} / {tier}")
            print(f"  [reviews] {category} / {tier}")

            df = df[df["review_count"].fillna(0) > 0].sort_values("review_count", ascending=False)
            # Myntra lists every colourway of the same shoe as its own listing, so an
            # undeduplicated "top 3" is often the same model three times. Collapse on
            # brand+title so the three shown are genuinely different products.
            top3 = df.drop_duplicates(subset=["brand", "title"]).head(3).to_dict("records")

            focal_df = df[df["brand"].fillna("").str.strip().str.lower() == FOCAL_BRAND.lower()]
            focal_top = focal_df.drop_duplicates(subset=["brand", "title"]).head(1).to_dict("records")

            top_products = []
            for row in top3:
                if budget[0] <= 0:
                    break
                print(f"    top: {row['brand']} — {row['title']}")
                r = scrape_product_reviews(page, row["listing_id"], budget)
                top_products.append({**_product_payload(row), "reviews": r["reviews"]})

            focal_products = []
            for row in focal_top:
                if budget[0] <= 0:
                    break
                print(f"    {FOCAL_BRAND}: {row['title']}")
                r = scrape_product_reviews(page, row["listing_id"], budget)
                focal_products.append({**_product_payload(row), "reviews": r["reviews"]})

            results[key] = {
                "category": category,
                "price_tier": tier,
                "market_leader": cell.get("market_leader"),
                "top_products": top_products,
                "focal_products": focal_products,
            }

        browser.close()
    return results


def save_raw_reviews(results: dict, run_ts: str):
    REVIEWS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = REVIEWS_DIR / f"raw_reviews_{run_ts}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(f"    saved -> {out_path}")
    return out_path
