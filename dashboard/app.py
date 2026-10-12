"""NEPSE Market Analytics dashboard (Streamlit).

    streamlit run dashboard/app.py      (normally started by docker compose → http://localhost:8501)
"""
import html
import time

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

import data

st.set_page_config(page_title="NEPSE Analytics", page_icon="📈", layout="wide",
                   initial_sidebar_state="collapsed")

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
st.markdown(CSS, unsafe_allow_html=True)


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

# ───────────────────────── header ─────────────────────────
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

tab_live, tab_stock, tab_market, tab_screen, tab_pipe = st.tabs(
    ["Live market", "Stock explorer", "Market & sectors", "Screener", "Pipeline"])


# ───────────────────────── 1. live market ─────────────────────────
def market_frame():
    """Current market from the stream, or the last trading day from the batch layer."""
    feed = data.live_feed()
    deadline = time.time() + 3           # first page load: give the Kafka backlog a moment
    while not feed.ready and time.time() < deadline:
        time.sleep(0.1)
    snap, alerts, mode, age, session, session_date = feed.state()
    if mode == "HISTORICAL" or snap.empty:
        batch = data.latest_snapshot().rename(columns={"close": "ltp"})
        day = batch["date"].max()
        return batch[batch["date"] == day], pd.DataFrame(), "HISTORICAL", f"last trading day {day}", None
    what = f"replaying the {session_date} session" if mode == "REPLAY" else f"session {session_date}"
    return snap, alerts, mode, f"{what} · last update {data.fmt_age(age)}", session


@st.fragment(run_every="3s")
def live_market():
    df, alerts, mode, detail, session = market_frame()
    banner(mode, detail)
    note = st.empty()      # fixed slot → page layout stays identical between refreshes
    if not data.live_feed().ready:
        note.caption("Loading live data…")
    eq = df[df["instrument_type"] == "Equity"].copy()
    if eq.empty:
        empty("No market data yet", "Market data is not available yet.")
        return

    adv, dec = int((eq["change_pct"] > 0).sum()), int((eq["change_pct"] < 0).sum())
    flat = len(eq) - adv - dec
    st.write("")
    k = st.columns([1, 1, 1, 2])
    k[0].metric("Stocks traded", f"{len(eq)}", help="Ordinary shares with a price in this view")
    k[1].metric("Turnover", rupees(eq["turnover"].fillna(0).sum()), help="Total value traded (Rs)")
    k[2].metric("Alerts", f"{len(alerts)}" if mode != "HISTORICAL" else "—",
                help="Circuit hits, volume spikes and large price moves this session")
    n = max(len(eq), 1)
    k[3].markdown(
        f"<div class='nx-breadth'><div class='lbl'>Market breadth</div><div class='bar'>"
        f"<div style='width:{adv / n * 100:.1f}%;background:{UP}'></div>"
        f"<div style='width:{flat / n * 100:.1f}%;background:#cbd5e1'></div>"
        f"<div style='width:{dec / n * 100:.1f}%;background:{DOWN}'></div></div>"
        f"<div class='legend'><span style='color:{UP}'>▲ {adv} advancing</span>"
        f"<span style='color:#64748b'>{flat} unchanged</span>"
        f"<span style='color:{DOWN}'>▼ {dec} declining</span></div></div>", unsafe_allow_html=True)
    st.write("")

    c1, c2, c3 = st.columns(3)
    with c1.container(key="card_gain"):
        section("Top gainers", "Biggest % rise")
        movers(eq.nlargest(10, "change_pct"))
    with c2.container(key="card_lose"):
        section("Top losers", "Biggest % fall")
        movers(eq.nsmallest(10, "change_pct"))
    with c3.container(key="card_active"):
        section("Most active", "Highest turnover")
        movers(eq.nlargest(10, "turnover"), "turn")
    st.caption(EQUITY_ONLY)

    left, right = st.columns([3, 2])
    with left.container(key="card_map"):
        section("Sector map", "Tile size = turnover · colour = % change (green up, red down)")
        tm = eq[eq["turnover"] > 0].assign(change_pct=lambda d: d["change_pct"].round(2))
        fig = px.treemap(tm, path=[px.Constant("NEPSE"), "sector", "symbol"], values="turnover",
                         color="change_pct", color_continuous_scale=[DOWN, MIDPOINT, UP],
                         color_continuous_midpoint=0, range_color=(-5, 5),
                         custom_data=["change_pct"])
        fig.update_traces(texttemplate="%{label}<br>%{customdata[0]:+.2f}%",
                          hovertemplate="%{label}<br>Turnover Rs %{value:,.0f}<br>Change %{customdata[0]:+.2f}%",
                          marker=dict(line=dict(color="white", width=2)))
        fig.update_layout(coloraxis_colorbar=dict(title="%", ticksuffix="%", thickness=10))
        st.plotly_chart(style(fig, 450, legend=False), key="treemap", config=PLOT_CONFIG)
    with right.container(key="card_alerts"):
        section("Market alerts", "Circuit, volume and price-move alerts")
        if alerts.empty:
            if mode == "HISTORICAL":
                empty("Market closed", "Alerts appear while the market is live.")
            else:
                empty("All quiet", "No alerts in this session yet.")
        else:
            items = []
            for a in alerts.head(30).itertuples():
                color, label = ALERT_STYLE.get(a.alert_type, ("#64748b", a.alert_type.replace("_", " ")))
                items.append(f"<div class='nx-alert'><div class='h'><span class='nx-chip' style='color:{color}'>"
                             f"{label}</span><span class='t'>{str(a.event_time)[11:19]}</span></div>"
                             f"<div class='m'>{html.escape(str(a.message))}</div></div>")
            st.markdown("<div class='nx-alerts'>" + "".join(items) + "</div>", unsafe_allow_html=True)

    if mode != "HISTORICAL":
        intraday(eq, session)


