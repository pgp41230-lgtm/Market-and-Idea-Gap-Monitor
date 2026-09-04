"""One-off repair: fetch product images for the listings the dashboard actually shows.

Myntra lazy-loads card images, so a scrape taken before the fix in
myntra_scraper._load_lazy_images captured no <img src> for most cards. Images are only
rendered for the top products of each opportunity sub-category, so rather than re-scrape
everything we visit just those product pages and read their og:image.
"""

import json
import random
import sys
import time
from pathlib import Path

import pandas as pd
from playwright.sync_api import TimeoutError as PWTimeoutError, sync_playwright

from config import FOCAL_BRAND

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PROCESSED = PROJECT_ROOT / "data" / "processed"
SCORES = PROJECT_ROOT / "data" / "scores"

TOP_N = 3


def _needs_image(p) -> bool:
    u = p.get("image_url")
    return not (isinstance(u, str) and u.startswith("http"))


def _fetch_image(page, url) -> str:
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=25000)
        page.wait_for_timeout(700)
        return page.evaluate("""() => {
            const og = document.querySelector('meta[property="og:image"]');
            if (og && og.content) return og.content;
            const m = window.__myx && window.__myx.pdpData && window.__myx.pdpData.media;
            if (m && m.albums && m.albums[0] && m.albums[0].images && m.albums[0].images[0])
                return m.albums[0].images[0].secureSrc || m.albums[0].images[0].src;
            const img = document.querySelector('.image-grid-image, .image-grid-imageContainer img');
            if (img) {
                const bg = getComputedStyle(img).backgroundImage;
                const mm = bg && bg.match(/url\\("?(.*?)"?\\)/);
                if (mm) return mm[1];
                if (img.src) return img.src;
            }
            return null;
        }""")
    except PWTimeoutError:
        return None


def run(run_ts: str, headless: bool = False):
    scores = json.loads((SCORES / f"scores_{run_ts}.json").read_text(encoding="utf-8"))
    cells = [c for c in scores["cells"] if c["quadrant"] == "Opportunity" and not c.get("is_thin")]

    # which (category, tier) -> which listing_ids we actually display
    wanted = {}
    files = {}
    for cat in scores["categories"]:
        p = PROCESSED / f"{cat}_{run_ts}.json"
        files[cat] = json.loads(p.read_text(encoding="utf-8"))

    for cell in cells:
        cat, tier = cell["category"], cell["price_tier"]
        for sub in files[cat]["subcategories"]:
            if sub["price_tier"] != tier:
                continue
            df = pd.DataFrame(sub["products"])
            if df.empty:
                continue
            df = df[df["review_count"].fillna(0) > 0].sort_values("review_count", ascending=False)
            ids = list(df.head(TOP_N)["listing_id"])
            focal = df[df["brand"].fillna("").str.strip().str.lower() == FOCAL_BRAND.lower()]
            ids += list(focal.head(1)["listing_id"])
            wanted[(cat, tier)] = set(ids)

    todo = []
    for cat, data in files.items():
        for sub in data["subcategories"]:
            ids = wanted.get((cat, sub["price_tier"]))
            if not ids:
                continue
            for p in sub["products"]:
                if p["listing_id"] in ids and _needs_image(p) and p.get("url"):
                    todo.append((cat, sub["price_tier"], p))

    print(f"  {len(todo)} displayed products need an image")
    if not todo:
        return

    fixed = 0
    with sync_playwright() as pw:
        b = pw.chromium.launch(headless=headless)
        ctx = b.new_context(viewport={"width": 1400, "height": 900},
                            user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                                        "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"))
        page = ctx.new_page()
        for cat, tier, p in todo:
            img = _fetch_image(page, p["url"])
            if img:
                p["image_url"] = img
                fixed += 1
                print(f"    ok  {p['brand']} — {str(p['title'])[:40]}")
            else:
                print(f"    --  {p['brand']} — {str(p['title'])[:40]}")
            time.sleep(random.uniform(1.5, 3.0))
        b.close()

    for cat, data in files.items():
        (PROCESSED / f"{cat}_{run_ts}.json").write_text(
            json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"  backfilled {fixed}/{len(todo)} images")


if __name__ == "__main__":
    run(sys.argv[1] if len(sys.argv) > 1 else "2026-09-05_PILOT")
