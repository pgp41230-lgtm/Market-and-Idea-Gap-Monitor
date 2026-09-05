import os
import sys
from datetime import datetime
from pathlib import Path

import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scraper"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from config import FOCAL_BRAND
from data_loader import (data_fingerprint, load_bundle, load_raw_reviews,
                         load_review_analysis)
from theme import CSS

import page_analytics
import page_monitor
import page_opportunity

st.set_page_config(page_title=f"Market and Idea Gap Monitor — {FOCAL_BRAND}",
                   page_icon="◉", layout="wide",
                   initial_sidebar_state="collapsed")  # nav is an in-page column, not the sidebar
st.markdown(CSS, unsafe_allow_html=True)

PAGES = {
    "Idea Gap Monitor": page_monitor,
    "Opportunity Detailing": page_opportunity,
    "Sub-Category Analytics": page_analytics,
}

# each page is addressable as ?page=<slug> so a page can be linked or bookmarked
PAGE_SLUG = {
    "Idea Gap Monitor": "monitor",
    "Opportunity Detailing": "opportunity",
    "Sub-Category Analytics": "analytics",
}
SLUG_PAGE = {v: k for k, v in PAGE_SLUG.items()}


@st.cache_data(show_spinner=False, ttl=900)
def _bundle(fingerprint: str):
    """`fingerprint` is not used inside — it is the cache key, so that changing the data
    on disk invalidates this entry. The TTL is a backstop in case anything slips past it."""
    run_ts, scores, processed = load_bundle()
    if not run_ts:
        return None, None, None, {}, {}
    return run_ts, scores, processed, load_raw_reviews(run_ts), load_review_analysis(run_ts)


def is_hosted() -> bool:
    """True when running on a server rather than the user's own machine.

    Scraping Myntra needs a real, visible browser on a residential connection — Myntra
    is behind Akamai bot protection, which blocks headless browsers and datacenter IPs.
    So on a host the pipeline cannot run, and the Refresh control is replaced with an
    explanation instead of being left as a button that always fails.
    """
    if os.environ.get("GAPMONITOR_HOSTED", "").lower() in ("1", "true", "yes"):
        return True
    # Streamlit Community Cloud sets this on its runners
    return bool(os.environ.get("HOSTNAME", "").startswith("streamlit")
                or os.environ.get("STREAMLIT_RUNTIME_ENV") == "cloud")


def _run_refresh():
    from pipeline import run_pipeline
    with st.status("Refreshing data from Myntra…", expanded=True) as status:
        try:
            run_pipeline(status_callback=lambda m: st.write(m), headless=False)
            status.update(label="Refresh complete", state="complete")
        except Exception as e:
            status.update(label=f"Refresh failed: {e}", state="error")
            return
    st.cache_data.clear()
    st.rerun()


run_ts, scores, processed, reviews, analysis = _bundle(data_fingerprint())

# The nav is the first column of the page rather than Streamlit's sidebar: the sidebar
# can be collapsed and then offers no dependable way back, which hides all navigation.
nav_col, main_col = st.columns([1, 4.4], gap="large")

with nav_col:
    st.markdown('<div class="navcol-marker"></div>', unsafe_allow_html=True)
    st.markdown(
        f'<div class="brandmark">'
        f'<span class="puma">{FOCAL_BRAND.upper()}</span>'
        f'<div class="rule"></div>'
        f'<div class="wm"><b>Market and Idea Gap Monitor</b>'
        f'<span>Myntra Market Intelligence</span></div>'
        f'</div>', unsafe_allow_html=True)

    st.markdown('<div class="navlabel">Navigate</div>', unsafe_allow_html=True)
    # apply an in-page navigation request before the radio exists — a widget key cannot
    # be written once its widget has been instantiated
    goto = st.session_state.pop("_goto_page", None)
    if goto in PAGES:
        st.session_state["nav"] = goto
    elif "nav" not in st.session_state:
        slug = st.query_params.get("page")
        if slug in SLUG_PAGE:
            st.session_state["nav"] = SLUG_PAGE[slug]
    nav = st.radio("Navigation", list(PAGES.keys()), key="nav", label_visibility="collapsed")

    st.markdown('<div class="navlabel">Data</div>', unsafe_allow_html=True)
    if is_hosted():
        st.caption("This is a published snapshot. Myntra blocks automated traffic from "
                   "servers, so data is refreshed from a local machine and republished.")
    else:
        if st.button("Refresh from Myntra"):
            _run_refresh()
        st.caption("Re-scrapes every category and price band, then rescores. "
                   "Takes several minutes and opens a browser window.")

if st.query_params.get("page") != PAGE_SLUG[nav]:
    st.query_params["page"] = PAGE_SLUG[nav]

with main_col:
    if run_ts is None:
        st.markdown('<div class="ph"><h1>No data yet</h1>'
                    '<p>Run the pipeline to populate the dashboard.</p></div>',
                    unsafe_allow_html=True)
        st.info("Use **Refresh from Myntra** in the left panel to run the first scrape.")
        st.stop()

    # Derive the shown time from the run id, which is stamped when the scrape starts.
    # run_log's completed_at moves whenever the run is re-scored or annotated, so it
    # drifts away from when the data was actually captured.
    when = run_ts.replace("_", " ")
    try:
        when = datetime.strptime(run_ts, "%Y-%m-%d_%H%M").strftime("%d %b %Y, %H:%M")
    except ValueError:
        pass
    stamp = f'<div class="stamp"><i></i>Data last refreshed &nbsp;<b>{when}</b></div>'

    PAGES[nav].render(scores, processed, reviews, analysis, stamp)
