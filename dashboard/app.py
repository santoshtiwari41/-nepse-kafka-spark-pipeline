"""NEPSE Market Analytics dashboard (Streamlit).

    streamlit run dashboard/app.py      (normally started by docker compose → http://localhost:8501)
"""
import time

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

import data

st.set_page_config(page_title="NEPSE Analytics", page_icon="📈", layout="wide")

# ───────────────────────── chart style (validated palette) ─────────────────────────
SURFACE, INK, INK2, MUTED = "#fcfcfb", "#0b0b0b", "#52514e", "#898781"
GRID, AXIS, MIDPOINT = "#e1e0d9", "#c3c2b7", "#f0efec"
SERIES = ["#2a78d6", "#eb6834", "#1baf7a"]          # categorical slots 1-3 (validated all-pairs)
UP, DOWN = "#0ca30c", "#d03b3b"                      # price direction, always with +/− in text
BAND = "rgba(137,135,129,0.12)"
FONT = "system-ui, -apple-system, Segoe UI, sans-serif"
MODE_BADGE = {
    "LIVE": ("#d03b3b", "● LIVE", "Real-time ticks from NEPSE are streaming through Kafka → Spark"),
    "REPLAY": ("#eb6834", "↻ REPLAY", "A recorded/historical session is being streamed through Kafka → Spark"),
    "HISTORICAL": ("#2a78d6", "◷ HISTORICAL", "No active stream — showing the batch layer (last trading day)"),
}


def style(fig, height=420, legend=True):
    fig.update_layout(
        template="none", height=height, paper_bgcolor=SURFACE, plot_bgcolor=SURFACE,
        font=dict(family=FONT, color=INK2, size=12), margin=dict(l=64, r=16, t=32, b=44),
        showlegend=legend, hovermode="x unified",
        legend=dict(orientation="h", x=0, y=1.0, yanchor="bottom", font=dict(color=INK2), traceorder="normal"),
        hoverlabel=dict(bgcolor="white", font=dict(family=FONT, color=INK)))
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


def badge(mode, detail):
    color, label, text = MODE_BADGE[mode]
    st.markdown(
        f"<span style='background:{color};color:white;padding:4px 12px;border-radius:12px;"
        f"font-weight:600;font-size:0.95rem'>{label}</span>"
        f"<span style='color:{INK2};margin-left:12px'>{text} · {detail}</span>",
        unsafe_allow_html=True)


def rupees(x):
    return f"Rs {x / 1e9:,.2f} B" if x >= 1e9 else f"Rs {x / 1e6:,.1f} M"


EQUITY_ONLY = "Ordinary shares only (debentures and mutual funds excluded)."

