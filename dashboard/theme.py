"""Visual system for the dashboard: palette, plotly template, CSS."""

import sys
from pathlib import Path

import plotly.graph_objects as go
import plotly.io as pio

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scraper"))
from config import FOCAL_BRAND

C = {
    "ink": "#101828",
    "body": "#344054",
    "muted": "#667085",
    "line": "#E4E7EC",
    "surface": "#FFFFFF",
    "canvas": "#F7F8FA",
    "nav": "#0E1726",
    "nav_hover": "#1B2637",
    "focal": "#D6202B",       # focal-brand accent
    "focal_soft": "#FDECEC",
    "blue": "#2B5CE6",
    "blue_soft": "#EAF0FE",
    "green": "#0E9F6E",
    "green_soft": "#E7F7F0",
    "amber": "#D97706",
    "amber_soft": "#FEF3E2",
    "grey": "#98A2B3",
}

QUADRANT = {
    "Opportunity": C["amber"],
    "Defend": C["blue"],
    "Maintain": C["green"],
    "Deprioritise": C["grey"],
}

BRAND_PALETTE = [
    "#2B5CE6", "#0E9F6E", "#7A5AF8", "#D97706", "#0BA5EC",
    "#EE46BC", "#4E5BA6", "#12B76A", "#F79009", "#6172F3",
    "#875BF7", "#15B79E",
]

FONT = "'Inter', 'Segoe UI', system-ui, sans-serif"

pio.templates["gapmon"] = go.layout.Template(
    layout=go.Layout(
        font=dict(family=FONT, color=C["body"], size=13),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        colorway=BRAND_PALETTE,
        xaxis=dict(gridcolor="#F0F2F5", linecolor=C["line"], zerolinecolor="#F0F2F5"),
        yaxis=dict(gridcolor="#F0F2F5", linecolor=C["line"], zerolinecolor="#F0F2F5"),
        legend=dict(bgcolor="rgba(0,0,0,0)"),
        margin=dict(l=8, r=8, t=30, b=8),
    )
)


def brand_color(brand: str, i: int = 0) -> str:
    if (brand or "").strip().lower() == FOCAL_BRAND.lower():
        return C["focal"]
    return BRAND_PALETTE[i % len(BRAND_PALETTE)]


CSS = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

html, body, [class*="css"], .stMarkdown {{ font-family: {FONT}; }}

/* ---------- shell ---------- */
.stApp {{ background: {C["canvas"]}; }}
.main .block-container {{ padding: 2rem 2.4rem 4rem; max-width: 1420px; }}
#MainMenu, footer, header {{ visibility: hidden; }}

/* ---------- left nav lives in the page, not Streamlit's sidebar ----------
   The sidebar can be collapsed by the user and then has no reliable way back, which
   hides the only navigation and makes the three sections look like separate apps.
   So the sidebar is removed entirely and the nav is rendered as the first column of
   the page, where it cannot be dismissed. */
section[data-testid="stSidebar"] {{ display: none !important; }}
[data-testid="stSidebarCollapsedControl"],
[data-testid="collapsedControl"] {{ display: none !important; }}

/* the nav column is identified by a marker element it renders, so these rules cannot
   leak onto the first column of other row layouts (KPI tiles, chart pairs, etc.) */
div[data-testid="stColumn"]:has(.navcol-marker) {{
    background: {C["nav"]};
    border-radius: 16px;
    padding: 20px 16px 22px;
    position: sticky;
    top: 14px;
    align-self: flex-start;
}}
.navcol-marker {{ display: none; }}

.brandmark {{ padding: 2px 4px 18px; }}
.brandmark .puma {{
    color:#fff; font-size:1.5rem; font-weight:800; letter-spacing:.16em;
    line-height:1; display:block;
}}
.brandmark .wm {{ line-height:1.25; margin-top:7px; }}
.brandmark .wm b {{ color:#C7CEDB; font-size:.78rem; font-weight:700; display:block;
                    letter-spacing:.01em; }}
