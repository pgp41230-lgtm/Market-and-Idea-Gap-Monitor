"""Shared UI blocks — most importantly the opportunity detail, which is rendered both
as a popup on the Idea Gap Monitor page and inline on the Opportunity Detailing page."""

import html

import pandas as pd
import streamlit as st

from data_loader import pretty_category, products_for
from theme import C

FOCAL = "Puma"


def esc(x):
    return html.escape(str(x)) if x is not None else ""


_EYE_SVG = (
    '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
    'stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
    '<path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/>'
    '<circle cx="12" cy="12" r="3"/></svg>'
)


def info(text: str, align: str = "center") -> str:
    """An eye icon that reveals an explanation on hover. `text` may contain <b>.

    align="right" for elements near the right edge, whose centred tooltip would
    otherwise be clipped by Streamlit's scroll container.
    """
    cls = {"right": " tip-right", "left": " tip-left"}.get(align, "")
    return f'<span class="info-icon{cls}">{_EYE_SVG}<span class="tip">{text}</span></span>'


def fmt_int(x):
    try:
        return f"{int(x):,}"
    except (TypeError, ValueError):
        return "—"


def fmt_pct(x, dp=1):
    try:
        return f"{float(x)*100:.{dp}f}%"
    except (TypeError, ValueError):
        return "—"


def fmt_rating(x):
    try:
        return f"{float(x):.2f}"
    except (TypeError, ValueError):
        return "—"


def tier_range(cell) -> str:
    lo, hi = cell.get("price_min"), cell.get("price_max")
    if lo is None:
        return ""
    return f"Rs {int(lo):,}+" if hi is None else f"Rs {int(lo):,} – {int(hi):,}"


def intensity_pill(intensity) -> str:
    cls = {"Fragmented": "frag", "Moderate": "mod", "Concentrated": "conc"}.get(intensity, "mod")
    return f'<span class="pill {cls}">{esc(intensity or "n/a")}</span>'


def _bullets(items):
    if not items:
        return '<li style="font-style:italic;color:#667085">Not yet analysed for this sub-category.</li>'
    return "".join(f"<li>{esc(i)}</li>" for i in items)


def product_card(p: dict) -> str:
    img = p.get("image_url")
    if not isinstance(img, str) or not img.startswith("http"):
        img = None                      # NaN / missing -> neutral placeholder, not a broken icon
    url = p.get("url") or "#"
    rating = fmt_rating(p.get("rating"))
    n = fmt_int(p.get("review_count"))
    price = f"Rs {int(p['price']):,}" if p.get("price") else ""
    visual = (f'<img src="{esc(img)}" alt="{esc(p.get("title"))}"/>' if img
              else '<div class="noimg">image unavailable</div>')
    return f"""
    <div class="prod">
      {visual}
      <div class="pb">
        <div class="br">{esc(p.get('brand'))}</div>
        <div class="tt">{esc((p.get('title') or '')[:58])}</div>
        <div class="mt"><span class="st">★ {rating}</span> · {n} ratings</div>
        <div class="mt" style="margin-top:3px;color:{C['muted']}">{price}</div>
        <div style="margin-top:8px"><a href="{esc(url)}" target="_blank">View on Myntra ↗</a></div>
      </div>
    </div>"""