# ───────────────────────── header ─────────────────────────
st.title("NEPSE Market Analytics")
st.caption("Kafka → Spark Structured Streaming + Spark batch → HDFS data lake · "
           "real-time and historical Nepal Stock Exchange analytics")

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
    badge(mode, detail)
    note = st.empty()      # fixed slot → page layout stays identical between refreshes
    if not data.live_feed().ready:
        note.caption("⏳ Catching up with the Kafka stream… the live view switches over in a few seconds.")
    eq = df[df["instrument_type"] == "Equity"].copy()
    if eq.empty:
        st.info("No market data yet. Run the batch layer (`./scripts/run_batch.sh`) or start the stream and a producer.")
        return

    adv, dec = (eq["change_pct"] > 0).sum(), (eq["change_pct"] < 0).sum()
    k = st.columns(5)
    k[0].metric("Stocks traded", f"{len(eq)}")
    k[1].metric("Advancers ▲", f"{adv}")
    k[2].metric("Decliners ▼", f"{dec}")
    k[3].metric("Turnover", rupees(eq["turnover"].fillna(0).sum()))
    k[4].metric("Alerts this session", f"{len(alerts)}" if mode != "HISTORICAL" else "—")

    eq["turnover_m"] = eq["turnover"] / 1e6
    cols = ["symbol", "ltp", "change_pct", "volume"]
    cfg = {"symbol": st.column_config.TextColumn("Symbol"),
           "ltp": st.column_config.NumberColumn("LTP", format="%.2f"),
           "change_pct": st.column_config.NumberColumn("Change", format="%+.2f%%"),
           "volume": st.column_config.NumberColumn("Volume", format="%d"),
           "turnover_m": st.column_config.NumberColumn("Turnover (Rs M)", format="%.1f")}
    c1, c2, c3 = st.columns(3)
    c1.markdown("**Top gainers**")
    c1.dataframe(eq.nlargest(10, "change_pct")[cols], hide_index=True, column_config=cfg, use_container_width=True)
    c2.markdown("**Top losers**")
    c2.dataframe(eq.nsmallest(10, "change_pct")[cols], hide_index=True, column_config=cfg, use_container_width=True)
    c3.markdown("**Most active (turnover)**")
    c3.dataframe(eq.nlargest(10, "turnover")[["symbol", "ltp", "change_pct", "turnover_m"]],
                 hide_index=True, column_config=cfg, use_container_width=True)
    st.caption(EQUITY_ONLY)

    left, right = st.columns([3, 2])
    with left:
        st.markdown("**Sector map** — tile size = turnover, colour = % change")
        tm = eq[eq["turnover"] > 0].assign(change_pct=lambda d: d["change_pct"].round(2))
        fig = px.treemap(tm, path=[px.Constant("NEPSE"), "sector", "symbol"], values="turnover",
                         color="change_pct", color_continuous_scale=[DOWN, MIDPOINT, UP],
                         color_continuous_midpoint=0, range_color=(-5, 5),
                         custom_data=["change_pct"])
        fig.update_traces(texttemplate="%{label}<br>%{customdata[0]:+.2f}%",
                          hovertemplate="%{label}<br>Turnover Rs %{value:,.0f}<br>Change %{customdata[0]:+.2f}%",
                          marker=dict(line=dict(color=SURFACE, width=2)))
        fig.update_layout(coloraxis_colorbar=dict(title="%", ticksuffix="%"))
        st.plotly_chart(style(fig, 460, legend=False), key="treemap")
    with right:
        st.markdown("**Alerts** (Spark streaming)")
        if alerts.empty:
            st.caption("No alerts in this session." if mode != "HISTORICAL"
                       else "Alerts appear while a LIVE or REPLAY stream is running.")
        else:
            icons = {"UPPER_CIRCUIT": "🔺", "LOWER_CIRCUIT": "🔻", "VOLUME_SPIKE": "📊", "BIG_MOVE": "⚡"}
            lines = [f"`{str(a.event_time)[11:19]}` {icons.get(a.alert_type, '•')} **{a.alert_type.replace('_', ' ')}** — {a.message}"
                     for a in alerts.head(14).itertuples()]
            st.markdown("  \n".join(lines))

    if mode != "HISTORICAL":
        intraday(eq, session)


def intraday(eq, session):
    st.markdown("**Intraday candles** (1-minute windows computed by Spark, read from HDFS)")
    symbols = eq.sort_values("turnover", ascending=False)["symbol"].tolist()
    c1, c2 = st.columns([1, 3])
    symbol = c1.selectbox("Symbol", symbols, key="intraday_symbol")
    interval = c2.radio("Interval", ["1 min", "5 min"], horizontal=True, key="intraday_interval")
    cdf = data.intraday_candles(symbol, session)
    if cdf.empty:
        st.caption("Candles are written when each 1-minute window closes — they appear shortly.")
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
    st.plotly_chart(style(fig, 420, legend=False), key="intraday_chart")


with tab_live:
    live_market()


