# 311.py — NYC 311 Service Requests Explorer (Streamlit)
# ------------------------------------------------------
# - Reads a compressed CSV (.csv.gz) shipped in the repo
# - Provides interactive, polished visualizations with narratives
# - Robust against empty filters / missing columns

from __future__ import annotations
import os
from typing import List, Tuple

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

# -----------------------------
# Basic config
# -----------------------------
st.set_page_config(
    page_title="NYC 311 Service Requests Explorer",
    page_icon="📞",
    layout="wide",
)

TITLE = "NYC 311 Service Requests Explorer"
SUBTITLE = (
    "Explore complaint types, resolution times, and closure rates by day and hour — "
    "powered by a compressed local dataset (.csv.gz)."
)
DATA_FILE = "nyc311_12months.csv.gz"  # change if your file is named differently

# -----------------------------
# Helpers
# -----------------------------
def fmt_int(n):
    try:
        return f"{int(n):,}"
    except Exception:
        return "—"

def safe_col(df: pd.DataFrame, col: str) -> bool:
    return (df is not None) and (col in df.columns)

def simplify_status(s: pd.Series) -> pd.Series:
    s = s.fillna("").str.lower()
    return np.where(s.str.contains("closed"), "Closed", "Open / In Progress")

# -----------------------------
# Load data (cached)
# -----------------------------
@st.cache_data(show_spinner=True)
def load_data(path: str) -> pd.DataFrame:
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"Data file '{path}' not found. "
            f"Upload it to the repo root next to 311.py."
        )
    df = pd.read_csv(path, compression="gzip")
    # Basic typing
    for c in ["created_date", "closed_date", "resolution_action_updated_date"]:
        if c in df:
            df[c] = pd.to_datetime(df[c], errors="coerce")
    for c in ["latitude", "longitude"]:
        if c in df:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    if "hours_to_close" not in df and {"created_date", "closed_date"}.issubset(df.columns):
        delta = (df["closed_date"] - df["created_date"]).dt.total_seconds() / 3600.0
        df["hours_to_close"] = delta
    # essentials for charts
    if "created_date" in df:
        df["day_of_week"] = df["created_date"].dt.day_name()
        df["hour"] = df["created_date"].dt.hour
        df["year"] = df["created_date"].dt.year
        df["month"] = df["created_date"].dt.month
    if "status" in df:
        df["status_simple"] = simplify_status(df["status"])
    if "borough" in df:
        df["borough"] = df["borough"].fillna("Unspecified")
    if "complaint_type" in df:
        df["complaint_type"] = df["complaint_type"].fillna("(Unknown)")
    return df

# -----------------------------
# Charts
# -----------------------------
def fig_top_types(df: pd.DataFrame, n: int) -> Tuple[go.Figure, pd.DataFrame]:
    if df.empty or not safe_col(df, "complaint_type"):
        return go.Figure(), pd.DataFrame()
    counts = (
        df["complaint_type"].value_counts()
        .head(n)
        .rename_axis("complaint_type")
        .reset_index(name="count")
    )
    fig = px.bar(
        counts,
        x="count",
        y="complaint_type",
        orientation="h",
        color="count",
        color_continuous_scale="sunset",
        labels={"count": "Requests (count)", "complaint_type": "Complaint Type"},
        title=f"Top {n} Complaint Types",
    )
    fig.update_layout(
        yaxis=dict(autorange="reversed"),
        font=dict(size=14),
        height=520,
        coloraxis_showscale=False,
        margin=dict(t=60, r=10, l=10, b=10),
    )
    return fig, counts


def fig_status_donut(df: pd.DataFrame) -> go.Figure:
    if df.empty or not safe_col(df, "status"):
        return go.Figure()
    s = df["status"].fillna("Unspecified").value_counts().reset_index()
    s.columns = ["status", "count"]
    fig = px.pie(
        s, values="count", names="status",
        hole=0.6, color="status",
        color_discrete_sequence=px.colors.qualitative.Set3,
        title="Status Breakdown"
    )
    fig.update_traces(textposition='inside', textinfo='percent+label')
    fig.update_layout(font=dict(size=14), height=520, margin=dict(t=60, r=10, l=10, b=10))
    return fig