def render_opportunity_detail(cell: dict, processed: dict, reviews: dict,
                              analysis: dict, show_analytics_link: bool = True):
    """The full insight for one opportunity sub-category."""
    key = f"{cell['category']}|{cell['price_tier']}"
    name = pretty_category(cell["category"])
    tier = cell["price_tier"]

    st.markdown(
        f"""<div style="margin-bottom:14px">
              <div style="font-size:1.15rem;font-weight:800;color:{C['ink']}">{esc(name)} · {esc(tier)}</div>
              <div style="font-size:.8rem;color:{C['muted']};margin-top:2px">
                Price band {esc(tier_range(cell))} &nbsp;·&nbsp; {fmt_int(cell.get('total_count_reported'))} listings on Myntra in this band
              </div>
            </div>""",
        unsafe_allow_html=True,
    )

    if cell.get("is_thin"):
        st.markdown(
            f'<div class="warn"><b>Thin category — read with care.</b> Myntra carries only '
            f'{fmt_int(cell.get("total_count_reported"))} listings in this band, so percentage '
            f'shares here can swing on a single product and are not a reliable market position.</div>',
            unsafe_allow_html=True)

    # --- market leader / structure -------------------------------------------------
    a, b, c, d = st.columns(4)
    a.markdown(f'<div class="tile"><div class="cap">Market leader</div>'
               f'<div class="big" style="font-size:1.25rem">{esc(cell.get("market_leader") or "—")}</div>'
               f'<div class="sub">{fmt_pct(cell.get("leader_share"),0)} of ratings volume</div></div>',
               unsafe_allow_html=True)
    b.markdown(f'<div class="tile"><div class="cap">Leader rating</div>'
               f'<div class="big" style="font-size:1.25rem">{fmt_rating(cell.get("leader_rating"))}</div>'
               f'<div class="sub">weighted across their listings</div></div>', unsafe_allow_html=True)
    c.markdown(f'<div class="tile"><div class="cap">Competition</div>'
               f'<div class="big" style="font-size:1.25rem">{esc(cell.get("competition_intensity") or "—")}</div>'
               f'<div class="sub">{cell.get("meaningful_brands", 0)} brands with real share</div></div>',
               unsafe_allow_html=True)
    focal_rt = cell.get("focal_weighted_rating")
    d.markdown(f'<div class="tile f"><div class="cap">{FOCAL} avg rating</div>'
               f'<div class="big" style="font-size:1.25rem">{fmt_rating(focal_rt)}</div>'
               f'<div class="sub">{cell.get("focal_listing_count",0)} listings · '
               f'{fmt_pct(cell.get("focal_share"))} of ratings</div></div>', unsafe_allow_html=True)

    # --- top 3 products ------------------------------------------------------------
    st.markdown('<hr class="sep"/>', unsafe_allow_html=True)
    st.markdown('<div class="ptitle">Top 3 products in this sub-category</div>'
                '<div class="psub">Ranked by number of customer ratings — what shoppers in this '
                'price band are actually buying.</div>', unsafe_allow_html=True)

    cat_df = products_for(processed, cell["category"], tier)

    def with_image(p: dict) -> dict:
        """The review-mining snapshot can pre-date an image backfill, so fill any missing
        image from the processed dataset by listing id."""
        u = p.get("image_url")
        if isinstance(u, str) and u.startswith("http"):
            return p
        if not cat_df.empty:
            match = cat_df[cat_df["listing_id"] == p.get("listing_id")]
            if not match.empty:
                cand = match.iloc[0].get("image_url")
                if isinstance(cand, str) and cand.startswith("http"):
                    return {**p, "image_url": cand}
        return p

    mined = reviews.get(key, {})
    top_products = mined.get("top_products")
    if not top_products:
        if not cat_df.empty:
            top_products = (cat_df[cat_df["review_count"].fillna(0) > 0]
                            .sort_values("review_count", ascending=False)
                            .drop_duplicates(subset=["brand", "title"])
                            .drop_duplicates(subset=["brand", "review_count"])
                            .head(3).to_dict("records"))
        else:
            top_products = []
    top_products = [with_image(p) for p in top_products]

    if top_products:
        cols = st.columns(3)
        for col, p in zip(cols, top_products[:3]):
            col.markdown(product_card(p), unsafe_allow_html=True)
    else:
        st.info("No rated products captured in this sub-category.")

    # --- pros / cons of the top 3 ---------------------------------------------------
    ana = analysis.get(key, {})
    st.markdown('<div style="height:16px"></div>', unsafe_allow_html=True)
    st.markdown('<div class="ptitle">What customers say about these leading products</div>'
                '<div class="psub">Themes mined from real Myntra review text across the three '
                'products above, combined.</div>', unsafe_allow_html=True)
    p1, p2 = st.columns(2)
    p1.markdown(f'<div class="pc pro"><h6>What works</h6><ul>{_bullets(ana.get("top_pros"))}</ul></div>',
                unsafe_allow_html=True)
    p2.markdown(f'<div class="pc con"><h6>What frustrates buyers</h6><ul>{_bullets(ana.get("top_cons"))}</ul></div>',
                unsafe_allow_html=True)

    # --- focal brand ----------------------------------------------------------------
    st.markdown('<hr class="sep"/>', unsafe_allow_html=True)
    focal_products = mined.get("focal_products") or []
    if cell.get("focal_listing_count", 0) == 0:
        st.markdown(f'<div class="warn"><b>{FOCAL} has no listings in this price band.</b> '
                    f'The themes above describe the demand {FOCAL} would be entering against — '
                    f'there is no {FOCAL} review evidence here to compare with.</div>',
                    unsafe_allow_html=True)
    else:
        label = f"{FOCAL}'s own position here"
        st.markdown(f'<div class="ptitle">{label}</div>'
                    f'<div class="psub">{FOCAL} carries {cell.get("focal_listing_count",0)} listings in this '
                    f'band with a {fmt_rating(focal_rt)} weighted rating '
                    f'({fmt_pct(cell.get("focal_share"))} of the band\'s ratings volume).</div>',
                    unsafe_allow_html=True)
        if focal_products:
            fc1, fc2 = st.columns([1, 2])
            with fc1:
                st.markdown(product_card(with_image(focal_products[0])), unsafe_allow_html=True)
            with fc2:
                q1, q2 = st.columns(2)
                q1.markdown(f'<div class="pc pro"><h6>{FOCAL} — praised for</h6>'
                            f'<ul>{_bullets(ana.get("focal_pros"))}</ul></div>', unsafe_allow_html=True)
                q2.markdown(f'<div class="pc con"><h6>{FOCAL} — criticised for</h6>'
                            f'<ul>{_bullets(ana.get("focal_cons"))}</ul></div>', unsafe_allow_html=True)
        else:
            q1, q2 = st.columns(2)
            q1.markdown(f'<div class="pc pro"><h6>{FOCAL} — praised for</h6>'
                        f'<ul>{_bullets(ana.get("focal_pros"))}</ul></div>', unsafe_allow_html=True)
            q2.markdown(f'<div class="pc con"><h6>{FOCAL} — criticised for</h6>'
                        f'<ul>{_bullets(ana.get("focal_cons"))}</ul></div>', unsafe_allow_html=True)

    st.markdown('<div style="height:10px"></div>', unsafe_allow_html=True)
    st.markdown('<div class="note">Review themes come from competitor and own-brand review text on '
                'Myntra — directional evidence of unmet need, not a controlled survey.</div>',
                unsafe_allow_html=True)

    if show_analytics_link:
        st.markdown('<div style="height:12px"></div>', unsafe_allow_html=True)
        if st.button(f"Open full analytics for {name} · {tier} →",
                     key=f"toanalytics_{key}", use_container_width=True):
            # "nav" is the sidebar radio's widget key and cannot be written once that
            # widget exists, so hand the request over in a plain key that app.py applies
            # on the next run before the radio is built.
            st.session_state["_goto_page"] = "Sub-Category Analytics"
            st.session_state["sel_category"] = cell["category"]
            st.session_state["sel_tier"] = tier
            st.rerun()
