"""Page 3 — Sub-Category Analytics: brand structure, ratings, pricing and paid ads."""

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from components import FOCAL, esc, fmt_int, fmt_pct, fmt_rating, tier_range
from data_loader import pretty_category, products_for
from theme import C, brand_color

TOP_N = 8


def _brand_colors(brands):
    return {b: brand_color(b, i) for i, b in enumerate(brands)}


def render(scores, processed, reviews, analysis, stamp_html):
    cells = scores["cells"]
    st.markdown(
        '<div class="ph"><h1>Sub-Category Analytics</h1>'
        '<p>Brand structure, quality and pricing inside any single category and price band.</p></div>',
        unsafe_allow_html=True)
    st.markdown(stamp_html, unsafe_allow_html=True)
    st.markdown('<div style="height:16px"></div>', unsafe_allow_html=True)

    categories = sorted({c["category"] for c in cells})
    if not categories:
        st.info("No data.")
        return

    pre_cat = st.session_state.pop("sel_category", None)
    pre_tier = st.session_state.pop("sel_tier", None)

    c1, c2 = st.columns(2)
    cat_index = categories.index(pre_cat) if pre_cat in categories else 0
    category = c1.selectbox("Main category", categories, index=cat_index,
                            format_func=pretty_category)

    tiers = [c["price_tier"] for c in cells if c["category"] == category]
    order = ["Entry-Level", "Mid-Range", "Premium", "Pro-Tier"]
    tiers = sorted(set(tiers), key=lambda t: order.index(t) if t in order else 99)
    tier_index = tiers.index(pre_tier) if pre_tier in tiers else 0
    tier = c2.selectbox("Sub-category (price band)", tiers, index=tier_index)

    cell = next((c for c in cells if c["category"] == category and c["price_tier"] == tier), None)
    if cell is None:
        st.info("No data for that combination.")
        return

    brands = pd.DataFrame(cell.get("brands", []))
    if brands.empty:
        st.info("No brand data captured for this sub-category.")
        return

    df = products_for(processed, category, tier)

    # ---- context strip ----
    k1, k2, k3, k4 = st.columns(4)
    k1.markdown(f'<div class="tile"><div class="cap">Price band</div>'
                f'<div class="big" style="font-size:1.2rem">{esc(tier_range(cell))}</div>'
                f'<div class="sub">{esc(tier)}</div></div>', unsafe_allow_html=True)
    k2.markdown(f'<div class="tile"><div class="cap">Listings on Myntra</div>'
                f'<div class="big" style="font-size:1.2rem">{fmt_int(cell.get("total_count_reported"))}</div>'
                f'<div class="sub">{fmt_int(cell.get("total_listings"))} sampled</div></div>',
                unsafe_allow_html=True)
    k3.markdown(f'<div class="tile"><div class="cap">Ratings volume</div>'
                f'<div class="big" style="font-size:1.2rem">{fmt_int(cell.get("total_review_volume"))}</div>'
                f'<div class="sub">demand proxy</div></div>', unsafe_allow_html=True)
    k4.markdown(f'<div class="tile f"><div class="cap">{FOCAL} share</div>'
                f'<div class="big" style="font-size:1.2rem">{fmt_pct(cell.get("focal_share"))}</div>'
                f'<div class="sub">{cell.get("focal_listing_count",0)} listings</div></div>',
                unsafe_allow_html=True)

    st.markdown('<div style="height:20px"></div>', unsafe_allow_html=True)

    top = brands.head(TOP_N).copy()
    others_listings = brands.iloc[TOP_N:]["listing_share"].sum() if len(brands) > TOP_N else 0
    others_reviews = brands.iloc[TOP_N:]["review_share"].sum() if len(brands) > TOP_N else 0
    cmap = _brand_colors(list(top["brand"]) + ["All other brands"])
    cmap["All other brands"] = C["grey"]

    # ---- a) listings share (stacked 100% bar) ----
    st.markdown('<div class="ptitle">Share of listings in this sub-category</div>'
                '<div class="psub">How the shelf is split — what proportion of products on offer each '
                'brand accounts for.</div>', unsafe_allow_html=True)
    rows = [{"brand": r["brand"], "share": r["listing_share"]} for _, r in top.iterrows()]
    if others_listings > 0:
        rows.append({"brand": "All other brands", "share": float(others_listings)})
    sdf = pd.DataFrame(rows)
    fig = go.Figure()
    for _, r in sdf.iterrows():
        fig.add_bar(x=[r["share"]], y=["Listings"], orientation="h", name=r["brand"],
                    marker_color=cmap.get(r["brand"], C["grey"]),
                    hovertemplate=f"{r['brand']}: %{{x:.1%}}<extra></extra>",
                    text=f"{r['share']*100:.0f}%" if r["share"] >= 0.05 else "",
                    textposition="inside", insidetextanchor="middle")
    fig.update_layout(barmode="stack", height=150, xaxis_tickformat=".0%",
                      xaxis_title=None, yaxis_title=None, template="gapmon",
                      legend=dict(orientation="h", y=-0.45, font=dict(size=11)))
    st.plotly_chart(fig, use_container_width=True)

    # ---- b) ratings share ----
    g1, g2 = st.columns(2)
    with g1:
        st.markdown('<div class="ptitle">Brand share of ratings volume</div>'
                    '<div class="psub">Share of demand actually captured — a better read on traction '
                    'than shelf space.</div>', unsafe_allow_html=True)
        rows = [{"brand": r["brand"], "share": r["review_share"]} for _, r in top.iterrows()]
        if others_reviews > 0:
            rows.append({"brand": "All other brands", "share": float(others_reviews)})
        rdf = pd.DataFrame(rows).sort_values("share", ascending=True)
        fig = go.Figure(go.Bar(
            x=rdf["share"], y=rdf["brand"], orientation="h",
            marker_color=[cmap.get(b, C["grey"]) for b in rdf["brand"]],
            text=[f"{v*100:.1f}%" for v in rdf["share"]], textposition="outside",
            hovertemplate="%{y}: %{x:.1%}<extra></extra>"))
        fig.update_layout(height=340, xaxis_tickformat=".0%", template="gapmon",
                          xaxis_title=None, yaxis_title=None, showlegend=False,
                          xaxis_range=[0, min(1, rdf["share"].max() * 1.25)])
        st.plotly_chart(fig, use_container_width=True)

    # ---- c) weighted rating ----
    with g2:
        st.markdown('<div class="ptitle">Weighted average rating</div>'
                    '<div class="psub">Ratings pulled toward the sub-category mean by review count, so '
                    'thin-but-perfect scores do not outrank proven ones.</div>', unsafe_allow_html=True)
        rr = top.dropna(subset=["weighted_rating"]).sort_values("weighted_rating")
        if rr.empty:
            st.info("No rated listings here.")
        else:
            fig = go.Figure(go.Bar(
                x=rr["weighted_rating"], y=rr["brand"], orientation="h",
                marker_color=[cmap.get(b, C["grey"]) for b in rr["brand"]],
                text=[f"{v:.2f}" for v in rr["weighted_rating"]], textposition="outside",
                hovertemplate="%{y}: %{x:.2f}<extra></extra>"))
            lo = max(0, float(rr["weighted_rating"].min()) - 0.25)
            hi = min(5, float(rr["weighted_rating"].max()) + 0.25)
            fig.update_layout(height=340, template="gapmon", showlegend=False,
                              xaxis_title=None, yaxis_title=None, xaxis_range=[lo, hi])
            st.plotly_chart(fig, use_container_width=True)

    # ---- d) discount ----
    g3, g4 = st.columns(2)
    with g3:
        st.markdown('<div class="ptitle">Average discount depth</div>'
                    '<div class="psub">How hard each brand is discounting to hold this band.</div>',
                    unsafe_allow_html=True)
        dd = top.dropna(subset=["avg_discount_pct"]).sort_values("avg_discount_pct")
        if dd.empty:
            st.info("No discount data here.")
        else:
            fig = go.Figure(go.Bar(
                x=dd["avg_discount_pct"], y=dd["brand"], orientation="h",
                marker_color=[cmap.get(b, C["grey"]) for b in dd["brand"]],
                text=[f"{v*100:.0f}%" for v in dd["avg_discount_pct"]], textposition="outside",
                hovertemplate="%{y}: %{x:.1%}<extra></extra>"))
            fig.update_layout(height=340, template="gapmon", showlegend=False,
                              xaxis_tickformat=".0%", xaxis_title=None, yaxis_title=None,
                              xaxis_range=[0, min(1, float(dd["avg_discount_pct"].max()) * 1.25)])
            st.plotly_chart(fig, use_container_width=True)

    # ---- e) paid sponsorship (category level — see note below) ----
    with g4:
        st.markdown('<div class="ptitle">Brands buying paid placement</div>'
                    '<div class="psub">Listings carrying Myntra\'s "AD" marker. Myntra serves no ads '
                    'on price-filtered views, so this is sampled once across the whole category.</div>',
                    unsafe_allow_html=True)
        ad_land = (scores.get("ad_landscape") or {}).get(category) or {}
        ad_brands = ad_land.get("brands") or []
        if not ad_brands:
            st.markdown('<div class="note">No sponsored listings detected in '
                        f'{esc(pretty_category(category))} — nobody is buying placement here.</div>',
                        unsafe_allow_html=True)
        else:
            adf = pd.DataFrame(ad_brands)
            total_ads = int(adf["ad_listings"].sum())
            seen = ad_land.get("listings_seen") or 0
            st.markdown(f'<div class="warn"><b>{total_ads} sponsored listings</b> from '
                        f'{len(adf)} brands across {seen} cards in '
                        f'{esc(pretty_category(category))}.</div>', unsafe_allow_html=True)
            adf = adf.sort_values("ad_listings", ascending=False)
            fig = go.Figure(go.Bar(
                x=adf["ad_listings"], y=adf["brand"], orientation="h",
                marker_color=[brand_color(b, i) for i, b in enumerate(adf["brand"])],
                text=adf["ad_listings"], textposition="outside",
                hovertemplate="%{y}: %{x} sponsored listings<extra></extra>"))
            fig.update_layout(height=max(180, 34 * len(adf)), template="gapmon",
                              showlegend=False, xaxis_title=None, yaxis_title=None,
                              xaxis_range=[0, int(adf["ad_listings"].max()) * 1.3])
            st.plotly_chart(fig, use_container_width=True)

    # ---- full brand table ----
    st.markdown('<hr class="sep"/>', unsafe_allow_html=True)
    st.markdown('<div class="ptitle">Full brand breakdown</div>', unsafe_allow_html=True)
    tbl = brands.copy()
    tbl["Brand"] = tbl["brand"]
    tbl["Listings"] = tbl["listing_count"]
    tbl["Listing share"] = tbl["listing_share"].apply(lambda v: f"{v*100:.1f}%")
    tbl["Ratings volume"] = tbl["review_volume"].apply(lambda v: f"{int(v):,}")
    tbl["Ratings share"] = tbl["review_share"].apply(lambda v: f"{v*100:.1f}%")
    tbl["Weighted rating"] = tbl["weighted_rating"].apply(fmt_rating)
    tbl["Avg discount"] = tbl["avg_discount_pct"].apply(
        lambda v: "—" if pd.isna(v) else f"{v*100:.0f}%")
    # no "sponsored" column here: price-filtered views never carry ads, so it would be
    # structurally zero — paid placement is reported category-level in the panel above
    st.dataframe(tbl[["Brand", "Listings", "Listing share", "Ratings volume", "Ratings share",
                      "Weighted rating", "Avg discount"]],
                 hide_index=True, use_container_width=True)
