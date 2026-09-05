"""
Feature engineering.

Takes a raw scrape result (one category, containing one entry per price tier /
sub-category) and adds, per listing:
  - adjusted_rating: review-weighted rating shrunk toward the sub-category average, so a
    product with 5 reviews and a perfect score doesn't outrank one with 8,000 and 4.3
  - keyword_tags: cheap positioning fingerprint from the product title

plus, per category, focal_concentration_index — how concentrated the focal brand's
review volume is across its own SKUs (1.0 = one hero product carries everything).
"""

import json
from pathlib import Path

import pandas as pd

from config import FOCAL_BRAND

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"

KEYWORDS = [
    "boost", "air", "react", "gel", "foam", "knit", "mesh", "lightweight",
    "breathable", "cushioned", "flyknit", "primeknit",
]


def tag_keywords(title: str) -> list:
    if not title:
        return []
    t = title.lower()
    return [kw for kw in KEYWORDS if kw in t]


def adjusted_rating(df: pd.DataFrame) -> pd.Series:
    """Bayesian shrink toward the sub-category mean:
        adjusted = (v/(v+m)) * R + (m/(v+m)) * C
    R = raw rating, v = review count, C = sub-category mean rating,
    m = sub-category median review count (the shrinkage prior).
    """
    valid = df["rating"].dropna()
    C = valid.mean() if len(valid) else 0.0
    m = max(df["review_count"].median() if len(df) else 0.0, 1)

    def calc(row):
        r, v = row["rating"], row["review_count"]
        if pd.isna(r):
            return None
        return (v / (v + m)) * r + (m / (v + m)) * C

    return df.apply(calc, axis=1)


def focal_concentration_index(products: list) -> float:
    df = pd.DataFrame(products)
    if df.empty:
        return None
    focal = df[df["brand"].fillna("").str.strip().str.lower() == FOCAL_BRAND.lower()]
    total = focal["review_count"].sum()
    if total <= 0:
        return None
    shares = focal["review_count"] / total
    return float((shares ** 2).sum())


FOOTWEAR_HINTS = ("shoe", "sneaker", "boot", "sandal", "floater", "slipper", "flip-flop")


def footwear_only(df: pd.DataFrame) -> pd.DataFrame:
    """Drop products that are not footwear.

    Searching Myntra for "men football shoes" also returns actual footballs, and those
    carry real ratings — in Football Women they accounted for ~46% of listings, with two
    Puma footballs inflating Puma's apparent presence in the category. Product titles are
    truncated in the grid so they can't be trusted ("LeBron Witness 9 Basketball Sh"), but
    every product URL starts with Myntra's own article type — sports-shoes / casual-shoes
    for footwear, footballs / basketballs for the balls — which is reliable.
    """
    if df.empty or "url" not in df:
        return df
    seg = (df["url"].fillna("")
           .str.extract(r"myntra\.com/([^/]+)/", expand=False)
           .fillna("")
           .str.lower())
    keep = seg.apply(lambda s: any(h in s for h in FOOTWEAR_HINTS))
    return df[keep]


def collapse_colourways(df: pd.DataFrame) -> pd.DataFrame:
    """Myntra lists every colour of the same shoe as its own listing. Counting those as
    separate products makes a brand with eight colourways of one model look like eight
    products, inflating both shelf share and ratings share. Collapse on brand+title:
    ratings sum across colours, the best-reviewed colour represents the model, and
    sku_count records how many colourways sit behind it."""
    if df.empty:
        return df
    df = df.sort_values("review_count", ascending=False)

    rows = []
    for (brand, title), g in df.groupby(["brand", "title"], dropna=False, sort=False):
        lead = g.iloc[0]                       # best-reviewed colourway represents the model
        rated = g[g["rating"].notna() & (g["review_count"] > 0)]
        if not rated.empty:
            rating = float((rated["rating"] * rated["review_count"]).sum() / rated["review_count"].sum())
        else:
            rating = float(g["rating"].mean()) if g["rating"].notna().any() else None
        # Myntra lazy-loads card images, so a given colourway may have been captured
        # before its <img src> resolved — take the first colourway that does have one.
        imgs = g["image_url"].dropna() if "image_url" in g else pd.Series(dtype=object)
        imgs = [u for u in imgs if isinstance(u, str) and u.startswith("http")]
        rows.append({
            "listing_id": lead["listing_id"],
            "url": lead["url"],
            "image_url": imgs[0] if imgs else None,
            "brand": brand,
            "title": title,
            "price": float(g["price"].median()) if g["price"].notna().any() else None,
            "mrp": float(g["mrp"].median()) if g["mrp"].notna().any() else None,
            "discount_pct": float(g["discount_pct"].mean()) if g["discount_pct"].notna().any() else None,
            "rating": rating,
            "review_count": int(g["review_count"].sum()),
            "sponsored": bool(g["sponsored"].any()),
            "sku_count": int(len(g)),
            "category": lead["category"],
            "price_tier": lead["price_tier"],
        })
    return pd.DataFrame(rows)


def engineer_features(raw: dict) -> dict:
    subcategories = []
    all_products = []

    for sub in raw.get("subcategories", []):
        products = sub.get("products", [])
        if not products:
            subcategories.append({**sub, "products": [], "sku_listings": 0})
            continue

        df = pd.DataFrame(products)
        df["brand"] = df["brand"].fillna("Unknown").str.strip()
        df["review_count"] = df["review_count"].fillna(0).astype(int)

        df = footwear_only(df)
        if df.empty:
            subcategories.append({**sub, "products": [], "sku_listings": 0})
            continue

        sku_listings = int(len(df))
        df = collapse_colourways(df)

        df["adjusted_rating"] = adjusted_rating(df)
        df["keyword_tags"] = df["title"].apply(tag_keywords)

        enriched = df.to_dict(orient="records")
        subcategories.append({**sub, "products": enriched, "sku_listings": sku_listings})
        all_products.extend(enriched)

    return {
        "category": raw["category"],
        "search_term": raw["search_term"],
        "scraped_at": raw.get("scraped_at"),
        "focal_concentration_index": focal_concentration_index(all_products),
        "ad_landscape": raw.get("ad_landscape"),
        "subcategories": subcategories,
    }


def save_processed(result: dict, run_ts: str):
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    out_path = PROCESSED_DIR / f"{result['category']}_{run_ts}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False, default=lambda o: None if pd.isna(o) else o)
    print(f"    saved -> {out_path}")
    return out_path