def fig_resolution_box(df: pd.DataFrame, top_types: List[str]) -> go.Figure:
    if df.empty or not safe_col(df, "hours_to_close"):
        return go.Figure()
    sub = df.copy()
    # focus on most common complaint types only (to keep the plot readable)
    if top_types:
        sub = sub[sub["complaint_type"].isin(top_types)]
    sub = sub.dropna(subset=["hours_to_close"])
    if sub.empty:
        return go.Figure()
    # clip extreme values for readability
    q99 = sub["hours_to_close"].quantile(0.99)
    sub = sub[sub["hours_to_close"] <= q99]
    fig = px.box(
        sub,
        x="complaint_type",
        y="hours_to_close",
        points=False,
        color="complaint_type",
        labels={"hours_to_close": "Hours to Close", "complaint_type": "Complaint Type"},
        title="Resolution Time by Complaint Type (hours, clipped at 99th pct)",
        color_discrete_sequence=px.colors.qualitative.Bold,
    )
    fig.update_layout(
        showlegend=False,
        xaxis_tickangle=-45,
        font=dict(size=14),
        height=560,
        margin=dict(t=60, r=10, l=10, b=80),
    )
    return fig


def fig_day_hour_heatmap(df: pd.DataFrame) -> go.Figure:
    if df.empty or not safe_col(df, "day_of_week") or not safe_col(df, "hour"):
        return go.Figure()
    order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    piv = (
        df.groupby(["day_of_week", "hour"])
        .size()
        .reset_index(name="count")
        .pivot(index="day_of_week", columns="hour", values="count")
        .reindex(order)
        .fillna(0)
    )
    # Use imshow for better hover + readable colorbar title
    fig = px.imshow(
        piv.values,
        labels={"x": "Hour of Day (24h)", "y": "Day of Week", "color": "Number of requests"},
        x=[f"{h:02d}" for h in piv.columns],
        y=piv.index.tolist(),
        color_continuous_scale="YlOrRd",
        title="When are requests made? (Day × Hour)",
    )
    fig.update_traces(
        hovertemplate="Day: %{y}<br>Hour: %{x}:00<br><b>Number of requests</b>: %{z}<extra></extra>"
    )
    fig.update_layout(font=dict(size=14), height=560, margin=dict(t=60, r=10, l=10, b=10))
    return fig


def fig_bubbles_hourly(df: pd.DataFrame, max_types: int = 10) -> go.Figure:
    """
    Animated bubbles by hour of day.
    - size: number of requests
    - color: Closed vs Open / In Progress
    - group: complaint type (top N overall to keep chart readable)
    """
    if df.empty or not safe_col(df, "hour") or not safe_col(df, "complaint_type"):
        return go.Figure()

    top_types = (
        df["complaint_type"].value_counts().head(max_types).index.tolist()
    )
    sub = df[df["complaint_type"].isin(top_types)].copy()
    sub["status_simple"] = simplify_status(sub.get("status", pd.Series(index=sub.index)))

    agg = (
        sub.groupby(["hour", "complaint_type", "status_simple"])
        .size()
        .reset_index(name="count")
    )
    # Use hour as categorical frame so it animates 0..23
    agg["hour"] = agg["hour"].astype(int)

    fig = px.scatter(
        agg,
        x="complaint_type",
        y="count",
        size="count",
        color="status_simple",
        animation_frame="hour",
        size_max=40,
        color_discrete_map={
            "Closed": "#2ca02c",
            "Open / In Progress": "#ff7f0e",
        },
        labels={"count": "Requests (count)", "complaint_type": "Complaint Type", "status_simple": "Status"},
        title="How requests change through the day (play ▶ to animate)",
    )
    fig.update_layout(
        font=dict(size=14),
        height=560,
        xaxis_tickangle=-30,
        margin=dict(t=60, r=10, l=10, b=40),
    )
    # nicer hover
    fig.update_traces(
        hovertemplate="Hour: %{frame}%{_frame}<br>%{x}<br>Status: %{marker.color}<br><b>Requests</b>: %{y:,}<extra></extra>"
    )
    return fig


