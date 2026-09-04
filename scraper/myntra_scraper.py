"""
Myntra scraper — sub-category level.

Terminology used throughout the project:
  category      e.g. "running_men"  (a search term + gender)
  sub-category  a category at one price tier, e.g. "running_men / Mid-Range"

For every sub-category we load the category's Myntra listing page with the PRICE
slider filter applied to that tier's range (taken from data/price_tier_table.json,
which comes from the user's Footwear_Price_Tiers.xlsx), then capture the first 5
result pages.

The price filter is applied through the URL. Myntra encodes the price-slider state
in a `rf` (range filter) query param:

    ?rf=Price:{lo}.0_{hi}.0_{lo}.0 TO {hi}.0

which is exactly what dragging the slider in the UI produces (verified by driving the
slider and reading back the resulting URL). Note it is `rf`, not `f` — `f=Price:...`
silently returns nothing. Open-ended top tiers ("Rs 13,000+") use a high upper bound.

Myntra is a JS-rendered SPA behind Akamai bot protection. Pagination only happens by
clicking `.pagination-next` (the `?p=` param is silently ignored), so this drives a
real non-headless Chromium and reads the DOM after each click.
"""

import json
import random
import re
import time
from datetime import datetime
from pathlib import Path

from playwright.sync_api import Page, TimeoutError as PWTimeoutError, sync_playwright

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = PROJECT_ROOT / "data" / "raw"
TIER_TABLE_PATH = PROJECT_ROOT / "data" / "price_tier_table.json"

PAGES_PER_SUBCATEGORY = 5
OPEN_ENDED_MAX = 99999
DELAY_RANGE = (2.0, 5.0)
MAX_RETRIES = 3

# Scope: five categories, each split by gender. Training/Gym, Hiking/Outdoor and
# Badminton were dropped from the original brief's eight at the user's request.
CATEGORIES = {
    "running_men": "men running shoes",
    "running_women": "women running shoes",
    "basketball_men": "men basketball shoes",
    "basketball_women": "women basketball shoes",
    "casual_men": "men casual sneakers",
    "casual_women": "women casual sneakers",
    "football_men": "men football shoes",
    "football_women": "women football shoes",
    "walking_men": "men walking shoes",
    "walking_women": "women walking shoes",
}

PILOT_CATEGORIES = {
    k: CATEGORIES[k]
    for k in ("running_men", "running_women", "basketball_men", "basketball_women")
}

EXTRACT_JS = """
() => {
  const cards = document.querySelectorAll('li.product-base');
  return Array.from(cards).map(c => {
    const brand = c.querySelector('.product-brand')?.textContent?.trim() || null;
    const title = c.querySelector('.product-product')?.textContent?.trim() || null;
    // Myntra uses two price layouts: discounted items get .product-discountedPrice +
    // .product-strike, while full-price items render a bare <span>Rs. 3695</span> with
    // neither class. Taking the FIRST number in .product-price covers both, since the
    // selling price always comes first.
    const priceBlockText = c.querySelector('.product-price')?.textContent?.trim() || null;
    const mrpText = c.querySelector('.product-strike')?.textContent?.trim() || null;
    const ratingContainer = c.querySelector('.product-ratingsContainer');
    let rating = null, reviewCount = null;
    if (ratingContainer) {
      const directSpans = Array.from(ratingContainer.children).filter(el => el.tagName === 'SPAN' && !el.className.includes('starIcon'));
      if (directSpans.length > 0) rating = directSpans[0].textContent.trim();
      const rc = ratingContainer.querySelector('.product-ratingsCount');
      if (rc) reviewCount = rc.textContent.replace('|', '').trim();
    }
    const sponsored = !!c.querySelector('.product-waterMark');
    const href = c.querySelector('a')?.getAttribute('href') || null;
    const img = c.querySelector('img')?.getAttribute('src') || null;
    return { id: c.id, brand, title, priceBlockText, mrpText, rating, reviewCount, sponsored, href, img };
  });
}
"""


def load_tier_table() -> dict:
    with open(TIER_TABLE_PATH, encoding="utf-8") as f:
        return json.load(f)


def _delay():
    time.sleep(random.uniform(*DELAY_RANGE))


def _parse_int(text):
    if not text:
        return None
    digits = re.sub(r"[^\d]", "", text)
    return int(digits) if digits else None


