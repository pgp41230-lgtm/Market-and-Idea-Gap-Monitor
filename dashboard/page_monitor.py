"""Page 1 — Idea Gap Monitor: tiles, prioritisation matrix, ranked opportunities."""

import pandas as pd
import streamlit as st

from components import (FOCAL, esc, fmt_int, fmt_pct, info, intensity_pill,
                        render_opportunity_detail, tier_range)
from data_loader import pretty_category
from theme import C

QUAD_COPY = {
    "Opportunity": ("Grow here", "High demand, thin presence"),
    "Defend":      ("Protect", "High demand, strong presence"),
    "Deprioritise": ("Watch only", "Low demand, thin presence"),
    "Maintain":    ("Hold", "Low demand, strong presence"),
}


def _cell_names(cells, quadrant):
    names = []
    for c in cells:
        if c["quadrant"] != quadrant:
            continue
        label = f"{pretty_category(c['category'])} · {c['price_tier']}"
        if c.get("is_thin"):
            label += '  <span class="thin">thin data</span>'
        names.append(label)
    return sorted(names)


def _qbox(cells, quadrant, hot=False):
    title, sub = QUAD_COPY[quadrant]
    names = _cell_names(cells, quadrant)
    # names already carry a safe <span class="thin"> marker, so they are inserted as-is
    body = ("".join(f"<li>{n}</li>" for n in names)
            if names else '<div class="none">None in this run</div>')
    inner = f"<ul>{body}</ul>" if names else body
    return (f'<div class="qbox{" hot" if hot else ""}">'
            f'<h5>{title}</h5><div class="qh">{sub} · {len(names)} sub-categories</div>'
            f'{inner}</div>')


@st.dialog("Opportunity detail", width="large")
def _detail_dialog(cell, processed, reviews, analysis):
    render_opportunity_detail(cell, processed, reviews, analysis, show_analytics_link=True)


