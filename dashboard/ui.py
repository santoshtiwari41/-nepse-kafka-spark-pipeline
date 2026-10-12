"""Shared look & feel: palette, CSS, helpers, page chrome (header + price ticker)."""
import html

import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

import data

# ───────────────────────── chart style (validated palette) ─────────────────────────
SURFACE, INK, INK2, MUTED = "rgba(0,0,0,0)", "#0f172a", "#475569", "#94a3b8"
GRID, AXIS, MIDPOINT = "#eef1f5", "#cbd5e1", "#f1f5f9"
SERIES = ["#2a78d6", "#eb6834", "#1baf7a"]          # categorical slots 1-3 (validated all-pairs)
UP, DOWN = "#0b7a3b", "#b42318"                      # price direction, always with +/− in text
BAND = "rgba(42,120,214,0.10)"
FONT = "system-ui, -apple-system, Segoe UI, Roboto, sans-serif"
PLOT_CONFIG = {"displaylogo": False, "modeBarButtonsToRemove": ["lasso2d", "select2d", "autoScale2d"]}
MODE_BADGE = {
    "LIVE": ("#b42318", "LIVE", "Live market data"),
    "REPLAY": ("#b45309", "REPLAY", "Replay of a past trading session"),
    "HISTORICAL": ("#1f4e8c", "HISTORICAL", "Market closed, showing the last trading day"),
}