# ───────────────────────── 2. stock explorer ─────────────────────────
with tab_stock:
    snap = data.latest_snapshot()
    symbols = sorted(snap["symbol"])
    f1, f2 = st.columns([1, 3])
    symbol = f1.selectbox("Symbol", symbols, index=symbols.index("NABIL") if "NABIL" in symbols else 0)
    period = f2.radio("Range", ["6M", "1Y", "3Y", "5Y", "All"], index=1, horizontal=True)

    hist = data.price_history(symbol)
    if hist.empty:
        st.warning("No history for this symbol.")
    else:
        hist["date"] = pd.to_datetime(hist["date"])
        ca = hist[hist["corporate_action"]]          # over the full history, not just the range
        if period != "All":
            years = {"6M": 0.5, "1Y": 1, "3Y": 3, "5Y": 5}[period]
            hist = hist[hist["date"] >= hist["date"].max() - pd.DateOffset(days=int(365 * years))]

        s = snap[snap["symbol"] == symbol].iloc[0]
        st.markdown(f"**{s['company_name'] or symbol}** · {s['sector']} · as of {s['date']}")
        m = st.columns(6)
        m[0].metric("Close", f"Rs {s['close']:,.2f}", f"{s['change_pct']:+.2f}%")
        m[1].metric("1-year return", f"{s['ret_1y']:+.2f}%" if pd.notna(s["ret_1y"]) else "—")
        m[2].metric("52-week range", f"{s['low_52w']:,.0f} – {s['high_52w']:,.0f}")
        m[3].metric(f"RSI (14) · {s['rsi_signal'].lower()}", f"{s['rsi_14']:.1f}" if pd.notna(s["rsi_14"]) else "—")
        m[4].metric("Trend", s["trend"])
        m[5].metric("Volatility (20d, ann.)", f"{s['volatility_20']:.1f}%" if pd.notna(s["volatility_20"]) else "—")

        fig = make_subplots(rows=3, cols=1, shared_xaxes=True, row_heights=[0.6, 0.15, 0.25],
                            vertical_spacing=0.03)
        fig.add_trace(go.Scatter(x=hist["date"], y=hist["bb_upper"], line=dict(width=0), hoverinfo="skip",
                                 showlegend=False), row=1, col=1)
        fig.add_trace(go.Scatter(x=hist["date"], y=hist["bb_lower"], line=dict(width=0), fill="tonexty",
                                 fillcolor=BAND, name="Bollinger band (20, 2σ)", hoverinfo="skip"), row=1, col=1)
        candles(fig, hist, 1, "adj_open", "adj_high", "adj_low", "adj_close", "date")
        for (col, label), color in zip([("sma_20", "SMA 20"), ("sma_50", "SMA 50"), ("sma_200", "SMA 200")], SERIES):
            fig.add_trace(go.Scatter(x=hist["date"], y=hist[col], name=label,
                                     line=dict(color=color, width=2)), row=1, col=1)
        fig.add_trace(go.Bar(x=hist["date"], y=hist["volume"], name="Volume", marker_color=AXIS,
                             showlegend=False), row=2, col=1)
        fig.add_trace(go.Scatter(x=hist["date"], y=hist["rsi_14"], name="RSI 14",
                                 line=dict(color=SERIES[0], width=2), showlegend=False), row=3, col=1)
        for level in (30, 70):
            fig.add_hline(y=level, line=dict(color=AXIS, width=1), row=3, col=1)
        fig.update_yaxes(title_text="Price (Rs, adjusted)", row=1, col=1)
        fig.update_yaxes(title_text="Volume", row=2, col=1)
        fig.update_yaxes(title_text="RSI", range=[0, 100], tickvals=[30, 50, 70], row=3, col=1)
        st.plotly_chart(style(fig, 640), key="stock_chart")
        st.caption("Prices are adjusted for bonus/right shares detected by the Spark batch layer, "
                   "so the chart has no artificial drops. RSI lines mark 30 (oversold) and 70 (overbought).")

        with st.expander(f"Table view & detected corporate actions ({len(ca)})"):
            st.markdown("**Bonus / right share adjustments** (opening gap beyond the ±10 % circuit)")
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
    period = st.radio("Range", ["1Y", "3Y", "5Y", "10Y", "All"], index=2, horizontal=True, key="mk_range")
    if period != "All":
        mk_view = mk[mk["date"] >= mk["date"].max() - pd.DateOffset(years=int(period[:-1]))]
    else:
        mk_view = mk
    last = mk.iloc[-1]
    m = st.columns(4)
    m[0].metric("NEPSE index", f"{last['close']:,.2f}", f"{last['change_pct']:+.2f}%")
    m[1].metric("SMA 50 / SMA 200", f"{last['sma_50']:,.0f} / {last['sma_200']:,.0f}")
    m[2].metric("RSI (14)", f"{last['rsi_14']:.1f}")
    m[3].metric("Market turnover (last day)", rupees(last["turnover"] or 0))

    fig = go.Figure()
    for (col, label), color in zip([("close", "NEPSE index"), ("sma_50", "SMA 50"), ("sma_200", "SMA 200")], SERIES):
        fig.add_trace(go.Scatter(x=mk_view["date"], y=mk_view[col], name=label, line=dict(color=color, width=2)))
    fig.update_yaxes(title_text="Index points")
    st.plotly_chart(style(fig, 380), key="nepse_chart")

    left, right = st.columns(2)
    with left:
        st.markdown("**NEPSE yearly return**")
        yearly = (mk[mk["date"].dt.year >= 2010].groupby(mk["date"].dt.year)["close"]
                  .agg(["first", "last"]).assign(ret=lambda d: (d["last"] / d["first"] - 1) * 100).reset_index())
        fig = go.Figure(go.Bar(x=yearly["date"], y=yearly["ret"], marker_color=signed_colors(yearly["ret"]),
                               text=[f"{v:+.0f}%" for v in yearly["ret"]], textposition="outside", cliponaxis=False,
                               hovertemplate="%{x}: %{y:+.2f}%<extra></extra>"))
        fig.update_yaxes(title_text="Return (%)", ticksuffix="%")
        st.plotly_chart(style(fig, 360, legend=False), key="yearly_chart")

    with right:
        window = st.radio("Sector window", ["30 days", "90 days", "1 year"], horizontal=True)
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
        st.markdown(f"**Turnover by sector — last {window}**")
        st.plotly_chart(style(fig, 360, legend=False), key="sector_turnover")

    st.markdown(f"**Average daily return by sector — last {window}**")
    agg = agg.sort_values("ret")
    fig = go.Figure(go.Bar(x=agg["sector"], y=agg["ret"], marker_color=signed_colors(agg["ret"]),
                           text=[f"{v:+.2f}%" for v in agg["ret"]], textposition="outside", cliponaxis=False,
                           hovertemplate="%{x}: %{y:+.3f}%<extra></extra>"))
    fig.update_yaxes(title_text="Avg daily return (%)", ticksuffix="%")
    st.plotly_chart(style(fig, 320, legend=False), key="sector_return")
    st.caption(EQUITY_ONLY + " Returns are bonus-adjusted.")


