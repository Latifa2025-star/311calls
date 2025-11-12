# 311.py  — NYC 311 Service Requests Explorer (polished + narratives + animation)
# --------------------------------------------------------------------------------
# Requirements (requirements.txt):
# streamlit>=1.38
# pandas>=2.2
# numpy>=1.26
# plotly>=5.24

import os
import numpy as np
import pandas as pd
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go

# ----------------------------- CONFIG -----------------------------------------
st.set_page_config(
    page_title="NYC 311 Service Requests Explorer",
    page_icon="📞",
    layout="wide",
    initial_sidebar_state="expanded",
)

DATA_FILE = "nyc311_12months.csv.gz"   # gzip csv shipped with the repo

THEME_COLORS = {
    "primary": "#4C78A8",
    "accent":  "#F58518",
    "ok":      "#33A02C",
    "warn":    "#FB9A99",
    "muted":   "#9E9E9E",
}

st.markdown(
    """
    <style>
    /* Bigger base font for readability */
    html, body, [class*="css"]  { font-size: 16px; }
    .small-muted { color:#6b7280; font-size:0.95rem; }
    .caption-strong { color:#374151; font-weight:600; }
    .kpi { font-size: 2.0rem; font-weight:700; }
    .subkpi { color:#6b7280; font-size: 0.9rem;}
    </style>
    """,
    unsafe_allow_html=True
)