CSS = """
<style>
:root { --ink:#111827; --ink2:#4b5563; --muted:#9ca3af; --line:#dfe3e8; --card:#ffffff;
        --bg:#f4f5f7; --brand:#1f4e8c; --up:#0b7a3b; --down:#b42318; }
#MainMenu, footer, [data-testid="stToolbar"], [data-testid="stDecoration"],
[data-testid="stStatusWidget"] { display:none !important; }
header[data-testid="stHeader"] { background:transparent; height:0; }
.stApp { background:var(--bg); }
.block-container { padding-top:1.1rem; padding-bottom:2rem; max-width:1500px; }
html, body, [class*="css"] { font-feature-settings:"tnum" 1; }

/* header */
.nx-head { display:flex; align-items:baseline; gap:14px; border-bottom:2px solid var(--ink); padding-bottom:8px; }
.nx-title { font-size:1.25rem; font-weight:700; color:var(--ink); letter-spacing:.01em; }
.nx-sub { color:var(--ink2); font-size:.82rem; }

/* tabs */
.stTabs [data-baseweb="tab-list"] { gap:0; border-bottom:1px solid var(--line); }
.stTabs [data-baseweb="tab"] { height:auto; padding:9px 18px; font-weight:600; font-size:.88rem;
                               color:var(--ink2); background:transparent; border-radius:0; }
.stTabs [data-baseweb="tab"]:hover { color:var(--ink); background:#e9ecf0; }
.stTabs [aria-selected="true"] { color:var(--ink) !important; }
.stTabs [data-baseweb="tab-highlight"] { background:var(--ink); height:2px; }
.stTabs [data-baseweb="tab-border"] { display:none; }

/* metrics */
[data-testid="stMetric"] { background:var(--card); border:1px solid var(--line); border-radius:4px;
                           padding:10px 14px; }
[data-testid="stMetricLabel"] p { color:var(--ink2); font-size:.7rem; font-weight:600;
                                  text-transform:uppercase; letter-spacing:.06em; }
[data-testid="stMetricValue"] { font-size:1.35rem; font-weight:600; color:var(--ink); }
[data-testid="stMetricDelta"] { font-size:.8rem; }

/* panels */
[class*="st-key-card"] { background:var(--card); border:1px solid var(--line) !important; border-radius:4px;
                         padding:4px 12px 10px; }
.nx-sec { margin:.45rem 0 .5rem; padding-bottom:6px; border-bottom:1px solid var(--line); }
.nx-sec b { font-size:.74rem; color:var(--ink); text-transform:uppercase; letter-spacing:.07em; font-weight:700; }
.nx-sec span { color:var(--muted); font-size:.76rem; margin-left:10px; }

/* status strip */
.nx-banner { display:flex; align-items:center; gap:14px; flex-wrap:wrap; background:var(--card);
             border:1px solid var(--line); border-radius:4px; padding:8px 14px; font-size:.84rem; }
.nx-badge { font-weight:700; font-size:.72rem; letter-spacing:.08em; padding:2px 8px; border-radius:2px; color:#fff; }
.nx-banner .txt { color:var(--ink2); flex:1; min-width:240px; }
.nx-banner .rt { color:var(--muted); font-size:.76rem; }

/* ranked tables */
.nx-list { display:flex; flex-direction:column; }
.nx-row { display:grid; gap:10px; align-items:center; padding:5px 2px; border-bottom:1px solid #eef0f3;
          font-size:.86rem; font-variant-numeric:tabular-nums; }
.nx-row:last-child { border-bottom:none; }
.nx-rk { color:var(--muted); font-size:.72rem; }
.nx-sym { font-weight:600; color:var(--ink); }
.nx-px { color:var(--ink2); text-align:right; }
.nx-pill { min-width:62px; text-align:right; font-weight:600; font-size:.86rem; }
.nx-up { color:var(--up); } .nx-dn { color:var(--down); } .nx-fl { color:var(--ink2); }
.nx-bar { height:4px; background:#e5e8ec; width:80px; position:relative; }
.nx-bar i { position:absolute; left:0; top:0; bottom:0; background:var(--brand); }

/* breadth */
.nx-breadth { background:var(--card); border:1px solid var(--line); border-radius:4px; padding:10px 14px; height:100%; }
.nx-breadth .lbl { color:var(--ink2); font-size:.7rem; font-weight:600; text-transform:uppercase; letter-spacing:.06em; }
.nx-breadth .bar { display:flex; height:8px; overflow:hidden; margin:12px 0 8px; background:#e5e8ec; }
.nx-breadth .legend { display:flex; justify-content:space-between; font-size:.8rem; font-weight:600; }

/* alerts */
.nx-alerts { max-height:430px; overflow-y:auto; }
.nx-alert { border-bottom:1px solid #eef0f3; padding:7px 2px; font-size:.84rem; }
.nx-alert .h { display:flex; justify-content:space-between; }
.nx-chip { font-size:.68rem; font-weight:700; letter-spacing:.06em; }
.nx-alert .t { color:var(--muted); font-size:.74rem; }
.nx-alert .m { color:var(--ink2); margin-top:1px; }
.nx-empty { text-align:center; color:var(--ink2); padding:26px 12px; font-size:.86rem; }
.nx-empty b { display:block; color:var(--ink); font-size:.92rem; margin-bottom:3px; }

/* security header */
.nx-hero { display:flex; justify-content:space-between; align-items:center; gap:24px; flex-wrap:wrap;
           background:var(--card); border:1px solid var(--line); border-radius:4px; padding:14px 18px; }
.nx-hero .sym { font-size:1.5rem; font-weight:700; color:var(--ink); line-height:1; }
.nx-hero .co { color:var(--ink2); margin-top:5px; font-size:.86rem; }
.nx-tag { color:var(--ink2); font-size:.74rem; font-weight:600; margin-right:12px; text-transform:uppercase; letter-spacing:.05em; }
.nx-hero .px { font-size:1.6rem; font-weight:700; color:var(--ink); font-variant-numeric:tabular-nums; }
.nx-range { min-width:260px; flex:1; max-width:380px; }
.nx-range .ends { display:flex; justify-content:space-between; font-size:.78rem; color:var(--ink2); font-variant-numeric:tabular-nums; }
.nx-range .trk { position:relative; height:4px; margin:12px 0 7px; background:#d5d9df; }
.nx-range .trk i { position:absolute; top:-5px; width:3px; height:14px; background:var(--ink); }
.nx-range .cap { font-size:.7rem; color:var(--ink2); text-transform:uppercase; letter-spacing:.06em; font-weight:600; }

/* inputs */
[data-testid="stWidgetLabel"] p { font-weight:600; color:var(--ink2); font-size:.74rem;
                                  text-transform:uppercase; letter-spacing:.05em; }
[data-baseweb="select"] > div, [data-testid="stTextInput"] input { border-radius:3px !important; }
[data-testid="stDataFrame"] { border:1px solid var(--line); border-radius:4px; }

/* ---- brokerage terminal theme ---- */
/* page navigation (st.page_link row) */
.st-key-navbar { background:var(--navy2); margin:6px -1rem 14px; padding:0 8px; }
.st-key-navbar [data-testid="stHorizontalBlock"] { gap:0; }
.st-key-navbar a { color:#b8c7de !important; padding:11px 20px; border-radius:0; font-weight:600; font-size:.88rem;
                   border-bottom:3px solid transparent; justify-content:center; }
.st-key-navbar a:hover { background:#1c3f73; color:#fff !important; }
.st-key-navbar a p { font-weight:600; font-size:.88rem; }

:root { --navy:#0b2545; --navy2:#13315c; --gold:#c9a227; }
.block-container { padding-top:0 !important; }
.nx-top { background:var(--navy); color:#fff; display:flex; justify-content:space-between; align-items:center;
          gap:20px; flex-wrap:wrap; padding:14px 22px; margin:0 -1rem; }
.nx-brand .n { font-size:1.2rem; font-weight:700; letter-spacing:.04em; }
.nx-brand .s { color:#9fb3cf; font-size:.74rem; letter-spacing:.08em; text-transform:uppercase; margin-top:2px; }
.nx-idx { display:flex; gap:28px; flex-wrap:wrap; }
.nx-idx .k { color:#9fb3cf; font-size:.66rem; letter-spacing:.09em; text-transform:uppercase; }
.nx-idx .v { font-size:1.05rem; font-weight:600; font-variant-numeric:tabular-nums; }
.nx-idx .up { color:#4ade80; } .nx-idx .dn { color:#f87171; }
.nx-tape { background:#081a33; border-bottom:2px solid var(--gold); overflow:hidden; white-space:nowrap;
           margin:0 -1rem 8px; padding:6px 0; }
.nx-tape .in { display:inline-block; padding-left:100%; animation:nxtape 160s linear infinite; }
.nx-tape:hover .in { animation-play-state:paused; }
.nx-tape span { display:inline-block; margin-right:34px; font-size:.8rem; color:#d6e0ef; font-variant-numeric:tabular-nums; }
.nx-tape b { color:#fff; margin-right:6px; }
.nx-tape .u { color:#4ade80; } .nx-tape .d { color:#f87171; }
@keyframes nxtape { from { transform:translateX(0);} to { transform:translateX(-100%);} }
@media (prefers-reduced-motion:reduce) { .nx-tape .in { animation:none; padding-left:12px; } }

.stTabs [data-baseweb="tab-list"] { background:var(--navy2); border-bottom:none; padding:0 8px; margin-top:6px; }
.stTabs [data-baseweb="tab"] { color:#b8c7de; padding:11px 20px; }
.stTabs [data-baseweb="tab"]:hover { background:#1c3f73; color:#fff; }
.stTabs [aria-selected="true"] { color:#fff !important; }
.stTabs [data-baseweb="tab-highlight"] { background:var(--gold); height:3px; }
.stTabs [data-baseweb="tab-panel"] { padding-top:14px; }

.nx-sec { background:var(--navy); margin:-4px -12px 10px; padding:7px 12px; border:none; }
.nx-sec b { color:#fff; }
.nx-sec span { color:#9fb3cf; }
[class*="st-key-card"] { padding:4px 12px 10px; overflow:hidden; }
.nx-row:nth-child(even) { background:#f7f9fc; }
.nx-badge { border-radius:2px; }
.nx-hero { border-top:3px solid var(--navy); }
[data-testid="stMetric"] { border-top:3px solid var(--navy); }
.nx-foot { color:var(--muted); font-size:.75rem; margin-top:1.5rem; border-top:1px solid var(--line); padding-top:8px; }
</style>
"""


