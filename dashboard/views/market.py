import html
import time

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

import data
from ui import *  # noqa: F401,F403  (shared palette, helpers and layout)

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