def intraday(eq, session):
    with st.container(key="card_intraday"):
        section("Intraday candles", "1-minute and 5-minute price bars")
        symbols = eq.sort_values("turnover", ascending=False)["symbol"].tolist()
        c1, c2, _ = st.columns([1, 1, 3])
        symbol = c1.selectbox("Symbol", symbols, key="intraday_symbol")
        interval = c2.segmented_control("Interval", ["1 min", "5 min"], default="1 min", key="intraday_interval") or "1 min"
        cdf = data.intraday_candles(symbol, session)
        if cdf.empty:
            empty("Waiting for the first candle", "The first price bar appears after one minute.")
            return
        if interval == "5 min":
            cdf = (cdf.set_index("window_start").resample("5min")
                      .agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"})
                      .dropna().reset_index())
        fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.75, 0.25], vertical_spacing=0.04)
        candles(fig, cdf, 1, "open", "high", "low", "close", "window_start")
        fig.add_trace(go.Bar(x=cdf["window_start"], y=cdf["volume"], name="Volume", marker_color=AXIS), row=2, col=1)
        fig.update_yaxes(title_text="Price (Rs)", row=1, col=1)
        fig.update_yaxes(title_text="Volume", row=2, col=1)
        st.plotly_chart(style(fig, 420, legend=False), key="intraday_chart", config=PLOT_CONFIG)


with tab_live:
    live_market()


