import html
import time

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

import data
from ui import *  # noqa: F401,F403  (shared palette, helpers and layout)

PRESETS = {
    "Oversold": dict(rsi=["OVERSOLD"]),
    "Overbought": dict(rsi=["OVERBOUGHT"]),
    "Uptrend": dict(trend=["UPTREND"]),
    "Downtrend": dict(trend=["DOWNTREND"]),
    "Volume spikes": dict(spikes=True),
}
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
