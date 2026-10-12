import html
import time

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

import data
from ui import *  # noqa: F401,F403  (shared palette, helpers and layout)

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