# ───────────────────────── 2. stock explorer ─────────────────────────
with tab_stock:
    snap = data.latest_snapshot()
    symbols = sorted(snap["symbol"])
    f1, f2, _ = st.columns([1.2, 2, 3], vertical_alignment="bottom")
    symbol = f1.selectbox("Company", symbols, index=symbols.index("NABIL") if "NABIL" in symbols else 0,
                          help="Type to search by symbol")
    period = f2.segmented_control("Range", ["6M", "1Y", "3Y", "5Y", "All"], default="1Y", key="stock_range") or "1Y"

    hist = data.price_history(symbol)
    if hist.empty:
        empty("No history", "This symbol has no price history in the data lake.")
    else:
        hist["date"] = pd.to_datetime(hist["date"])
        ca = hist[hist["corporate_action"]]          # over the full history, not just the range
        if period != "All":
            years = {"6M": 0.5, "1Y": 1, "3Y": 3, "5Y": 5}[period]
            hist = hist[hist["date"] >= hist["date"].max() - pd.DateOffset(days=int(365 * years))]

        s = snap[snap["symbol"] == symbol].iloc[0]
        lo, hi = s["low_52w"], s["high_52w"]
        pos = min(max((s["close"] - lo) / (hi - lo), 0), 1) * 100 if pd.notna(lo) and hi > lo else 50
        st.markdown(
            f"<div class='nx-hero'><div><div class='sym'>{html.escape(symbol)}</div>"
            f"<div class='co'>{html.escape(str(s['company_name'] or symbol))}</div>"
            f"<div style='margin-top:8px'><span class='nx-tag'>{html.escape(str(s['sector']))}</span>"
            f"<span class='nx-tag'>as of {s['date']}</span></div></div>"
            f"<div><div class='px'>Rs {s['close']:,.2f}</div><div style='margin-top:4px'>{pill(s['change_pct'])}"
            f" <span style='color:#94a3b8;font-size:.8rem'>today</span></div></div>"
            f"<div class='nx-range'><div class='cap'>52-week range</div><div class='trk'><i style='left:calc({pos:.0f}% - 2px)'></i></div>"
            f"<div class='ends'><span>Rs {lo:,.0f}</span><span>{pos:.0f}% of range</span><span>Rs {hi:,.0f}</span></div></div></div>",
            unsafe_allow_html=True)
        st.write("")
        m = st.columns(4)
        m[0].metric("1-year return", f"{s['ret_1y']:+.2f}%" if pd.notna(s["ret_1y"]) else "—",
                    help="Bonus-adjusted price change over the last 12 months")
        m[1].metric("RSI (14)", f"{s['rsi_14']:.1f}" if pd.notna(s["rsi_14"]) else "—",
                    delta=str(s["rsi_signal"]).title(), delta_color="off",
                    help="Momentum 0–100. Below 30 = oversold, above 70 = overbought")
        m[2].metric("Trend", str(s["trend"]).title(), help="From SMA 20/50/200 alignment")
        m[3].metric("Volatility (20d, annualised)", f"{s['volatility_20']:.1f}%" if pd.notna(s["volatility_20"]) else "—",
                    help="How much the price swings; higher = riskier")
        _, _, preds = data.ml_results()
        pred = preds[preds["symbol"] == symbol] if not preds.empty else preds
        if not pred.empty:
            p = pred.iloc[0]
            st.caption(f"Model estimate: **{p['p_up'] * 100:.0f}% chance of closing higher** on the next "
                       f"trading day → {p['signal'].lower()}. Experimental — daily moves are mostly noise "
                       f"(see the Pipeline tab). Not investment advice.")

        with st.container(key="card_stock"):
            section(f"{symbol} price & indicators", "Candles with SMA 20/50/200 and Bollinger band · volume · RSI")
            fig = make_subplots(rows=3, cols=1, shared_xaxes=True, row_heights=[0.6, 0.15, 0.25],
                                vertical_spacing=0.03)
            fig.add_trace(go.Scatter(x=hist["date"], y=hist["bb_upper"], line=dict(width=0), hoverinfo="skip",
                                     showlegend=False), row=1, col=1)
            fig.add_trace(go.Scatter(x=hist["date"], y=hist["bb_lower"], line=dict(width=0), fill="tonexty",
                                     fillcolor=BAND, name="Bollinger band (20, 2σ)", hoverinfo="skip"), row=1, col=1)
            candles(fig, hist, 1, "adj_open", "adj_high", "adj_low", "adj_close", "date")
            for (col, label), color in zip([("sma_20", "SMA 20"), ("sma_50", "SMA 50"), ("sma_200", "SMA 200")], SERIES):
                fig.add_trace(go.Scatter(x=hist["date"], y=hist[col], name=label,
                                         line=dict(color=color, width=1.8)), row=1, col=1)
            fig.add_trace(go.Bar(x=hist["date"], y=hist["volume"], name="Volume", marker_color=AXIS,
                                 showlegend=False), row=2, col=1)
            fig.add_trace(go.Scatter(x=hist["date"], y=hist["rsi_14"], name="RSI 14",
                                     line=dict(color=SERIES[0], width=2), showlegend=False), row=3, col=1)
            fig.add_hrect(y0=30, y1=70, fillcolor="#f1f5f9", opacity=0.7, line_width=0, row=3, col=1)
            for level in (30, 70):
                fig.add_hline(y=level, line=dict(color=AXIS, width=1, dash="dot"), row=3, col=1)
            fig.update_yaxes(title_text="Price (Rs, adjusted)", row=1, col=1)
            fig.update_yaxes(title_text="Volume", row=2, col=1)
            fig.update_yaxes(title_text="RSI", range=[0, 100], tickvals=[30, 50, 70], row=3, col=1)
            st.plotly_chart(style(fig, 640), key="stock_chart", config=PLOT_CONFIG)
            st.caption("Prices are adjusted for bonus and right shares, so the chart has "
                       "no artificial drops. The shaded RSI zone is neutral (30–70).")

        with st.expander(f"Table view & detected corporate actions ({len(ca)})"):
            st.markdown("**Bonus / right share adjustments** (opening gap beyond the ±10 % circuit)")
            if ca.empty:
                st.caption("None detected for this company.")
            else:
                st.dataframe(ca[["date", "prev_close", "open", "close"]].assign(
                    gap_ratio=(ca["open"] / ca["prev_close"]).round(3)), hide_index=True)
            st.markdown("**Last 30 trading days**")
            st.dataframe(hist.tail(30).iloc[::-1][["date", "adj_open", "adj_high", "adj_low", "adj_close",
                                                    "volume", "sma_20", "sma_50", "sma_200", "rsi_14"]],
                         hide_index=True)