def style(fig, height=420, legend=True):
    fig.update_layout(
        template="none", height=height, paper_bgcolor=SURFACE, plot_bgcolor=SURFACE,
        font=dict(family=FONT, color=INK2, size=12), margin=dict(l=56, r=16, t=28, b=40),
        showlegend=legend, hovermode="x unified",
        legend=dict(orientation="h", x=0, y=1.0, yanchor="bottom", font=dict(color=INK2), traceorder="normal"),
        hoverlabel=dict(bgcolor="white", bordercolor=AXIS, font=dict(family=FONT, color=INK)))
    fig.update_xaxes(showgrid=False, linecolor=AXIS, tickfont=dict(color=MUTED), rangeslider_visible=False,
                     automargin=True)
    fig.update_yaxes(gridcolor=GRID, zeroline=False, linecolor=AXIS, tickfont=dict(color=MUTED),
                     automargin=True)
    return fig


def candles(fig, df, row, o, h, l, c, x):
    fig.add_trace(go.Candlestick(
        x=df[x], open=df[o], high=df[h], low=df[l], close=df[c], name="Price",
        increasing=dict(line=dict(color=UP, width=1), fillcolor=UP),
        decreasing=dict(line=dict(color=DOWN, width=1), fillcolor=DOWN)), row=row, col=1)


def signed_colors(values):
    return [UP if v > 0 else DOWN if v < 0 else MUTED for v in values]


