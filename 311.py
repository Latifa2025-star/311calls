# 311.py — NYC 311 Service Requests Explorer (Streamlit)
# ------------------------------------------------------
# Usage: streamlit run 311.py
# Data expected in the same folder:
#   - nyc311_12months.csv.gz  (recommended)  OR
#   - nyc311_sample.csv.gz / nyc311_12months.csv (fallbacks)

from __future__ import annotations
import os
import io
import math
from typing import Tuple, Optional, List

import pandas as pd
import numpy as np
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go

# ---------------------------- Page config & theme tweaks ---------------------------- #
st.set_page_config(
    page_title="NYC 311 Explorer",
    page_icon="📞",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Subtle style polish (larger metrics, nicer headers)
st.markdown(
    """
    <style>
      .block-container {padding-top: 1.2rem; padding-bottom: 2rem;}
      h1, h2, h3 { font-weight: 800; }
      .metric-label { font-size: 0.95rem !important; color: #5a5a5a !important; }
      .metric-value { font-size: 1.6rem !important; }
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("📞 NYC 311 Service Requests Explorer")
st.caption("Explore complaint types, resolution times, and closure rates by day and hour — powered by a compressed local dataset (`.csv.gz`).")

# ---------------------------- Data loading & prep ---------------------------------- #
DATA_CANDIDATES = [
    "nyc311_12months.csv.gz",   # preferred
    "nyc311_sample.csv.gz",
    "nyc311_12months.csv",
    "nyc311_sample.csv",
]

@st.cache_data(show_spinner=False)
def _read_any_dataframe() -> Tuple[pd.DataFrame, str]:
    """
    Read the first available file from DATA_CANDIDATES.
    Returns (df, filename_used).
    """
    for fname in DATA_CANDIDATES:
        if os.path.exists(fname):
            kw = {}
            if fname.endswith(".gz"):
                kw["compression"] = "gzip"
            df = pd.read_csv(fname, **kw)
            return df, fname
    raise FileNotFoundError(
        "No data file found. Please add 'nyc311_12months.csv.gz' "
        "next to 311.py (or one of the fallback names)."
    )

@st.cache_data(show_spinner=False)
def load_and_prepare() -> Tuple[pd.DataFrame, str]:
    df_raw, source = _read_any_dataframe()

    # Normalize datetimes
    for c in ["created_date", "closed_date", "resolution_action_updated_date"]:
        if c in df_raw.columns:
            df_raw[c] = pd.to_datetime(df_raw[c], errors="coerce")

    # Ensure numeric coords
    for c in ["latitude", "longitude"]:
        if c in df_raw.columns:
            df_raw[c] = pd.to_numeric(df_raw[c], errors="coerce")

    # hours_to_close if missing
    if "hours_to_close" not in df_raw.columns and {"created_date", "closed_date"}.issubset(df_raw.columns):
        df_raw["hours_to_close"] = (
            (df_raw["closed_date"] - df_raw["created_date"])
            .dt.total_seconds() / 3600.0
        )

    # Derived fields
    if "created_date" in df_raw.columns:
        df_raw["year"] = df_raw["created_date"].dt.year
        df_raw["month"] = df_raw["created_date"].dt.month
        df_raw["day_of_week"] = df_raw["created_date"].dt.day_name()
        df_raw["hour"] = df_raw["created_date"].dt.hour

    # Clean text columns for robustness
    for c in ["status", "complaint_type", "borough", "agency_name"]:
        if c in df_raw.columns:
            df_raw[c] = df_raw[c].astype(str)

    # Binary closed flag
    df_raw["is_closed"] = df_raw["status"].str.lower().str.contains("closed")

    return df_raw, source


with st.spinner("📊 Loading NYC 311 data..."):
    df, source_file = load_and_prepare()
st.success(f"Loaded **{len(df):,}** rows from **{source_file}**")

# ---------------------------- Sidebar filters -------------------------------------- #
st.sidebar.header("🎛️ Filters")

# Day filter
days_all = ["All"] + (df["day_of_week"].dropna().unique().tolist() if "day_of_week" in df else [])
day_choice = st.sidebar.selectbox("Day of Week", days_all, index=0)

# Hour range
hour_min, hour_max = st.sidebar.select_slider(
    "Hour range (24h)",
    options=list(range(0, 24)),
    value=(0, 23),
)

# Borough(s)
boroughs = sorted(df["borough"].dropna().unique().tolist()) if "borough" in df else []
borough_sel = st.sidebar.multiselect("Borough(s)", boroughs, default=boroughs[:3] if boroughs else [])

# Top N complaint types
top_n = st.sidebar.slider("Top complaint types to show", 5, 25, 12)

# Apply filters
df_f = df.copy()
if day_choice != "All":
    df_f = df_f[df_f["day_of_week"] == day_choice]
df_f = df_f[(df_f["hour"] >= hour_min) & (df_f["hour"] <= hour_max)]
if borough_sel:
    df_f = df_f[df_f["borough"].isin(borough_sel)]

# ---------------------------- KPIs ------------------------------------------------- #
col_a, col_b, col_c, col_d = st.columns(4)

with col_a:
    st.metric("Rows (after filters)", f"{len(df_f):,}")
with col_b:
    pct_closed = float(df_f["is_closed"].mean() * 100) if len(df_f) else 0.0
    st.metric("% Closed", f"{pct_closed:.1f}%")
with col_c:
    med_hours = df_f["hours_to_close"].median() if "hours_to_close" in df_f else np.nan
    st.metric("Median Hours to Close", f"{med_hours:.2f}" if pd.notnull(med_hours) else "—")
with col_d:
    top_ct = (df_f["complaint_type"].mode().iloc[0] if "complaint_type" in df_f and not df_f["complaint_type"].empty else "—")
    st.metric("Top Complaint Type", top_ct)

st.divider()

# ---------------------------- Charts ------------------------------------------------ #
def fig_top_types(data: pd.DataFrame, n: int) -> go.Figure:
    counts = (
        data["complaint_type"]
        .value_counts()
        .nlargest(n)
        .reset_index()
        .rename(columns={"index": "Complaint Type", "complaint_type": "Count"})
    )
    fig = px.bar(
        counts,
        x="Count",
        y="Complaint Type",
        orientation="h",
        color="Count",
        color_continuous_scale="YlOrRd",
        title=f"Top {n} Complaint Types",
    )
    fig.update_layout(
        height=520,
        yaxis=dict(autorange="reversed"),
        xaxis_title="Requests (count)",
        yaxis_title=None,
        coloraxis_showscale=False,
        margin=dict(l=10, r=10, t=60, b=10),
        title_font=dict(size=22, family="Arial Black"),
    )
    return fig

def fig_borough_breakdown(data: pd.DataFrame) -> go.Figure:
    if "borough" not in data:  # safety
        return go.Figure()
    counts = data["borough"].value_counts().reset_index().rename(columns={"index": "Borough", "borough": "Count"})
    fig = px.bar(
        counts, x="Borough", y="Count",
        text="Count",
        color="Borough",
        color_discrete_sequence=px.colors.qualitative.Set2,
        title="Requests by Borough",
    )
    fig.update_traces(texttemplate="%{text:,}", textposition="outside")
    fig.update_layout(
        height=520,
        xaxis_title=None, yaxis_title="Requests (count)",
        uniformtext_minsize=10, uniformtext_mode="hide",
        margin=dict(l=10, r=10, t=60, b=10),
        showlegend=False,
        title_font=dict(size=22, family="Arial Black"),
    )
    return fig

def fig_resolution_box(data: pd.DataFrame) -> go.Figure:
    if "hours_to_close" not in data or "complaint_type" not in data:
        return go.Figure()
    sub = data.dropna(subset=["hours_to_close"]).copy()
    if sub.empty:
        return go.Figure()
    # Clip to 99th percentile to avoid wild outliers spoiling scale
    q99 = sub["hours_to_close"].quantile(0.99)
    sub = sub[sub["hours_to_close"] <= q99]
    top_types = sub["complaint_type"].value_counts().nlargest(12).index
    sub = sub[sub["complaint_type"].isin(top_types)]
    fig = px.box(
        sub, x="complaint_type", y="hours_to_close",
        points=False,
        color="complaint_type",
        color_discrete_sequence=px.colors.qualitative.Set3,
        title="Hours to Close by Complaint Type (clipped at 99th pct)",
    )
    fig.update_layout(
        height=520,
        xaxis_title="Complaint Type", yaxis_title="Hours to Close",
        margin=dict(l=10, r=10, t=60, b=100),
        showlegend=False,
        title_font=dict(size=22, family="Arial Black"),
    )
    fig.update_xaxes(tickangle=-35)
    return fig

def fig_daily_trend(data: pd.DataFrame) -> go.Figure:
    if "created_date" not in data:
        return go.Figure()
    ts = (data
          .assign(day=lambda x: x["created_date"].dt.date)
          .groupby("day", as_index=False).size())
    fig = px.line(
        ts, x="day", y="size",
        markers=True,
        title="Daily Requests (after filters)",
    )
    fig.update_layout(
        height=420,
        xaxis_title="Date", yaxis_title="Requests",
        margin=dict(l=10, r=10, t=60, b=10),
        title_font=dict(size=22, family="Arial Black"),
    )
    return fig

def fig_map(data: pd.DataFrame) -> go.Figure:
    if not {"latitude", "longitude"}.issubset(data.columns):
        return go.Figure()
    sub = data.dropna(subset=["latitude", "longitude"]).copy()
    if sub.empty:
        return go.Figure()
    fig = px.density_mapbox(
        sub,
        lat="latitude", lon="longitude",
        radius=7,
        hover_name="complaint_type",
        hover_data={"borough": True, "agency_name": True, "status": True, "latitude": False, "longitude": False},
        color_continuous_scale="Inferno",
        mapbox_style="carto-positron",
        zoom=9, opacity=0.75,
        title="Complaint Density Across NYC",
    )
    fig.update_layout(height=640, margin=dict(l=0, r=0, t=60, b=0))
    return fig

# Layout row 1
c1, c2 = st.columns((1,1))
with c1:
    st.plotly_chart(fig_top_types(df_f, top_n), use_container_width=True)
with c2:
    st.plotly_chart(fig_borough_breakdown(df_f), use_container_width=True)

# Layout row 2
c3, c4 = st.columns((1,1))
with c3:
    st.plotly_chart(fig_resolution_box(df_f), use_container_width=True)
with c4:
    st.plotly_chart(fig_daily_trend(df_f), use_container_width=True)

st.subheader("🗺️ Map")
st.caption("Tip: Zoom and pan to explore hotspots. Hover for complaint type, agency and status.")
st.plotly_chart(fig_map(df_f), use_container_width=True)

st.divider()

# ---------------------------- Data table & download -------------------------------- #
st.subheader("📄 Data Preview")
show_cols = [c for c in [
    "created_date","closed_date","status","agency_name","complaint_type","descriptor",
    "borough","incident_zip","latitude","longitude","hours_to_close","day_of_week","hour"
] if c in df_f.columns]

st.dataframe(df_f[show_cols].head(1000), use_container_width=True, height=380)

# Download filtered CSV
csv_buf = io.StringIO()
df_f.to_csv(csv_buf, index=False)
st.download_button(
    "⬇️ Download filtered data as CSV",
    csv_buf.getvalue(),
    file_name="nyc311_filtered.csv",
    mime="text/csv",
)

# Footer
st.caption("Data: NYC Open Data (311 Service Requests, dataset id erm2-nwe9). App reads a local compressed CSV shipped with the repo.")