# ───────────────────────── 4. screener ─────────────────────────
with tab_screen:
    snap = data.latest_snapshot()
    f = st.columns([3, 2, 2, 1, 1])
    sectors = f[0].multiselect("Sector", sorted(snap["sector"].unique()))
    trend = f[1].multiselect("Trend", ["UPTREND", "SIDEWAYS", "DOWNTREND"])
    rsi = f[2].multiselect("RSI signal", ["OVERSOLD", "NEUTRAL", "OVERBOUGHT"])
    spikes = f[3].toggle("Volume spikes")
    equity = f[4].toggle("Shares only", value=True)

    view = snap
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

    st.caption(f"{len(view)} of {len(snap)} securities · batch layer, as of {snap['date'].max()}")
    st.dataframe(
        view.sort_values("ret_1y", ascending=False)[
            ["symbol", "sector", "close", "change_pct", "ret_1m", "ret_1y", "rsi_14", "rsi_signal", "trend",
             "volume_ratio", "low_52w", "high_52w", "volatility_20"]],
        hide_index=True, height=560,
        column_config={
            "symbol": st.column_config.TextColumn("Symbol"),
            "sector": st.column_config.TextColumn("Sector"),
            "rsi_signal": st.column_config.TextColumn("RSI signal"),
            "trend": st.column_config.TextColumn("Trend"),
            "close": st.column_config.NumberColumn("Close", format="%.2f"),
            "change_pct": st.column_config.NumberColumn("1D", format="%+.2f%%"),
            "ret_1m": st.column_config.NumberColumn("1M", format="%+.2f%%"),
            "ret_1y": st.column_config.NumberColumn("1Y", format="%+.2f%%"),
            "rsi_14": st.column_config.ProgressColumn("RSI 14", min_value=0, max_value=100, format="%.0f"),
            "volume_ratio": st.column_config.NumberColumn("Vol ÷ 20d avg", format="%.2fx"),
            "low_52w": st.column_config.NumberColumn("52W low", format="%.0f"),
            "high_52w": st.column_config.NumberColumn("52W high", format="%.0f"),
            "volatility_20": st.column_config.NumberColumn("Volatility", format="%.1f%%"),
        })


# ───────────────────────── 5. pipeline ─────────────────────────
with tab_pipe:
    st.markdown("**Architecture**")
    st.graphviz_chart("""
    digraph {
      rankdir=LR; bgcolor="transparent";
      node [shape=box, style="rounded,filled", fillcolor="#f0efec", color="#c3c2b7", fontname="Helvetica", fontsize=11];
      edge [color="#898781", fontname="Helvetica", fontsize=9];
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

    snap_live, alerts_live, mode, age, session, session_date = data.live_feed().state()
    c = st.columns(3)
    c[0].metric("Mode", mode)
    c[1].metric("Last stream update", data.fmt_age(age))
    c[2].metric("Symbols in live state", len(snap_live))

    left, right = st.columns(2)
    with left:
        st.markdown("**Kafka topics**")
        try:
            st.dataframe(data.live_feed().topic_offsets(), hide_index=True)
        except Exception as exc:
            st.error(f"Kafka unavailable: {exc}")
        st.markdown("**Data quality (batch cleaning)**")
        st.dataframe(data.data_quality(), hide_index=True)
    with right:
        st.markdown("**HDFS data lake (Parquet)**")
        usage = data.hdfs_usage()
        st.dataframe(usage, hide_index=True, height=520,
                     column_config={"size_mb": st.column_config.NumberColumn("Size (MB)", format="%.2f")})