# ───────────────────────── 3. market & sectors ─────────────────────────
with tab_market:
    mk = data.market_daily()
    mk["date"] = pd.to_datetime(mk["date"])
    period = st.segmented_control("Range", ["1Y", "3Y", "5Y", "10Y", "All"], default="5Y", key="mk_range") or "5Y"
    if period != "All":
        mk_view = mk[mk["date"] >= mk["date"].max() - pd.DateOffset(years=int(period[:-1]))]
    else:
        mk_view = mk
    last = mk.iloc[-1]
    m = st.columns(4)
    m[0].metric("NEPSE index", f"{last['close']:,.2f}", f"{last['change_pct']:+.2f}%")
    m[1].metric("SMA 50 / SMA 200", f"{last['sma_50']:,.0f} / {last['sma_200']:,.0f}",
                help="Index above both averages = healthy uptrend")
    m[2].metric("RSI (14)", f"{last['rsi_14']:.1f}", help="Below 30 oversold, above 70 overbought")
    m[3].metric("Market turnover (last day)", rupees(last["turnover"] or 0))
    st.write("")

    with st.container(key="card_index"):
        section("NEPSE index", "Index level with 50- and 200-day moving averages")
        fig = go.Figure()
        for (col, label), color in zip([("close", "NEPSE index"), ("sma_50", "SMA 50"), ("sma_200", "SMA 200")], SERIES):
            fig.add_trace(go.Scatter(x=mk_view["date"], y=mk_view[col], name=label, line=dict(color=color, width=2)))
        fig.update_yaxes(title_text="Index points")
        st.plotly_chart(style(fig, 360), key="nepse_chart", config=PLOT_CONFIG)

    left, right = st.columns(2)
    with left.container(key="card_yearly"):
        section("Yearly return", "NEPSE index, calendar years since 2010")
        yearly = (mk[mk["date"].dt.year >= 2010].groupby(mk["date"].dt.year)["close"]
                  .agg(["first", "last"]).assign(ret=lambda d: (d["last"] / d["first"] - 1) * 100).reset_index())
        fig = go.Figure(go.Bar(x=yearly["date"], y=yearly["ret"], marker_color=signed_colors(yearly["ret"]),
                               text=[f"{v:+.0f}%" for v in yearly["ret"]], textposition="outside", cliponaxis=False,
                               hovertemplate="%{x}: %{y:+.2f}%<extra></extra>"))
        fig.update_yaxes(title_text="Return (%)", ticksuffix="%")
        st.plotly_chart(style(fig, 360, legend=False), key="yearly_chart", config=PLOT_CONFIG)

    with right.container(key="card_sector"):
        window = st.segmented_control("Sector window", ["30 days", "90 days", "1 year"], default="30 days",
                                      key="sector_window") or "30 days"
        days = {"30 days": 30, "90 days": 90, "1 year": 365}[window]
        sd = data.sector_daily()
        sd["date"] = pd.to_datetime(sd["date"])
        sd = sd[sd["date"] >= sd["date"].max() - pd.Timedelta(days=days)]
        agg = (sd.groupby("sector").agg(turnover=("turnover", "sum"), ret=("avg_return_pct", "mean"))
                 .sort_values("turnover").reset_index())
        fig = go.Figure(go.Bar(y=agg["sector"], x=agg["turnover"] / 1e9, orientation="h", marker_color=SERIES[0],
                               text=[f"{v / 1e9:,.1f}" for v in agg["turnover"]], textposition="outside", cliponaxis=False,
                               hovertemplate="%{y}: Rs %{x:,.2f} B<extra></extra>"))
        fig.update_xaxes(title_text="Turnover (Rs billion)")
        section(f"Turnover by sector", f"Where the money is flowing — last {window}")
        st.plotly_chart(style(fig, 310, legend=False), key="sector_turnover", config=PLOT_CONFIG)

    with st.container(key="card_sector_ret"):
        section("Average daily return by sector", f"Last {window} · green = rising, red = falling")
        agg = agg.sort_values("ret")
        fig = go.Figure(go.Bar(x=agg["sector"], y=agg["ret"], marker_color=signed_colors(agg["ret"]),
                               text=[f"{v:+.2f}%" for v in agg["ret"]], textposition="outside", cliponaxis=False,
                               hovertemplate="%{x}: %{y:+.3f}%<extra></extra>"))
        fig.update_yaxes(title_text="Avg daily return (%)", ticksuffix="%")
        st.plotly_chart(style(fig, 320, legend=False), key="sector_return", config=PLOT_CONFIG)
    st.caption(EQUITY_ONLY + " Returns are bonus-adjusted.")


