# 311.py — NYC 311 Service Requests Explorer (Streamlit)
# ------------------------------------------------------
# Works with a compressed CSV placed next to this file:
#   nyc311_12months.csv.gz
#
# Requirements (requirements.txt):
# streamlit>=1.36
# pandas>=2.1
# numpy>=1.26
# plotly>=5.24

from __future__ import annotations
import os
from datetime import datetime
import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st

# ------------ Page config ------------
st.set_page_config(
    page_title="NYC 311 Service Requests Explorer",
    page_icon="📞",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("📞 NYC 311 Service Requests Explorer")
st.caption(
    "Explore complaint types, resolution times, and closure rates by day and hour — "
    "powered by a compressed local dataset (.csv.gz)."
)

DATA_FILE = "nyc311_12months.csv.gz"  # shipped with the repo


# ------------ Data loading ------------
@st.cache_data(show_spinner=True)
def load_data(path: str) -> pd.DataFrame:
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"Could not find {path}. Make sure it is committed in the same folder as 311.py."
        )

    df = pd.read_csv(path, compression="gzip")

    # Type coercion
    for c in ["created_date", "closed_date", "resolution_action_updated_date"]:
        if c in df.columns:
            df[c] = pd.to_datetime(df[c], errors="coerce")

    # Basic columns that the app relies on; fill if missing
    if "status" not in df:
        df["status"] = "Unspecified"

    # Derive helpers
    if "created_date" in df.columns:
        df["day_of_week"] = df["created_date"].dt.day_name()
        df["hour"] = df["created_date"].dt.hour

    # Hours to close
    if {"created_date", "closed_date"}.issubset(df.columns):
        df["hours_to_close"] = (
            (df["closed_date"] - df["created_date"]).dt.total_seconds() / 3600.0
        )

    # Normalize text columns we display
    for tcol in ["complaint_type", "borough", "agency_name", "status"]:
        if tcol in df.columns:
            df[tcol] = df[tcol].fillna("(Unknown)")

    # is_closed flag
    df["is_closed"] = df["status"].str.lower().eq("closed")

    # Light numeric coercion to avoid plotting issues
    for c in ["latitude", "longitude"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")

    return df


with st.spinner("Loading dataset…"):
    df = load_data(DATA_FILE)

st.success(f"Loaded {len(df):,} rows from **{DATA_FILE}**")


# ------------ Sidebar filters ------------
with st.sidebar:
    st.header("Filters")
    # Day
    days_all = ["All"] + list(pd.Index(
        ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    ))
    sel_day = st.selectbox("Day of Week", days_all, index=0)

    # Hour
    sel_hour = st.slider("Hour range (24h)", 0, 23, (0, 23))

    # Borough(s)
    boroughs = ["All"]
    if "borough" in df.columns:
        boroughs += sorted([b for b in df["borough"].dropna().unique()])
    sel_boroughs = st.multiselect("Borough(s)", boroughs if boroughs else ["All"], default=["All"])

    # Top N
    top_n = st.slider("Top complaint types to show", 5, 20, 10, step=1)


# ------------ Apply filters ------------
df_f = df.copy()

if sel_day != "All" and "day_of_week" in df_f.columns:
    df_f = df_f[df_f["day_of_week"] == sel_day]

h0, h1 = sel_hour
if "hour" in df_f.columns:
    df_f = df_f[(df_f["hour"] >= h0) & (df_f["hour"] <= h1)]

if sel_boroughs and "All" not in sel_boroughs and "borough" in df_f.columns:
    df_f = df_f[df_f["borough"].isin(sel_boroughs)]

# ------------ KPIs ------------
c1, c2, c3, c4 = st.columns(4)
c1.metric("Rows (after filters)", f"{len(df_f):,}")
closed_pct = (df_f["is_closed"].mean() * 100) if len(df_f) else 0.0
c2.metric("% Closed", f"{closed_pct:,.1f}%")
med_hours = df_f["hours_to_close"].median() if "hours_to_close" in df_f and len(df_f) else np.nan
c3.metric("Median Hours to Close", f"{med_hours:,.2f}" if pd.notnull(med_hours) else "—")
top_type = (
    df_f["complaint_type"].mode().iloc[0]
    if "complaint_type" in df_f and not df_f["complaint_type"].empty
    else "—"
)
c4.metric("Top Complaint Type", top_type)

st.divider()


# ------------ Figure helpers ------------
def safe_top_counts(df_in: pd.DataFrame, col: str, n: int) -> pd.DataFrame:
    """Return a tidy DataFrame with columns [label, count] for top-N, never empty/ambiguous."""
    if col not in df_in or df_in[col].dropna().empty:
        return pd.DataFrame({"label": [], "count": []})
    s = df_in[col].value_counts(dropna=False).head(max(1, n))
    # Convert Series to a clean DF with unique column names
    out = s.reset_index()
    out.columns = ["label", "count"]
    # Ensure types are plot-friendly
    out["label"] = out["label"].astype(str)
    out["count"] = pd.to_numeric(out["count"], errors="coerce").fillna(0).astype(int)
    return out


def fig_top_types(df_in: pd.DataFrame, n: int):
    counts = safe_top_counts(df_in, "complaint_type", n)
    if counts.empty:
        return px.bar(title="Top Complaint Types (no data)")

    fig = px.bar(
        counts,
        x="count",
        y="label",
        orientation="h",
        color="count",
        color_continuous_scale="sunset",
        title=f"Top {len(counts)} Complaint Types",
    )
    fig.update_layout(
        yaxis_title=None,
        xaxis_title="Requests (count)",
        yaxis=dict(autorange="reversed"),
        coloraxis_showscale=False,
        height=480,
        margin=dict(l=10, r=10, t=60, b=10),
    )
    return fig


def fig_status_pie(df_in: pd.DataFrame):
    counts = safe_top_counts(df_in, "status", 20)
    if counts.empty:
        return px.pie(title="Status Breakdown (no data)")

    fig = px.pie(
        counts, names="label", values="count",
        hole=0.4, title="Status Breakdown"
    )
    fig.update_traces(textposition="outside", textinfo="label+percent")
    fig.update_layout(height=420, margin=dict(l=10, r=10, t=60, b=10))
    return fig


def fig_duration_box(df_in: pd.DataFrame, n: int):
    if "hours_to_close" not in df_in or "complaint_type" not in df_in:
        return px.box(title="Resolution Time by Complaint Type (no data)")

    # Focus on top-N complaint types in this filtered slice
    top_labels = (
        df_in["complaint_type"].value_counts().head(max(1, n)).index.tolist()
    )
    sub = df_in[df_in["complaint_type"].isin(top_labels)].copy()
    sub = sub.dropna(subset=["hours_to_close"])
    if sub.empty:
        return px.box(title="Resolution Time by Complaint Type (no data)")

    fig = px.box(
        sub,
        x="complaint_type",
        y="hours_to_close",
        points=False,
        title="Resolution Time by Complaint Type (hours)",
        color="complaint_type",
        color_discrete_sequence=px.colors.qualitative.Set2,
    )
    fig.update_layout(
        xaxis_title=None,
        yaxis_title="Hours to Close",
        showlegend=False,
        height=520,
        margin=dict(l=10, r=10, t=60, b=10),
    )
    return fig


def fig_heatmap_day_hour(df_in: pd.DataFrame):
    if not {"day_of_week", "hour"}.issubset(df_in.columns):
        return px.imshow([[0]], title="Requests Heatmap (no data)")

    # Build pivot Monday→Sunday, hours 0..23
    day_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    pivot = (
        df_in.groupby(["day_of_week", "hour"])
        .size()
        .rename("count")
        .reset_index()
        .pivot(index="day_of_week", columns="hour", values="count")
        .reindex(day_order)
        .fillna(0)
    )

    fig = px.imshow(
        pivot,
        color_continuous_scale="YlOrRd",
        title="When are requests made? (Day × Hour)",
        aspect="auto",
    )
    fig.update_layout(height=520, margin=dict(l=10, r=10, t=60, b=10))
    fig.update_xaxes(title="Hour of Day (24h)")
    fig.update_yaxes(title=None)
    return fig


# ------------ Layout with charts ------------
# Row: Top types + status pie
colA, colB = st.columns([2, 1])
with colA:
    st.plotly_chart(fig_top_types(df_f, top_n), use_container_width=True)
with colB:
    st.plotly_chart(fig_status_pie(df_f), use_container_width=True)

# Row: duration box + heatmap
colC, colD = st.columns([2, 2])
with colC:
    st.plotly_chart(fig_duration_box(df_f, top_n), use_container_width=True)
with colD:
    st.plotly_chart(fig_heatmap_day_hour(df_f), use_container_width=True)

st.caption(
    "Tip: Use the filters on the left to focus by day, hour window, and borough(s). "
    "Charts update instantly on your compressed local dataset."
)