def fig_monthly_trend(df: pd.DataFrame) -> go.Figure:
    if df.empty or not safe_col(df, "created_date"):
        return go.Figure()
    monthly = (
        df.set_index("created_date")
        .resample("M")
        .size()
        .reset_index(name="count")
    )
    monthly["rolling"] = monthly["count"].rolling(3, center=True).mean()
    fig = go.Figure()
    fig.add_traces([
        go.Scatter(
            x=monthly["created_date"],
            y=monthly["count"],
            mode="lines+markers",
            name="Monthly",
            line=dict(width=3, color="#1f77b4"),
        ),
        go.Scatter(
            x=monthly["created_date"],
            y=monthly["rolling"],
            mode="lines",
            name="3-month avg",
            line=dict(width=3, dash="dash", color="#d62728"),
        ),
    ])
    fig.update_layout(
        title="Monthly 311 Requests — last 12 months",
        xaxis_title="Month",
        yaxis_title="Requests (count)",
        font=dict(size=14),
        height=460,
        margin=dict(t=60, r=10, l=10, b=10),
    )
    return fig

# -----------------------------
# UI — Sidebar
# -----------------------------
st.sidebar.success(f"Loaded data from **{DATA_FILE}**")
with st.sidebar:
    day = st.selectbox("Day of Week", ["All", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"])
    hr = st.slider("Hour range (24h)", 0, 23, (0, 23))
    bor = st.multiselect("Borough(s)", [], placeholder="Loading…")
    top_n = st.slider("Top complaint types to show", 5, 30, 20)

# -----------------------------
# Load + announce
# -----------------------------
df = load_data(DATA_FILE)

# Populate borough choices after loading
if not bor:
    with st.sidebar:
        st.session_state.setdefault("boroughs_loaded", True)
        bor_default = ["All"]
        all_bor = sorted(df["borough"].dropna().unique().tolist()) if safe_col(df, "borough") else []
        bor_sel = st.multiselect("Borough(s)", options=all_bor, default=[], key="bor_select_repl")

st.markdown(f"## 📞 {TITLE}")
st.caption(SUBTITLE)

# -----------------------------
# Apply filters
# -----------------------------
df_f = df.copy()
if day != "All" and safe_col(df_f, "day_of_week"):
    df_f = df_f[df_f["day_of_week"] == day]
if safe_col(df_f, "hour"):
    df_f = df_f[(df_f["hour"] >= hr[0]) & (df_f["hour"] <= hr[1])]
if "bor_select_repl" in st.session_state and st.session_state["bor_select_repl"]:
    df_f = df_f[df_f["borough"].isin(st.session_state["bor_select_repl"])]

# -----------------------------
# KPIs + “At a glance”
# -----------------------------
colA, colB, colC, colD = st.columns(4)
with colA:
    st.metric("Rows (after filters)", fmt_int(len(df_f)))
closed_pct = df_f["status"].str.lower().str.contains("closed").mean()*100 if safe_col(df_f, "status") and len(df_f)>0 else 0
with colB:
    st.metric("% Closed", f"{closed_pct:.1f}%")
median_hours = df_f["hours_to_close"].median() if safe_col(df_f, "hours_to_close") and len(df_f)>0 else np.nan
with colC:
    st.metric("Median Hours to Close", f"{median_hours:.2f}" if pd.notnull(median_hours) else "—")
top_type = (
    df_f["complaint_type"].value_counts().idxmax()
    if safe_col(df_f, "complaint_type") and len(df_f)>0 else "—"
)
with colD:
    st.metric("Top Complaint Type", top_type)

# “At a glance” narrative
if len(df_f) > 0:
    # borough share
    bor_share = (
        df_f["borough"].value_counts(normalize=True).mul(100).round(1)
        if safe_col(df_f, "borough") else pd.Series(dtype=float)
    )
    slow_med = (
        df_f.groupby("complaint_type")["hours_to_close"].median().sort_values(ascending=False)
        if safe_col(df_f, "hours_to_close") and safe_col(df_f, "complaint_type") else pd.Series(dtype=float)
    )
    bits = []
    if safe_col(df_f, "complaint_type"):
        t = df_f["complaint_type"].value_counts().head(3)
        if not t.empty:
            bits.append("Most frequent issues right now are " + ", ".join([f"**{i}** ({fmt_int(v)})" for i, v in t.items()]))
    if not slow_med.empty:
        bits.append(
            f"Slowest to close (median hours) include **{slow_med.index[0]}** ({slow_med.iloc[0]:,.1f}h)"
        )
    if not bor_share.empty and len(bor_share) >= 3:
        top3 = bor_share.head(3)
        parts = [f"**{i}** {v:.1f}%" for i, v in top3.items()]
        bits.append("Requests are concentrated in " + ", ".join(parts))
    if bits:
        st.markdown("**At a glance:** " + " — ".join(bits) + ".")

st.markdown("---")

# -----------------------------
# Section 1 — Top complaint types + Status donut
# -----------------------------
st.subheader("Top Complaint Types")
st.caption("What issues are most frequently reported under the current filters?")

fig_bar, counts_df = fig_top_types(df_f, top_n)
st.plotly_chart(fig_bar, use_container_width=True)

# Narrative for bar (robust to empties)
if counts_df is not None and not counts_df.empty:
    lead = counts_df.iloc[0]
    lead_type = lead.get("complaint_type", "(Unknown)")
    lead_count = lead.get("count", 0)
    st.info(
        f"**Narrative:** **{lead_type}** leads with **{fmt_int(lead_count)}** requests "
        f"under the current filters."
    )
else:
    st.info("**Narrative:** No complaint types available for the current filters.")

# Status donut to the right
st.subheader("Status Breakdown")
st.caption("How many are closed vs in progress / open?")
st.plotly_chart(fig_status_donut(df_f), use_container_width=True)

st.markdown("---")

# -----------------------------
# Section 2 — Resolution time box + Day × Hour heatmap
# -----------------------------
left, right = st.columns(2)
with left:
    st.subheader("Resolution Time by Complaint Type (hours)")
    most_common_types = (
        df_f["complaint_type"].value_counts().head(15).index.tolist()
        if safe_col(df_f, "complaint_type") else []
    )
    st.plotly_chart(fig_resolution_box(df_f, most_common_types), use_container_width=True)
    if safe_col(df_f, "hours_to_close"):
        med_all = df_f["hours_to_close"].median()
        st.caption(f"**Narrative:** Typical (median) resolution time across filters is **{med_all:,.2f} hours**.")

with right:
    st.subheader("When are requests made? — Day × Hour")
    st.plotly_chart(fig_day_hour_heatmap(df_f), use_container_width=True)
    st.caption("Hover a cell to see the **Number of requests** at that day and hour.")

st.markdown("---")

# -----------------------------
# Section 3 — Animated bubbles (hourly dynamics)
# -----------------------------
st.subheader("How requests evolve during the day (playable)")
st.caption("Press ▶ to watch requests change by hour. Bubble size = requests; color = Closed vs Open / In Progress.")
st.plotly_chart(fig_bubbles_hourly(df_f, max_types=12), use_container_width=True)

st.markdown("---")

# -----------------------------
# Section 4 — Monthly trend
# -----------------------------
st.subheader("Monthly trend (last 12 months)")
st.caption("Overall request volume per month with a 3-month smoothing line for clarity.")
st.plotly_chart(fig_monthly_trend(df_f), use_container_width=True)

# -----------------------------
# Footer tip
# -----------------------------
st.caption(
    "Tip: Use the filters on the left to focus by day, hour window, and borough(s). "
    "All charts update instantly on your compressed local dataset."
)