# ───────────────────────── 4. screener ─────────────────────────
PRESETS = {
    "Oversold": dict(rsi=["OVERSOLD"]),
    "Overbought": dict(rsi=["OVERBOUGHT"]),
    "Uptrend": dict(trend=["UPTREND"]),
    "Downtrend": dict(trend=["DOWNTREND"]),
    "Volume spikes": dict(spikes=True),
}
with tab_screen:
    snap = data.latest_snapshot()
    with st.container(key="card_filters"):
        section("Find stocks", "Pick a quick preset or combine filters. Results update instantly.")
        preset = st.pills("Quick presets", list(PRESETS), key="scr_preset", selection_mode="single")
        pr = PRESETS.get(preset, {})
        f = st.columns([3, 2, 2, 2], vertical_alignment="bottom")
        query = f[0].text_input("Search symbol or company", placeholder="e.g. NABIL or hydro")
        sectors = f[1].multiselect("Sector", sorted(snap["sector"].dropna().unique()), placeholder="All sectors")
        trend = f[2].multiselect("Trend", ["UPTREND", "SIDEWAYS", "DOWNTREND"], default=pr.get("trend", []),
                                 placeholder="Any", key=f"scr_trend_{preset}")
        rsi = f[3].multiselect("RSI signal", ["OVERSOLD", "NEUTRAL", "OVERBOUGHT"], default=pr.get("rsi", []),
                               placeholder="Any", key=f"scr_rsi_{preset}")
        t = st.columns([1, 1, 6])
        spikes = t[0].toggle("Volume spikes", value=pr.get("spikes", False), key=f"scr_spk_{preset}")
        equity = t[1].toggle("Shares only", value=True)

    view = snap
    if query:
        q = query.strip().lower()
        view = view[view["symbol"].str.lower().str.contains(q, na=False)
                    | view["company_name"].fillna("").str.lower().str.contains(q, na=False)]
    if sectors:
        view = view[view["sector"].isin(sectors)]
    if trend:
        view = view[view["trend"].isin(trend)]
    if rsi:
        view = view[view["rsi_signal"].isin(rsi)]
    if spikes:
        view = view[view["volume_spike"]]
    if equity:
        view = view[view["instrument_type"] == "Equity"]

    k = st.columns(4)
    k[0].metric("Matches", f"{len(view)}", help=f"out of {len(snap)} securities")
    k[1].metric("Advancing today", f"{int((view['change_pct'] > 0).sum())}")
    k[2].metric("Oversold", f"{int((view['rsi_signal'] == 'OVERSOLD').sum())}")
    k[3].metric("Volume spikes", f"{int(view['volume_spike'].sum())}")
    st.caption(f"As of {snap['date'].max()} · click a column header to sort")

    if view.empty:
        empty("No securities match", "Try removing a filter or clearing the search.")
    else:
        table = view.sort_values("ret_1y", ascending=False).assign(
            pos_52w=lambda d: ((d["close"] - d["low_52w"]) / (d["high_52w"] - d["low_52w"])).clip(0, 1) * 100)
        st.dataframe(
            table[["symbol", "company_name", "sector", "close", "change_pct", "ret_1m", "ret_1y", "rsi_14",
                   "rsi_signal", "trend", "volume_ratio", "pos_52w", "volatility_20"]],
            hide_index=True, height=560, use_container_width=True,
            column_config={
                "symbol": st.column_config.TextColumn("Symbol", pinned=True),
                "company_name": st.column_config.TextColumn("Company", width="medium"),
                "sector": st.column_config.TextColumn("Sector"),
                "rsi_signal": st.column_config.TextColumn("RSI signal"),
                "trend": st.column_config.TextColumn("Trend"),
                "close": st.column_config.NumberColumn("Close (Rs)", format="%.2f"),
                "change_pct": st.column_config.NumberColumn("1D", format="%+.2f%%"),
                "ret_1m": st.column_config.NumberColumn("1M", format="%+.2f%%"),
                "ret_1y": st.column_config.NumberColumn("1Y", format="%+.2f%%"),
                "rsi_14": st.column_config.ProgressColumn("RSI 14", min_value=0, max_value=100, format="%.0f"),
                "volume_ratio": st.column_config.NumberColumn("Vol ÷ 20d avg", format="%.2fx",
                                                              help="3× or more is a volume spike"),
                "pos_52w": st.column_config.ProgressColumn("52-week position", min_value=0, max_value=100,
                                                           format="%.0f%%", help="0% = at 52-week low, 100% = at high"),
                "volatility_20": st.column_config.NumberColumn("Volatility", format="%.1f%%"),
            })