# ----------------------------- LOAD DATA --------------------------------------
@st.cache_data(show_spinner=True)
def load_data() -> pd.DataFrame:
    if not os.path.exists(DATA_FILE):
        st.stop()
    df = pd.read_csv(DATA_FILE, compression="gzip")
    # Coerce datetimes & derive fields
    for c in ["created_date", "closed_date", "resolution_action_updated_date"]:
        if c in df.columns:
            df[c] = pd.to_datetime(df[c], errors="coerce")

    # numeric coercions
    for c in ["latitude", "longitude", "hours_to_close"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")

    # helpers
    df["day_of_week"] = df["created_date"].dt.day_name()
    df["hour"] = df["created_date"].dt.hour
    df["month"] = df["created_date"].dt.month
    df["year"] = df["created_date"].dt.year
    df["is_closed"] = df.get("status", "").astype(str).str.lower().eq("closed")
    df["borough"] = df.get("borough", "Unspecified").fillna("Unspecified")
    df["complaint_type"] = df.get("complaint_type", "(Unknown)").fillna("(Unknown)")
    return df

df_full = load_data()

# ----------------------------- SIDEBAR ----------------------------------------
st.sidebar.header("Filters")

st.sidebar.success(f"Loaded data from `{DATA_FILE}`")

days = ["All"] + list(df_full["day_of_week"].dropna().unique())
day_filter = st.sidebar.selectbox("Day of Week", days, index=0)

hour_range = st.sidebar.slider("Hour range (24h)", 0, 23, (0, 23))
boroughs_all = sorted(df_full["borough"].dropna().unique().tolist())
boroughs = st.sidebar.multiselect("Borough(s)", options=boroughs_all, default=boroughs_all)

top_n = st.sidebar.slider("Top complaint types to show", 5, 30, 20)

# ----------------------------- APPLY FILTERS ----------------------------------
df = df_full.copy()
if day_filter != "All":
    df = df[df["day_of_week"] == day_filter]
df = df[(df["hour"] >= hour_range[0]) & (df["hour"] <= hour_range[1])]
if boroughs:
    df = df[df["borough"].isin(boroughs)]

rows = len(df)
pct_closed = (df["is_closed"].mean() * 100) if rows else 0
med_hours = df["hours_to_close"].median() if "hours_to_close" in df and rows else np.nan
top_type = (
    df["complaint_type"].mode().iloc[0]
    if rows and "complaint_type" in df and not df["complaint_type"].empty
    else "—"
)

# ----------------------------- HEADER & KPIs ----------------------------------
st.markdown(
    f"""
    <h1 style='display:flex;align-items:center;gap:.5rem'>
      <span style="font-size:2.2rem;">📞</span>
      NYC 311 Service Requests Explorer
    </h1>
    <div class="small-muted">Explore complaint types, resolution times, and closure rates by day and hour — powered by a compressed local dataset (<code>.csv.gz</code>).</div>
    """,
    unsafe_allow_html=True,
)

k1, k2, k3, k4 = st.columns(4)
k1.markdown(f"<div class='subkpi'>Rows (after filters)</div><div class='kpi'>{rows:,.0f}</div>", unsafe_allow_html=True)
k2.markdown(f"<div class='subkpi'>% Closed</div><div class='kpi'>{pct_closed:,.1f}%</div>", unsafe_allow_html=True)
k3.markdown(f"<div class='subkpi'>Median Hours to Close</div><div class='kpi'>{(med_hours if pd.notnull(med_hours) else 0):,.2f}</div>", unsafe_allow_html=True)
k4.markdown(f"<div class='subkpi'>Top Complaint Type</div><div class='kpi'>{top_type}</div>", unsafe_allow_html=True)

# ----------------------------- NARRATIVE (GLOBAL) -----------------------------
def global_findings_text(d: pd.DataFrame) -> str:
    if d.empty:
        return "_No rows for current filters. Try expanding your hour window or boroughs._"
    # top types & borough
    counts = d["complaint_type"].value_counts().head(3)
    top_str = ", ".join([f"**{i}** ({c:,})" for i, c in counts.items()])
    bor = d["borough"].value_counts(normalize=True).mul(100).round(1)
    bor_str = ", ".join([f"**{b}** {p:.1f}%" for b, p in bor.head(3).items()])
    slow = (
        d.dropna(subset=["hours_to_close"])
        .groupby("complaint_type")["hours_to_close"]
        .median()
        .sort_values(ascending=False)
        .head(3)
    )
    slow_str = ", ".join([f"**{i}** ({v:,.1f}h)" for i, v in slow.items()]) if not slow.empty else "—"

    return (
        f"**At a glance:** Most frequent issues right now are {top_str}. "
        f"Requests are concentrated in {bor_str}. "
        f"Slowest to close (median hours) include {slow_str}. "
        f"The overall closure rate is **{d['is_closed'].mean()*100:,.1f}%** with a median resolution time of **{d['hours_to_close'].median():,.2f} hours**."
    )

st.markdown(global_findings_text(df))

st.markdown("---")

# ============================ CHART 1: Top Complaint Types =====================
st.subheader("Top Complaint Types")
st.caption("**What issues are most frequently reported under the current filters?**")

if df.empty:
    st.info("No data for current filters.")
else:
    counts = (
        df["complaint_type"]
        .value_counts()
        .reset_index()
        .rename(columns={"index": "complaint_type", "complaint_type": "count"})
        .head(top_n)
    )

    # narrative for this chart
    if not counts.empty:
        lead = counts.iloc[0]
        st.markdown(
            f"*Narrative:* **{lead['complaint_type']}** leads with **{lead['count']:,}** requests. "
            f"The top {min(top_n, len(counts))} categories together make up **{counts['count'].sum():,}** requests."
        )

    fig_bar = px.bar(
        counts.sort_values("count"),
        x="count",
        y="complaint_type",
        orientation="h",
        color="count",
        color_continuous_scale="Sunset",
        labels={"count": "Requests (count)", "complaint_type": "Complaint Type"},
        title=f"Top {min(top_n, len(counts))} Complaint Types",
    )
    fig_bar.update_layout(height=500, yaxis=dict(autorange="reversed"), coloraxis_showscale=False)
    st.plotly_chart(fig_bar, use_container_width=True)

# ============================ CHART 2: Status Donut ============================
st.subheader("Status Breakdown")
st.caption("**How many requests are closed vs in progress or other states?**")

if df.empty:
    st.info("No data for current filters.")
else:
    status_counts = df.get("status", pd.Series(dtype=str)).fillna("Unspecified").value_counts().reset_index()
    status_counts.columns = ["status", "count"]
    fig_pie = px.pie(
        status_counts, values="count", names="status",
        hole=0.55, color_discrete_sequence=px.colors.qualitative.Set2,
        title="Share of Requests by Current Status"
    )
    fig_pie.update_traces(textposition="inside", textinfo="percent+label")
    fig_pie.update_layout(height=520)
    st.plotly_chart(fig_pie, use_container_width=True)

# ============================ CHART 3: Boxplot (Resolution) ====================
st.subheader("Resolution Time by Complaint Type (hours)")
st.caption(
    "Each box shows the distribution of **hours to close** for a complaint type (box = interquartile range, "
    "line = median, whiskers = typical range; dots are outliers)."
)

if df.empty or "hours_to_close" not in df.columns:
    st.info("No resolution-time data for current filters.")
else:
    dsub = df.dropna(subset=["hours_to_close"])
    # narrative
    med_by_type = dsub.groupby("complaint_type")["hours_to_close"].median().sort_values(ascending=False)
    if not med_by_type.empty:
        worst = med_by_type.head(3)
        best = med_by_type.tail(3)
        st.markdown(
            f"*Narrative:* Longest median resolution times: "
            + ", ".join([f"**{i}** ({v:,.1f}h)" for i, v in worst.items()])
            + ". "
            + "Fastest: "
            + ", ".join([f"**{i}** ({v:,.1f}h)" for i, v in best.items()])
            + "."
        )

    fig_box = px.box(
        dsub,
        x="complaint_type",
        y="hours_to_close",
        points="suspectedoutliers",
        color="complaint_type",
        labels={"hours_to_close": "Hours to Close", "complaint_type": "Complaint Type"},
        title="Distribution of Time to Close by Complaint Type",
    )
    fig_box.update_layout(height=600, showlegend=False, xaxis_tickangle=-45, margin=dict(t=60, b=80))
    st.plotly_chart(fig_box, use_container_width=True)

# ============================ CHART 4: Heatmap (Day x Hour) ====================
st.subheader("When are requests made? (Day × Hour)")
st.caption(
    "Heatmap of **Requests (count)** by day of week and hour. Hover to see exact counts. "
    "Use the filters to focus the view."
)

if df.empty:
    st.info("No data for current filters.")
else:
    pivot = (
        df.groupby(["day_of_week", "hour"])
        .size()
        .reset_index(name="count")
        .pivot(index="day_of_week", columns="hour", values="count")
        .reindex(["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"])
        .fillna(0)
    )
    fig_hm = px.imshow(
        pivot.values,
        labels={"x": "Hour of Day (24h)", "y": "Day of Week", "color": "Requests (count)"},
        x=[f"{h:02d}:00" for h in pivot.columns],
        y=pivot.index,
        color_continuous_scale="YlOrRd",
        aspect="auto",
        title="Intensity of Requests by Day and Hour"
    )
    fig_hm.update_layout(height=520, margin=dict(t=60, b=40))
    st.plotly_chart(fig_hm, use_container_width=True)

# ===================== CHART 5: Animated Bubble Timeline ======================
st.subheader("How complaints evolve through the day (animated)")
st.caption(
    "Press ▶ to animate. Bubble size = **Requests (count)**, X = **Median hours to close**, "
    "Y = **% Closed**. Colors distinguish complaint types. "
    "_Satisfaction isn’t available in this dataset, so closure rate and time to close serve as proxies._"
)

if df.empty or "hours_to_close" not in df.columns:
    st.info("No data for animation under current filters.")
else:
    # compute per hour & type: count, closure rate, median hours
    ag = (
        df.groupby(["hour", "complaint_type"])
        .agg(
            count=("complaint_type", "size"),
            pct_closed=("is_closed", "mean"),
            med_hours=("hours_to_close", "median"),
        )
        .reset_index()
        .dropna(subset=["med_hours", "pct_closed"])
    )

    # show only top N types overall to keep animation readable
    top_types_overall = (
        df["complaint_type"].value_counts().head(10).index.tolist()
    )
    ag = ag[ag["complaint_type"].isin(top_types_overall)]

    ag["pct_closed"] = (ag["pct_closed"] * 100).round(2)

    fig_anim = px.scatter(
        ag,
        x="med_hours",
        y="pct_closed",
        size="count",
        color="complaint_type",
        animation_frame="hour",
        range_x=[0, float(np.nanpercentile(ag["med_hours"], 95) * 1.1 if not ag["med_hours"].empty else 10)],
        range_y=[0, 100],
        labels={
            "med_hours": "Median Hours to Close",
            "pct_closed": "% Closed",
            "count": "Requests (count)",
            "complaint_type": "Complaint Type",
            "hour": "Hour of Day",
        },
        title="Bubble timeline: complaints across the day",
        height=620,
    )
    fig_anim.update_layout(legend_title_text="Complaint Type", margin=dict(t=60, b=20))
    st.plotly_chart(fig_anim, use_container_width=True)

# ============================ FOOTER / TIPS ===================================
st.markdown("---")
st.markdown(
    """
    **Tips**  
    • Use the sidebar to focus on any day, hour window, or set of boroughs.  
    • Narratives above each chart are generated from the current slice of the data.  
    • Want to demo with a smaller dataset? Replace `nyc311_12months.csv.gz` with a lighter sample and keep the same code.  
    """,
)