def _parse_rating(text):
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def build_filtered_url(search_term: str, lo: int, hi) -> str:
    """Category page with the PRICE slider set to this tier and Sort by = Popularity."""
    slug = search_term.replace(" ", "-")
    hi = OPEN_ENDED_MAX if hi is None else hi
    rf = f"Price:{float(lo)}_{float(hi)}_{float(lo)} TO {float(hi)}"
    from urllib.parse import quote
    return f"https://www.myntra.com/{slug}?rf={quote(rf, safe='')}&sort=popularity"


def _get_total_count(page: Page):
    try:
        text = page.locator(".title-count").first.text_content(timeout=5000) or ""
        m = re.search(r"([\d,]+)\s*items?", text, re.IGNORECASE)
        if m:
            return int(m.group(1).replace(",", ""))
    except PWTimeoutError:
        pass
    return None


def _first_number(text):
    if not text:
        return None
    m = re.search(r"[\d,]+", text)
    return int(m.group(0).replace(",", "")) if m else None


def _normalize(card, category, tier_label, page_num):
    price = _first_number(card["priceBlockText"])
    mrp = _parse_int(card["mrpText"]) or price
    discount_pct = None
    if price is not None and mrp:
        discount_pct = round((mrp - price) / mrp, 4) if mrp > 0 else None
    href = card["href"]
    return {
        "listing_id": card["id"],
        "url": f"https://www.myntra.com/{href}" if href and not href.startswith("http") else href,
        "image_url": card["img"],
        "brand": card["brand"],
        "title": card["title"],
        "price": price,
        "mrp": mrp,
        "discount_pct": discount_pct,
        "rating": _parse_rating(card["rating"]),
        "review_count": _parse_int(card["reviewCount"]) or 0,
        "sponsored": card["sponsored"],
        "category": category,
        "price_tier": tier_label,
        "page": page_num,
    }


def _load_lazy_images(page: Page):
    """Card images are lazy-loaded, so extracting straight after page load leaves the
    <img src> empty for everything below the fold. Sweep down the grid and back up so
    every card has resolved its image before we read the DOM."""
    try:
        page.evaluate("""async () => {
            const step = window.innerHeight * 0.9;
            for (let y = 0; y < document.body.scrollHeight; y += step) {
                window.scrollTo(0, y);
                await new Promise(r => setTimeout(r, 160));
            }
            window.scrollTo(0, 0);
            await new Promise(r => setTimeout(r, 250));
        }""")
    except PWTimeoutError:
        pass


def _click_next(page: Page) -> bool:
    next_btn = page.locator(".pagination-next")
    if next_btn.count() == 0:
        return False
    if "disabled" in (next_btn.get_attribute("class") or "").lower():
        return False
    first_id_before = page.locator("li.product-base").first.get_attribute("id")
    next_btn.scroll_into_view_if_needed()
    next_btn.click()
    try:
        page.wait_for_function(
            """(prevId) => {
                const first = document.querySelector('li.product-base');
                return first && first.id !== prevId;
            }""",
            arg=first_id_before,
            timeout=15000,
        )
    except PWTimeoutError:
        return False
    return True


def scrape_subcategory(page: Page, category: str, search_term: str, tier: dict) -> dict:
    url = build_filtered_url(search_term, tier["min"], tier["max"])
    label = tier["label"]
    print(f"    [{category} / {label}] {tier['min']}-{tier['max'] or 'max'}")

    products = []
    total_count = None

    empty = {
        "category": category, "price_tier": label,
        "price_min": tier["min"], "price_max": tier["max"],
        "total_count_reported": 0, "pages_scraped": 0, "products": [],
    }

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_selector("li.product-base", timeout=20000)
            break
        except Exception as e:
            # Catch every navigation failure, not just timeouts: a transient DNS blip
            # raises ERR_NAME_NOT_RESOLVED, which is a plain playwright Error and used
            # to abort the whole category. Back off longer so a brief network drop has
            # time to recover.
            if attempt == MAX_RETRIES:
                print(f"      giving up on this band after {MAX_RETRIES} tries: "
                      f"{str(e).splitlines()[0][:110]}")
                return empty
            time.sleep(5 * attempt)

    total_count = _get_total_count(page)

    page_num = 0
    for page_num in range(1, PAGES_PER_SUBCATEGORY + 1):
        _delay()
        _load_lazy_images(page)
        cards = page.evaluate(EXTRACT_JS)
        for card in cards:
            products.append(_normalize(card, category, label, page_num))
        print(f"      page {page_num}: {len(cards)} listings")

        if page_num == PAGES_PER_SUBCATEGORY:
            break
        advanced = False
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                advanced = _click_next(page)
                break
            except PWTimeoutError:
                time.sleep(2 * attempt)
        if not advanced:
            break

    return {
        "category": category,
        "price_tier": label,
        "price_min": tier["min"],
        "price_max": tier["max"],
        "total_count_reported": total_count,
        "pages_scraped": page_num,
        "products": products,
    }