def section(title, sub=None):
    st.markdown(f"<div class='nx-sec'><b>{html.escape(title)}</b>"
                f"{f'<span>{html.escape(sub)}</span>' if sub else ''}</div>", unsafe_allow_html=True)


def pill(v):
    cls = "nx-up" if v > 0 else "nx-dn" if v < 0 else "nx-fl"
    return f"<span class='nx-pill {cls}'>{v:+.2f}%</span>"


def empty(title, text):
    st.markdown(f"<div class='nx-empty'><b>{html.escape(title)}</b>{html.escape(text)}</div>", unsafe_allow_html=True)


def banner(mode, detail):
    color, label, text = MODE_BADGE[mode]
    right = "Updates every 3 s" if mode != "HISTORICAL" else "Previous close"
    st.markdown(
        f"<div class='nx-banner'><span class='nx-badge' style='background:{color}'>{label}</span>"
        f"<span class='txt'>{text} · <b>{html.escape(detail)}</b></span><span class='rt'>{right}</span></div>",
        unsafe_allow_html=True)


def rupees(x):
    return f"Rs {x / 1e9:,.2f} B" if x >= 1e9 else f"Rs {x / 1e6:,.1f} M"


def movers(df, kind="chg"):
    """Ranked list rendered as HTML: symbol, price and a coloured change pill (plus a turnover bar)."""
    if df.empty:
        return empty("No data", "Nothing to show yet.")
    top = df["turnover"].max() if kind == "turn" else 1
    grid = "22px 1fr auto 80px auto" if kind == "turn" else "22px 1fr auto auto"
    rows = []
    for i, r in enumerate(df.itertuples(), 1):
        bar = (f"<div class='nx-bar' style='width:80px'><i style='width:{max(r.turnover / top, 0.03) * 100:.0f}%'></i></div>"
               if kind == "turn" else "")
        rows.append(f"<div class='nx-row' style='grid-template-columns:{grid}'><span class='nx-rk'>{i}</span>"
                    f"<span class='nx-sym'>{r.symbol}</span><span class='nx-px'>{r.ltp:,.2f}</span>{bar}"
                    f"{pill(r.change_pct)}</div>")
    st.markdown("<div class='nx-list'>" + "".join(rows) + "</div>", unsafe_allow_html=True)


EQUITY_ONLY = "Ordinary shares only (debentures and mutual funds excluded)."
ALERT_STYLE = {"UPPER_CIRCUIT": ("#0b7a3b", "UPPER CIRCUIT"), "LOWER_CIRCUIT": ("#b42318", "LOWER CIRCUIT"),
               "VOLUME_SPIKE": ("#1f4e8c", "VOLUME SPIKE"), "BIG_MOVE": ("#b45309", "BIG MOVE")}


def chrome():
    """Inject CSS and draw the top band + price ticker (every page)."""
    st.markdown(CSS, unsafe_allow_html=True)
    _snap0, _mk0 = data.latest_snapshot(), data.market_daily()
    _last = _mk0.iloc[-1]
    _cls = "up" if _last["change_pct"] >= 0 else "dn"
    st.markdown(
        "<div class='nx-top'><div class='nx-brand'><div class='n'>NEPSE MARKET ANALYTICS</div>"
        "<div class='s'>Nepal Stock Exchange · market data and research</div></div>"
        "<div class='nx-idx'>"
        f"<div><div class='k'>NEPSE index</div><div class='v'>{_last['close']:,.2f}</div></div>"
        f"<div><div class='k'>Change</div><div class='v {_cls}'>{_last['change_pct']:+.2f}%</div></div>"
        f"<div><div class='k'>Turnover</div><div class='v'>{rupees(_last['turnover'] or 0)}</div></div>"
        f"<div><div class='k'>Session</div><div class='v'>{str(_last['date'])[:10]}</div></div>"
        "</div></div>", unsafe_allow_html=True)
    _t = _snap0[_snap0["instrument_type"] == "Equity"].nlargest(45, "turnover")
    _items = "".join(
        f"<span><b>{r.symbol}</b>{r.close:,.2f} <i class='{'u' if r.change_pct > 0 else 'd' if r.change_pct < 0 else ''}' "
        f"style='font-style:normal'>{'▲' if r.change_pct > 0 else '▼' if r.change_pct < 0 else '■'} {abs(r.change_pct):.2f}%</i></span>"
        for r in _t.itertuples())
    st.markdown(f"<div class='nx-tape'><div class='in'>{_items}</div></div>", unsafe_allow_html=True)

