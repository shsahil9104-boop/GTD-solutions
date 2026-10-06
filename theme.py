"""Look and feel: one stylesheet plus small HTML helpers. Call theme.inject() once per run."""
from html import escape

import streamlit as st

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap');
:root{--pine:#0f3b36;--teal:#1c5a52;--gold:#f2b01e;--cream:#f6f4ee;--card:#ffffff;--ink:#17201e;--mute:#64726f;--line:#e5e1d6;--r:16px}
html,body,[class*="css"],.stApp{font-family:'Plus Jakarta Sans',system-ui,sans-serif!important}
.stApp{background:radial-gradient(1200px 500px at 85% -10%,#fff3d1 0%,transparent 60%),var(--cream)}
header[data-testid="stHeader"]{background:transparent}
#MainMenu,footer{visibility:hidden}
.block-container{padding-top:2rem;max-width:1180px}
h1,h2,h3{color:var(--pine);letter-spacing:-.02em;font-weight:800!important}
h2{font-size:1.9rem!important} h3{font-size:1.25rem!important}
[data-testid="stToolbarActions"], [data-testid="stMainMenu"], [data-testid="stDecoration"], [data-testid="stStatusWidget"]{display:none!important}
[data-testid="stExpandSidebarButton"], [data-testid="stSidebarCollapseButton"]{display:flex!important;visibility:visible!important}
/* sidebar */
[data-testid="stSidebar"]{background:linear-gradient(180deg,#0f3b36 0%,#0b2a27 100%)}
[data-testid="stSidebar"] *{color:#e8f1ef}
[data-testid="stSidebar"] [role="radiogroup"]{gap:4px}
[data-testid="stSidebar"] [role="radiogroup"] label{padding:10px 14px;border-radius:12px;width:100%;transition:.15s;cursor:pointer}
[data-testid="stSidebar"] [role="radiogroup"] label>div:first-child{display:none}
[data-testid="stSidebar"] [role="radiogroup"] label:hover{background:#ffffff14}
[data-testid="stSidebar"] [role="radiogroup"] label:has(input:checked){background:var(--gold)}
[data-testid="stSidebar"] [role="radiogroup"] label:has(input:checked) *{color:#1b1b12;font-weight:700}
[data-testid="stSidebar"] .stButton>button{background:#ffffff14;border:1px solid #ffffff26;color:#fff}
[data-testid="stSidebar"] .stButton>button:hover{background:#ffffff26;border-color:var(--gold)}
.brand{font-size:1.9rem;font-weight:800;letter-spacing:.06em;color:#fff;margin:.2rem 0 .1rem}
.brand b{color:var(--gold)}
.who{display:flex;align-items:center;gap:10px;background:#ffffff12;border-radius:14px;padding:10px 12px;margin:10px 0 14px}
.who .av{width:36px;height:36px;border-radius:50%;background:var(--gold);color:#1b1b12!important;font-weight:800;display:flex;align-items:center;justify-content:center}
.who small{opacity:.7;display:block;text-transform:capitalize}

/* buttons + inputs */
.stButton>button,.stDownloadButton>button,[data-testid="stFormSubmitButton"]>button{border-radius:12px;font-weight:600;padding:.55rem 1.1rem;border:1px solid var(--line);transition:.15s}
.stButton>button:hover,[data-testid="stFormSubmitButton"]>button:hover{transform:translateY(-1px);box-shadow:0 6px 16px #0f3b3626}
button[kind="primary"],button[kind="primaryFormSubmit"]{background:var(--gold)!important;color:#1b1b12!important;border:0!important}
[data-baseweb="input"],[data-baseweb="select"]>div,[data-baseweb="textarea"]{border-radius:12px!important}
[data-testid="stForm"]{background:var(--card);border:1px solid var(--line);border-radius:var(--r);padding:1.4rem;box-shadow:0 8px 24px #0f3b3610}

/* tabs */
[data-baseweb="tab-list"]{gap:6px;background:#ebe7da;padding:5px;border-radius:14px;width:fit-content}
[data-baseweb="tab"]{border-radius:10px;padding:8px 18px;height:auto}
[aria-selected="true"][data-baseweb="tab"]{background:#fff;box-shadow:0 2px 8px #0f3b3620}
[data-baseweb="tab-highlight"],[data-baseweb="tab-border"]{display:none}

/* cards */
[data-testid="stMetric"]{background:var(--card);border:1px solid var(--line);border-radius:var(--r);padding:16px 18px;box-shadow:0 6px 18px #0f3b360d}
[data-testid="stMetricLabel"]{color:var(--mute)}
[data-testid="stMetricValue"]{color:var(--pine);font-weight:800}
[data-testid="stExpander"]{background:var(--card);border:1px solid var(--line)!important;border-radius:var(--r);overflow:hidden}
[data-testid="stDataFrame"],[data-testid="stDataEditor"]{border-radius:14px;overflow:hidden;border:1px solid var(--line)}

/* hero */
.hero{position:relative;overflow:hidden;color:#fff;border-radius:24px;padding:44px 40px;margin-bottom:26px;
 background:radial-gradient(500px 260px at 90% 0%,#f2b01e55,transparent 70%),linear-gradient(135deg,#0f3b36,#1c5a52)}
.hero h1{color:#fff;font-size:clamp(1.9rem,4vw,3rem);line-height:1.1;margin:0 0 10px;max-width:16ch;padding:0}
.hero p{color:#cfe3df;max-width:52ch;margin:0 0 18px;font-size:1.05rem}
.chip{display:inline-block;background:#ffffff1f;border:1px solid #ffffff33;border-radius:99px;padding:5px 14px;margin:0 8px 6px 0;font-size:.88rem;font-weight:600}

/* fare card */
.fare-card{background:linear-gradient(145deg,#0f3b36,#1c5a52);color:#fff;border-radius:20px;padding:22px;box-shadow:0 14px 34px #0f3b3638}
.fare-label{opacity:.75;font-size:.85rem;text-transform:uppercase;letter-spacing:.08em}
.fare-total{font-size:2.7rem;font-weight:800;color:var(--gold);line-height:1.1;margin:2px 0 10px}
.fare-lines div{display:flex;justify-content:space-between;padding:7px 0;border-top:1px solid #ffffff26;font-size:.95rem}
.fare-note{opacity:.7;font-size:.8rem;margin-top:10px}

/* badges */
.badge{display:inline-block;padding:3px 12px;border-radius:99px;font-size:.82rem;font-weight:700}
.b-pending{background:#fdf0cf;color:#8a6100}.b-confirmed,.b-assigned{background:#dde8f7;color:#1f4a86}
.b-ongoing{background:#e8dcf6;color:#5a2d8f}.b-completed{background:#d8efe2;color:#1f7a4d}.b-cancelled{background:#f7d9d6;color:#b3261e}
</style>
"""


def inject():
    st.markdown(CSS, unsafe_allow_html=True)


def hero(title, sub="", chips=()):
    chip_html = "".join(f'<span class="chip">{escape(c)}</span>' for c in chips)
    st.markdown(f'<div class="hero"><h1>{escape(title)}</h1><p>{escape(sub)}</p>{chip_html}</div>', unsafe_allow_html=True)


def badge(label, status):
    return f'<span class="badge b-{escape(status)}">{escape(label)}</span>'


def fare_card(total_text, lines, note=""):
    rows = "".join(f"<div><span>{escape(l)}</span><b>{escape(a)}</b></div>" for l, a in lines)
    st.markdown(f'<div class="fare-card"><div class="fare-label">Your fare</div><div class="fare-total">{escape(total_text)}</div>'
                f'<div class="fare-lines">{rows}</div><div class="fare-note">{escape(note)}</div></div>', unsafe_allow_html=True)


def sidebar_brand(user=None):
    st.markdown('<div class="brand">G<b>T</b>D</div><small style="opacity:.6">Travel Agency</small>', unsafe_allow_html=True)
    if user:
        name = user["full_name"] or user["username"]
        st.markdown(f'<div class="who"><div class="av">{escape(name[:1].upper())}</div>'
                    f'<div><b>{escape(name)}</b><small>{escape(user["role"])}</small></div></div>', unsafe_allow_html=True)