.brandmark .wm span {{ color:#66738A; font-size:.6rem; letter-spacing:.13em;
                       text-transform:uppercase; font-weight:600; }}
.brandmark .rule {{ height:2px; width:34px; background:#fff; margin:9px 0 0; opacity:.85; }}

/* ---------- info tooltips ---------- */
.info-icon {{
    position:relative; display:inline-block; margin-left:6px; cursor:help;
    vertical-align:middle; opacity:.45; transition:opacity .12s;
}}
.info-icon:hover {{ opacity:1; }}
.info-icon svg {{ display:block; }}
.info-icon .tip {{
    visibility:hidden; opacity:0; position:absolute; z-index:9999;
    left:50%; transform:translateX(-50%); bottom:150%; width:310px;
    background:{C["nav"]}; color:#E7EAF0; padding:11px 13px; border-radius:9px;
    font-size:.74rem; font-weight:500; line-height:1.5; letter-spacing:0;
    text-transform:none; text-align:left; white-space:normal;
    box-shadow:0 10px 28px rgba(16,24,40,.28); transition:opacity .12s;
}}
.info-icon:hover .tip {{ visibility:visible; opacity:1; }}
.info-icon .tip b {{ color:#fff; }}
/* Streamlit's scroll container clips absolutely-positioned children, so a centred
   tooltip on a right-hand card would be cut off. Anchor those to the right instead. */
.info-icon.tip-right .tip {{ left:auto; right:-6px; transform:none; }}
.info-icon.tip-left .tip {{ left:-6px; right:auto; transform:none; }}
/* tooltips must escape their card, so nothing in the chain may clip */
.tile, .panel, div[data-testid="stColumn"] {{ overflow: visible !important; }}

/* ---------- methodology strip ---------- */
.method {{
    background:{C["surface"]}; border:1px solid {C["line"]}; border-radius:12px;
    padding:13px 16px; margin:10px 0 4px; font-size:.78rem; color:{C["body"]};
    line-height:1.6;
}}
.method b {{ color:{C["ink"]}; font-weight:700; }}
.method .mlabel {{ font-size:.63rem; letter-spacing:.11em; text-transform:uppercase;
                   color:{C["muted"]}; font-weight:700; display:block; margin-bottom:7px; }}
.method ul {{ margin:0; padding-left:18px; }}
.method li {{ margin-bottom:5px; }}
.method li:last-child {{ margin-bottom:0; }}

.navlabel {{ color:#66738A !important; font-size:.62rem; letter-spacing:.13em;
             text-transform:uppercase; font-weight:700; padding:14px 6px 6px; }}

/* nav radio -> nav rows */
div[data-testid="stColumn"]:has(.navcol-marker) div[role="radiogroup"] {{ gap: 3px; }}
div[data-testid="stColumn"]:has(.navcol-marker) div[role="radiogroup"] label {{
    padding: 9px 12px; border-radius: 9px; cursor: pointer;
    transition: background .13s ease; margin: 0; width: 100%;
}}
div[data-testid="stColumn"]:has(.navcol-marker) div[role="radiogroup"] label:hover {{ background: {C["nav_hover"]}; }}
div[data-testid="stColumn"]:has(.navcol-marker) div[role="radiogroup"] label p {{
    font-size: .875rem !important; font-weight: 600 !important; color:#C7CEDB !important;
}}
div[data-testid="stColumn"]:has(.navcol-marker) div[role="radiogroup"] label:has(input:checked) {{
    background: rgba(214,32,43,.16); box-shadow: inset 2px 0 0 {C["focal"]};
}}
div[data-testid="stColumn"]:has(.navcol-marker) div[role="radiogroup"] label:has(input:checked) p {{ color:#fff !important; }}
div[data-testid="stColumn"]:has(.navcol-marker) div[role="radiogroup"] input {{ display:none; }}

div[data-testid="stColumn"]:has(.navcol-marker) .stButton button {{
    background: {C["focal"]}; color:#fff; border:none; border-radius:9px;
    font-weight:700; font-size:.83rem; padding:.55rem 0; width:100%;
}}
div[data-testid="stColumn"]:has(.navcol-marker) .stButton button:hover {{ background:#B71A24; color:#fff; }}
div[data-testid="stColumn"]:has(.navcol-marker) .stCaption,
div[data-testid="stColumn"]:has(.navcol-marker) [data-testid="stCaptionContainer"] {{ color:#7D8AA0 !important; }}
div[data-testid="stColumn"]:has(.navcol-marker) [data-testid="stCaptionContainer"] p {{ color:#7D8AA0 !important; font-size:.72rem; }}

/* ---------- page header ---------- */
.ph {{ margin-bottom: 1.5rem; }}
.ph h1 {{ font-size:1.85rem; font-weight:800; color:{C["ink"]}; margin:0; letter-spacing:-.025em; }}
.ph p {{ font-size:.9rem; color:{C["muted"]}; margin:.35rem 0 0; }}
.stamp {{
    display:inline-flex; align-items:center; gap:7px; background:{C["surface"]};
    border:1px solid {C["line"]}; border-radius:999px; padding:6px 14px;
    font-size:.75rem; color:{C["muted"]}; font-weight:600;
}}
.stamp i {{ width:7px; height:7px; border-radius:50%; background:{C["green"]}; display:inline-block; }}

/* ---------- tiles ---------- */
.tile {{
    background:{C["surface"]}; border:1px solid {C["line"]}; border-radius:14px;
    padding:18px 20px; height:100%;
}}
.tile .cap {{ font-size:.68rem; letter-spacing:.09em; text-transform:uppercase;
              color:{C["muted"]}; font-weight:700; }}
.tile .big {{ font-size:2.1rem; font-weight:800; color:{C["ink"]}; line-height:1.1; margin-top:6px; }}
.tile .sub {{ font-size:.76rem; color:{C["muted"]}; margin-top:3px; }}
.tile.a .big {{ color:{C["amber"]}; }}
.tile.f .big {{ color:{C["focal"]}; }}

/* ---------- panels ---------- */
.panel {{ background:{C["surface"]}; border:1px solid {C["line"]}; border-radius:14px;
          padding:20px 22px; margin-bottom:16px; }}
.ptitle {{ font-size:1.02rem; font-weight:750; color:{C["ink"]}; margin:0 0 2px; }}
.psub {{ font-size:.8rem; color:{C["muted"]}; margin:0 0 14px; }}

/* ---------- 2x2 matrix ---------- */
.mx {{ display:grid; grid-template-columns: 34px 1fr 1fr; gap:10px; align-items:stretch; }}
.mx .ylab {{
    writing-mode: vertical-rl; transform: rotate(180deg);
    display:flex; align-items:center; justify-content:center; white-space:nowrap;
    font-size:.68rem; font-weight:700; letter-spacing:.1em; text-transform:uppercase;
    color:{C["muted"]};
}}
.qbox {{ border:1px solid {C["line"]}; border-radius:12px; padding:14px 15px; min-height:150px;
         background:{C["canvas"]}; }}
.qbox.hot {{ background:{C["amber_soft"]}; border-color:#F5D9A8; }}
.qbox h5 {{ margin:0 0 3px; font-size:.85rem; font-weight:750; color:{C["ink"]}; }}
.qbox .qh {{ font-size:.68rem; color:{C["muted"]}; margin-bottom:9px; font-weight:600; }}
.qbox ul {{ margin:0; padding-left:16px; }}
.qbox li {{ font-size:.79rem; color:{C["body"]}; margin-bottom:4px; line-height:1.35; }}
.qbox .none {{ font-size:.78rem; color:{C["muted"]}; font-style:italic; }}
.thin {{ display:inline-block; font-size:.62rem; font-weight:700; padding:1px 7px;
         border-radius:999px; background:{C["amber_soft"]}; color:{C["amber"]};
         vertical-align:middle; }}
.axrow {{ display:grid; grid-template-columns:34px 1fr 1fr; gap:10px; margin-top:9px; }}
.axrow div {{ text-align:center; font-size:.7rem; font-weight:700; letter-spacing:.09em;
              text-transform:uppercase; color:{C["muted"]}; }}

/* ---------- ranked opportunity rows ---------- */
.oppcard {{ background:{C["surface"]}; border:1px solid {C["line"]}; border-left:4px solid {C["amber"]};
            border-radius:12px; padding:15px 18px; margin-bottom:11px; }}
.oppcard .rk {{ display:inline-flex; align-items:center; justify-content:center;
                width:25px; height:25px; border-radius:7px; background:{C["amber"]};
                color:#fff; font-weight:800; font-size:.78rem; margin-right:10px; }}
.oppcard .nm {{ font-size:1rem; font-weight:750; color:{C["ink"]}; }}
.oppcard .band {{ font-size:.73rem; color:{C["muted"]}; font-weight:600; margin-left:8px; }}
.oppcard .sc {{ margin-top:10px; font-size:.83rem; color:{C["body"]}; line-height:1.55; }}
.oppcard .sc b {{ color:{C["ink"]}; font-weight:700; }}
.pill {{ display:inline-block; font-size:.67rem; font-weight:700; padding:3px 10px;
         border-radius:999px; margin-left:6px; }}
.pill.frag {{ background:{C["green_soft"]}; color:{C["green"]}; }}
.pill.mod  {{ background:{C["amber_soft"]}; color:{C["amber"]}; }}
.pill.conc {{ background:{C["focal_soft"]}; color:{C["focal"]}; }}

/* ---------- product cards ---------- */
.prod {{ background:{C["surface"]}; border:1px solid {C["line"]}; border-radius:12px;
         overflow:hidden; height:100%; }}
.prod img {{ width:100%; height:168px; object-fit:contain; display:block; background:{C["canvas"]}; }}
.prod .noimg {{ width:100%; height:168px; background:{C["canvas"]}; display:flex;
                align-items:center; justify-content:center; color:{C["muted"]};
                font-size:.72rem; border-bottom:1px solid {C["line"]}; }}
.prod .pb {{ padding:12px 13px; }}
.prod .br {{ font-size:.82rem; font-weight:750; color:{C["ink"]}; }}
.prod .tt {{ font-size:.75rem; color:{C["muted"]}; margin:2px 0 8px; line-height:1.3;
             min-height:29px; }}
.prod .mt {{ font-size:.76rem; color:{C["body"]}; font-weight:600; }}
.prod .st {{ color:{C["green"]}; font-weight:700; }}
.prod a {{ font-size:.75rem; color:{C["blue"]}; text-decoration:none; font-weight:650; }}

/* ---------- pros / cons ---------- */
.pc {{ border-radius:11px; padding:13px 15px; height:100%; }}
.pc.pro {{ background:{C["green_soft"]}; border:1px solid #BCE8D6; }}
.pc.con {{ background:{C["focal_soft"]}; border:1px solid #F6CFCF; }}
.pc h6 {{ margin:0 0 7px; font-size:.72rem; letter-spacing:.08em; text-transform:uppercase;
          font-weight:750; }}
.pc.pro h6 {{ color:{C["green"]}; }}
.pc.con h6 {{ color:{C["focal"]}; }}
.pc ul {{ margin:0; padding-left:16px; }}
.pc li {{ font-size:.81rem; color:{C["body"]}; margin-bottom:5px; line-height:1.4; }}

.note {{ background:{C["blue_soft"]}; border:1px solid #C9D8FB; border-radius:10px;
         padding:10px 14px; font-size:.78rem; color:#1D3FAF; }}
.warn {{ background:{C["amber_soft"]}; border:1px solid #F5D9A8; border-radius:10px;
         padding:10px 14px; font-size:.78rem; color:#8A4B08; }}

hr.sep {{ border:none; border-top:1px solid {C["line"]}; margin:22px 0 18px; }}
</style>
"""
