import html
import time

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

import data
from ui import *  # noqa: F401,F403  (shared palette, helpers and layout)

snap = data.latest_snapshot()
symbols = sorted(snap["symbol"])
wanted = str(st.query_params.get("symbol", "NABIL")).upper()
default = symbols.index(wanted) if wanted in symbols else (symbols.index("NABIL") if "NABIL" in symbols else 0)
f1, f2, _ = st.columns([1.2, 2, 3], vertical_alignment="bottom")
symbol = f1.selectbox("Company", symbols, index=default, key="explore_symbol", help="Type to search by symbol")
st.query_params["symbol"] = symbol          # shareable link: /explore?symbol=NABIL
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
    metrics, _, preds = data.ml_results()
    pred = preds[preds["symbol"] == symbol] if not preds.empty else preds
    with st.container(key="card_ml_stock"):
        section("Machine-learning outlook", "Random forest model (Spark MLlib) · next trading day")
        c1, c2 = st.columns([3, 2], vertical_alignment="center")
        if not pred.empty:
            p = pred.iloc[0]
            prob = float(p["p_up"]) * 100
            tone = {"LIKELY UP": UP, "LIKELY DOWN": DOWN}.get(p["signal"], INK2)
            c1.markdown(
                f"<div style='display:flex;align-items:baseline;gap:14px;flex-wrap:wrap'>"
                f"<span style='font-size:2rem;font-weight:700;color:#111827'>{prob:.0f}%</span>"
                f"<span style='color:#4b5563'>chance of closing higher tomorrow</span>"
                f"<span style='font-weight:700;letter-spacing:.06em;font-size:.78rem;color:{tone}'>"
                f"{html.escape(str(p['signal']))}</span></div>"
                f"<div style='position:relative;height:8px;background:linear-gradient(90deg,#f3d4d1,#e5e8ec 50%,#cfe8d8);"
                f"margin:14px 0 6px'><i style='position:absolute;left:calc({prob:.0f}% - 2px);top:-5px;width:4px;"
                f"height:18px;background:#111827'></i></div>"
                f"<div style='display:flex;justify-content:space-between;font-size:.74rem;color:#9ca3af'>"
                f"<span>0% likely down</span><span>50%</span><span>100% likely up</span></div>",
                unsafe_allow_html=True)
        else:
            c1.markdown("**No prediction for this stock.** The model needs about 200 trading days of history "
                        "for its long-term indicators, so recently listed stocks are skipped.")
        if metrics:
            c2.markdown(
                f"<div style='font-size:.8rem;color:#4b5563;line-height:1.7'>"
                f"<b>Model accuracy on unseen data (2025 onward)</b><br>"
                f"Accuracy {float(metrics['accuracy']) * 100:.1f}% · baseline {float(metrics['baseline_accuracy']) * 100:.1f}% · "
                f"AUC {metrics['auc']}<br>"
                f"<span style='color:#9ca3af'>Experimental: daily price moves are mostly random. "
                f"Not investment advice.</span></div>", unsafe_allow_html=True)

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