# ───────────────────────── 5. pipeline ─────────────────────────
def ml_section():
    metrics, features, _ = data.ml_results()
    if not metrics:
        return
    with st.container(key="card_ml"):
        section("Next-day direction model", "Random forest, time-based train/test split")
        c = st.columns(3)
        c[0].metric("Accuracy (test)", f"{float(metrics['accuracy']) * 100:.1f}%")
        c[1].metric("Baseline (always majority)", f"{float(metrics['baseline_accuracy']) * 100:.1f}%")
        c[2].metric("AUC", metrics["auc"], help="0.5 = coin flip, 1.0 = perfect")
        st.caption(f"Trained on {int(metrics['train_rows']):,} stock-days before {metrics['split_date']}, tested on "
                   f"{int(metrics['test_rows']):,} after. Overall the model barely beats guessing — daily moves are "
                   f"mostly noise — but its {int(metrics['confident_rows']):,} confident calls (≥ 60 % sure) were "
                   f"right {float(metrics['confident_accuracy']) * 100:.0f}% of the time.")
        features = features.sort_values("importance")
        fig = go.Figure(go.Bar(y=features["feature"], x=features["importance"], orientation="h",
                               marker_color=SERIES[0], text=[f"{v:.2f}" for v in features["importance"]],
                               textposition="outside", cliponaxis=False,
                               hovertemplate="%{y}: %{x:.3f}<extra></extra>"))
        fig.update_xaxes(title_text="Feature importance")
        st.plotly_chart(style(fig, 320, legend=False), key="ml_features", config=PLOT_CONFIG)