def render(scores, processed, reviews, analysis, stamp_html):
    summary = scores["summary"]
    cells = scores["cells"]

    st.markdown(
        f'<div class="ph"><h1>Idea Gap Monitor</h1>'
        f'<p>Where {FOCAL} should grow, defend or leave alone across every '
        f'category and price band on Myntra.</p></div>', unsafe_allow_html=True)
    st.markdown(stamp_html, unsafe_allow_html=True)

    # ---- methodology ----
    st.markdown(
        '<div class="method"><span class="mlabel">How this was built</span><ul>'
        '<li>Each <b>sub-category</b> (a category at one price band) is searched on Myntra with the '
        '<b>price slider set to that band</b> and results <b>sorted by Popularity</b>; the '
        '<b>first 5 result pages</b> are captured.</li>'
        '<li>Multiple colour-option listings of the same shoe are merged into one product, so a brand '
        'with eight colours of one model is not counted as eight products.</li>'
        f'<li><b>Demand</b> for the sub-category is proxied by total customer ratings in the band, and '
        f'<b>{FOCAL}\'s presence</b> by {FOCAL}\'s share of those ratings. Myntra does not publish sales '
        'figures, so ratings are taken as a good proxy.</li>'
        '<li>Bands with under 50 listings in a sub-category are marked <i>thin data</i>, highlighting '
        'low product listings.</li>'
        '<li>Review themes are read from real review text on each band\'s best-selling products.</li>'
        '</ul></div>', unsafe_allow_html=True)
    st.markdown('<div style="height:14px"></div>', unsafe_allow_html=True)

    # ---- tiles ----
    t1, t2, t3, t4 = st.columns(4)
    t1.markdown(f'<div class="tile"><div class="cap">Categories considered'
                + info('A <b>category</b> is one shoe use-case type for one gender — Running Men, '
                       'Running Women, Basketball Men, Basketball Women and so on.')
                + f'</div><div class="big">{summary["n_categories"]}</div>'
                f'<div class="sub">gender-split shoe categories</div></div>', unsafe_allow_html=True)
    t2.markdown(f'<div class="tile"><div class="cap">Sub-categories'
                + info('A <b>sub-category</b> is a category at one price band — for example Running Men '
                       'at Rs 3,500-8,000.')
                + f'</div><div class="big">{summary["n_subcategories"]}</div>'
                f'<div class="sub">category × price band</div></div>', unsafe_allow_html=True)
    t3.markdown(f'<div class="tile a"><div class="cap">Opportunities identified'
                + info('Sub-categories where <b>demand for the sub-category is above the median</b> but '
                       f'<b>{FOCAL}\'s share is below it</b>. These are the "grow here" cells.')
                + f'</div><div class="big">{summary["n_opportunities"]}</div>'
                f'<div class="sub">high demand, thin {FOCAL} presence</div></div>', unsafe_allow_html=True)
    t4.markdown(f'<div class="tile f"><div class="cap">{FOCAL} overall share'
                + info(f'{FOCAL}\'s share of <b>overall customer ratings</b> captured across every '
                       'sub-category. Ratings are used as the demand proxy throughout because Myntra '
                       'publishes no sales figures; a rating is left by a verified buyer, so it tracks '
                       'purchases. Read it as relative traction, not market share in units.',
                       align="right")
                + f'</div><div class="big">{fmt_pct(summary["focal_overall_share"])}</div>'
                f'<div class="sub">of all ratings captured</div></div>', unsafe_allow_html=True)

    st.markdown('<div style="height:22px"></div>', unsafe_allow_html=True)

    # ---- 2x2 matrix ----
    # Built as one unbroken string: any newline + indentation here would be treated as a
    # markdown code block and the grid would fall apart.
    matrix = (
        '<div class="panel">'
        '<div class="ptitle">Sub-Category Wise Prioritization Matrix'
        + info('A classic two-by-two. The <b>vertical axis</b> is category demand, for which total '
               'customer ratings in that sub-category is taken as the proxy. The <b>horizontal axis</b> '
               f'is how much of that demand {FOCAL} already holds — barely present, or strong presence. '
               'Both axes are split at the <b>median across all sub-categories</b>, so each cell is '
               'judged against the other sub-category markets rather than an arbitrary threshold.')
        + '</div>'
        f'<div class="psub">Every sub-category placed by how much demand it carries and how much '
        f'of that demand {FOCAL} currently holds. The amber cell is where to grow.</div>'
        '<div class="mx">'
        '<div class="ylab">High category demand</div>'
        + _qbox(cells, "Opportunity", hot=True)
        + _qbox(cells, "Defend")
        + '<div class="ylab">Low category demand</div>'
        + _qbox(cells, "Deprioritise")
        + _qbox(cells, "Maintain")
        + '</div>'
        '<div class="axrow"><div></div>'
        f'<div>{FOCAL} barely has presence</div>'
        f'<div>{FOCAL} has strong presence</div>'
        '</div></div>'
    )
    st.markdown(matrix, unsafe_allow_html=True)

    # ---- ranked opportunities ----
    opps = sorted([c for c in cells
                   if c["quadrant"] == "Opportunity" and not c.get("is_thin")],
                  key=lambda c: c.get("priority_rank") or 999)
    thin_opps = [c for c in cells if c["quadrant"] == "Opportunity" and c.get("is_thin")]

    st.markdown('<div style="height:8px"></div>', unsafe_allow_html=True)
    st.markdown('<div class="ptitle">Prioritised opportunities'
                + info('Only the "grow here" sub-categories are ranked, by <b>demand × (1 − '
                       f'{FOCAL}\'s share)</b>. The first term is the size of the market; the second is '
                       f'how much of it is still unclaimed by {FOCAL}. Multiplying them favours big '
                       'markets where the brand is genuinely absent over small ones, or over ones where '
                       f'{FOCAL} is already present with a substantial share even though it sits below '
                       'the median.')
                + '</div>'
                f'<div class="psub">Ranked by the size of the prize — how much demand sits in the band '
                f'weighted by how much room {FOCAL} has to gain. Open any one for the full insight.</div>',
                unsafe_allow_html=True)

    if thin_opps:
        names = ", ".join(f"{pretty_category(c['category'])} · {c['price_tier']}" for c in thin_opps)
        st.markdown(f'<div class="warn"><b>Excluded from ranking — too few listings to judge:</b> '
                    f'{esc(names)}. Myntra carries under 50 products in these bands, so percentage '
                    f'shares there swing on one or two items.</div>', unsafe_allow_html=True)

    if not opps:
        st.info("No opportunity sub-categories with enough listings to rank in this run.")
        return

    for i, cell in enumerate(opps, start=1):
        sc = cell.get("scenario") or {}
        key = f"{cell['category']}|{cell['price_tier']}"
        card = (
            '<div class="oppcard">'
            f'<div><span class="rk">{i}</span>'
            f'<span class="nm">{esc(pretty_category(cell["category"]))} · {esc(cell["price_tier"])}</span>'
            f'<span class="band">{esc(tier_range(cell))}</span>'
            f'{intensity_pill(cell.get("competition_intensity"))}</div>'
            '<div class="sc">'
            f'<b>Market leader.</b> {esc(sc.get("leader",""))}<br/>'
            f'<b>Competitive intensity.</b> {esc(sc.get("competition",""))}<br/>'
            f'<b>{FOCAL} today.</b> {esc(sc.get("focal",""))}'
            '</div></div>'
        )
        st.markdown(card, unsafe_allow_html=True)
        if st.button("View detailed insight →", key=f"open_{key}"):
            _detail_dialog(cell, processed, reviews, analysis)

    st.markdown('<div style="height:6px"></div>', unsafe_allow_html=True)
    st.markdown('<div class="note">Point-in-time snapshot. Demand is proxied by customer ratings '
                'volume (not verified sales); each sub-category was scraped with Myntra\'s price '
                'slider set to that band, sorted by Popularity, first 5 result pages.</div>',
                unsafe_allow_html=True)
