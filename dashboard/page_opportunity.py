"""Page 2 — Opportunity Gap Detailing: the full insight for each prioritised opportunity."""

import streamlit as st

from components import FOCAL, esc, render_opportunity_detail, tier_range
from data_loader import pretty_category
from theme import C


def render(scores, processed, reviews, analysis, stamp_html):
    cells = scores["cells"]
    opps = sorted([c for c in cells if c["quadrant"] == "Opportunity"],
                  key=lambda c: c.get("priority_rank") or 999)

    st.markdown(
        f'<div class="ph"><h1>Opportunity Detailing</h1>'
        f'<p>For every prioritised gap: who leads it, what sells, what customers praise and '
        f'complain about, and where {FOCAL} stands.</p></div>', unsafe_allow_html=True)
    st.markdown(stamp_html, unsafe_allow_html=True)
    st.markdown('<div style="height:18px"></div>', unsafe_allow_html=True)

    if not opps:
        st.info("No opportunity sub-categories in this run.")
        return

    labels = [f"#{i}  {pretty_category(c['category'])} · {c['price_tier']}"
              for i, c in enumerate(opps, start=1)]

    # allow deep-linking in from the monitor page
    default = 0
    pre = st.session_state.pop("jump_to_opportunity", None)
    if pre:
        for i, c in enumerate(opps):
            if f"{c['category']}|{c['price_tier']}" == pre:
                default = i
                break

    choice = st.radio("Prioritised opportunity", labels, index=default,
                      horizontal=True, label_visibility="collapsed")
    cell = opps[labels.index(choice)]

    st.markdown('<div style="height:10px"></div>', unsafe_allow_html=True)
    with st.container():
        render_opportunity_detail(cell, processed, reviews, analysis, show_analytics_link=True)
