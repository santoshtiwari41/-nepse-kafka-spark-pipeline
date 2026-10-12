import html
import time

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

import data
from ui import *  # noqa: F401,F403  (shared palette, helpers and layout)

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


live_market()