def scrape_ad_landscape(page: Page, category: str, search_term: str, pages: int = 2) -> dict:
    """Who is paying for placement in this category.

    Myntra serves sponsored (PLA) cards only on the UNFILTERED category listing — apply
    the price slider and every "AD" marker disappears (verified: 18 ads on the plain
    men's running page, 0 on the same page price-filtered). So paid placement has to be
    sampled once per category, without the price filter, and is therefore reported at
    category level rather than per price band.
    """
    slug = search_term.replace(" ", "-")
    url = f"https://www.myntra.com/{slug}"
    counts, seen = {}, 0
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_selector("li.product-base", timeout=20000)
    except PWTimeoutError:
        return {"brands": [], "listings_seen": 0, "ad_listings": 0}

    for i in range(pages):
        _delay()
        cards = page.evaluate(EXTRACT_JS)
        seen += len(cards)
        for c in cards:
            if c["sponsored"] and c["brand"]:
                counts[c["brand"]] = counts.get(c["brand"], 0) + 1
        if i == pages - 1 or not _click_next(page):
            break

    brands = [{"brand": b, "ad_listings": n} for b, n in
              sorted(counts.items(), key=lambda kv: kv[1], reverse=True)]
    total = sum(counts.values())
    print(f"    [ads] {category}: {total} sponsored listings from {len(brands)} brands "
          f"across {seen} cards")
    return {"brands": brands, "listings_seen": seen, "ad_listings": total}


def scrape_category(page: Page, category: str, search_term: str, tiers: list) -> dict:
    print(f"  [scrape] {category} ({search_term})")
    subcategories = []
    for tier in tiers:
        # isolate each band: one failing price band should not cost us the other three
        try:
            subcategories.append(scrape_subcategory(page, category, search_term, tier))
        except Exception as e:
            print(f"      [ERROR] {category}/{tier['label']}: {str(e).splitlines()[0][:110]}")
            subcategories.append({
                "category": category, "price_tier": tier["label"],
                "price_min": tier["min"], "price_max": tier["max"],
                "total_count_reported": 0, "pages_scraped": 0, "products": [],
            })
        _delay()
    try:
        ad_landscape = scrape_ad_landscape(page, category, search_term)
    except Exception as e:
        print(f"      [ERROR] {category} ad landscape: {str(e).splitlines()[0][:110]}")
        ad_landscape = {"brands": [], "listings_seen": 0, "ad_listings": 0}
    _delay()
    return {
        "category": category,
        "search_term": search_term,
        "scraped_at": datetime.now().isoformat(),
        "subcategories": subcategories,
        "ad_landscape": ad_landscape,
    }


def save_raw(result: dict, run_ts: str):
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    out_path = RAW_DIR / f"{result['category']}_{run_ts}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    print(f"    saved -> {out_path}")
    return out_path


def run(categories: dict = None, headless: bool = False, run_ts: str = None, status_callback=None):
    categories = categories or PILOT_CATEGORIES
    run_ts = run_ts or datetime.now().strftime("%Y-%m-%d_%H%M")
    tier_table = load_tier_table()
    results = {}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        context = browser.new_context(
            viewport={"width": 1400, "height": 900},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
            ),
        )
        page = context.new_page()
        for key, term in categories.items():
            tiers = tier_table.get(key)
            if not tiers:
                print(f"  [skip] no price tiers defined for {key}")
                continue
            if status_callback:
                status_callback(f"Scraping {key} ({len(tiers)} price tiers)...")
            try:
                result = scrape_category(page, key, term, tiers)
                save_raw(result, run_ts)
                results[key] = result
            except Exception as e:
                print(f"  [ERROR] {key} failed: {e}")
                results[key] = {"error": str(e)}
        browser.close()

    return results


if __name__ == "__main__":
    run()