with tab_pipe:
    snap_live, alerts_live, mode, age, session, session_date = data.live_feed().state()
    c = st.columns(3)
    c[0].metric("Stream mode", mode)
    c[1].metric("Last stream update", data.fmt_age(age))
    c[2].metric("Symbols in live state", len(snap_live))
    st.write("")

    with st.container(key="card_arch"):
        section("Architecture", "How data flows from the exchange to this dashboard")
        st.graphviz_chart("""
        digraph {
          rankdir=LR; bgcolor="transparent";
          node [shape=box, style="rounded,filled", fillcolor="#f1f5f9", color="#cbd5e1", fontname="Helvetica", fontsize=11];
          edge [color="#94a3b8", fontname="Helvetica", fontsize=9];
          live [label="NEPSE API /\\nShareSansar"]; rec [label="Recordings /\\nhistorical CSV"];
          kafka [label="Kafka\\nnepse.ticks", fillcolor="#cde2fb"];
          stream [label="Spark Structured\\nStreaming", fillcolor="#cde2fb"];
          batch [label="Spark batch\\n(SQL, windows)", fillcolor="#cde2fb"];
          hdfs [label="HDFS data lake\\nbronze / silver / gold", fillcolor="#cde2fb"];
          out [label="Kafka\\nnepse.analytics / alerts"]; dash [label="Dashboard"];
          live -> kafka [label="LIVE"]; rec -> kafka [label="REPLAY"]; rec -> hdfs [label="bulk load"];
          kafka -> stream; stream -> hdfs; stream -> out; hdfs -> batch; batch -> hdfs;
          hdfs -> stream [label="reference\\n(stream-static join)", style=dashed];
          out -> dash; hdfs -> dash;
        }""")

    left, right = st.columns(2)
    with left:
        with st.container(key="card_kafka"):
            section("Kafka topics", "Message counts and sizes")
            try:
                st.dataframe(data.live_feed().topic_offsets(), hide_index=True, use_container_width=True)
            except Exception as exc:
                st.error(f"Kafka unavailable: {exc}")
        with st.container(key="card_dq"):
            section("Data quality", "What the batch layer cleaned")
            st.dataframe(data.data_quality(), hide_index=True, use_container_width=True)
        ml_section()
    with right:
        with st.container(key="card_hdfs"):
            section("HDFS data lake", "Parquet datasets by layer")
            usage = data.hdfs_usage()
            st.dataframe(usage, hide_index=True, height=520, use_container_width=True,
                         column_config={"size_mb": st.column_config.NumberColumn("Size (MB)", format="%.2f")})

with st.expander("Glossary"):
    st.markdown(
        "**LTP** – last traded price · **Circuit** – NEPSE halts a stock at ±10 % per day · "
        "**SMA** – simple moving average (20 / 50 / 200 days) · **RSI** – momentum 0–100, below 30 oversold, "
        "above 70 overbought · **Bollinger band** – SMA 20 ± 2 standard deviations · "
        "**Volume spike** – volume at least 3× its 20-day average · **Turnover** – value traded, in Rs")
st.markdown("<div class='nx-foot'>NEPSE Market Analytics · "
            "For information only — not investment advice.</div>", unsafe_allow_html=True)
