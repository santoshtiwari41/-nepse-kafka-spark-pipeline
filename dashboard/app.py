"""NEPSE Market Analytics dashboard (Streamlit multipage app).

    streamlit run dashboard/app.py      (normally started by docker compose → http://localhost:8501)

Routes:  /  (live market) · /explore?symbol=NABIL · /market · /screener · /pipeline
"""
import streamlit as st

st.set_page_config(page_title="NEPSE Analytics", page_icon="📈", layout="wide", initial_sidebar_state="collapsed")

import ui  # noqa: E402

PAGES = [
    st.Page("views/live.py", title="Live market", url_path="live", default=True),
    st.Page("views/explore.py", title="Stock explorer", url_path="explore"),
    st.Page("views/market.py", title="Market & sectors", url_path="market"),
    st.Page("views/screener.py", title="Screener", url_path="screener"),
    st.Page("views/pipeline.py", title="Pipeline", url_path="pipeline"),
]
current = st.navigation(PAGES, position="hidden")

ui.chrome()
with st.container(key="navbar"):
    for col, page in zip(st.columns(len(PAGES) + 3), PAGES):
        col.page_link(page, label=page.title)
# underline the active page
active = PAGES.index(current)
st.markdown(f"<style>.st-key-navbar [data-testid='stColumn']:nth-child({active + 1}) a"
            "{border-bottom-color:#c9a227}.st-key-navbar [data-testid='stColumn']:nth-child("
            f"{active + 1}) a *{{color:#ffffff !important}}</style>", unsafe_allow_html=True)

current.run()

with st.expander("Glossary"):
    st.markdown(
        "**LTP** – last traded price · **Circuit** – NEPSE halts a stock at ±10 % per day · "
        "**SMA** – simple moving average (20 / 50 / 200 days) · **RSI** – momentum 0–100, below 30 oversold, "
        "above 70 overbought · **Bollinger band** – SMA 20 ± 2 standard deviations · "
        "**Volume spike** – volume at least 3× its 20-day average · **Turnover** – value traded, in Rs")
st.markdown("<div class='nx-foot'>NEPSE Market Analytics · "
            "For information only — not investment advice.</div>", unsafe_allow_html=True)
