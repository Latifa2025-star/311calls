# 311.py
# NYC 311 Service Requests Explorer — Streamlit app
# - Loads a local compressed CSV (nyc311_12months.csv.gz) or CSV fallback
# - Rich filters + KPIs
# - Top types bar + status donut + resolution-time boxplot + day×hour heatmap (with clear "Number of requests" colorbar)
# - Animation 1: bar race of top complaint types through the day (hour)
# - Animation 2: bubble animation showing count vs median hours to close, by complaint type, over the day
# - Fancy Map: clustered points + heat layer (Leaflet/Folium) with type & status in popup; colored by status

from __future__ import annotations
import os
import numpy as np
import pandas as pd
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go

from streamlit_folium import st_folium
import folium
from folium.plugins import HeatMap, MarkerCluster

# -----------------------------
# App config & theme
# -----------------------------
st.set_page_config(
    page_title="NYC 311 Service Requests Explorer",
    page_icon="📞",
    layout="wide",
    initial_sidebar_state="expanded",
)

PRIMARY = "#4338CA"   # Indigo-ish
ACCENT  = "#F97316"   # Orange
GOOD    = "#16A34A"   # Green
OKAY    = "#0891B2"   # Teal
BAD     = "#DC2626"   # Red

# -----------------------------
# Data loading
# -----------------------------
@st.cache_data(show_spinner=True)
def load_data():
    # Try .csv.gz then .csv then sample
    paths = [
        ("nyc311_12months.csv.gz", {"compression":"gzip"}),
        ("nyc311_12months.csv", {}),
        ("sample.csv", {})
    ]
    df = None
    picked = None
    for p, kw in paths:
        if os.path.exists(p):
            df = pd.read_csv(p, **kw)
            picked = p
            break
    if df is None:
        raise FileNotFoundError("Could not find nyc311_12months.csv.gz/nyc311_12months.csv/sample.csv in repo.")

    # Normalize important columns
    for c in ["created_date","closed_date","resolution_action_updated_date"]:
        if c in df.columns:
            df[c] = pd.to_datetime(df[c], errors="coerce")

    # Missing standard columns? create them
    if "status" not in df.columns:
        df["status"] = "Unspecified"
    if "complaint_type" not in df.columns:
        df["complaint_type"] = "(Unknown)"
    if "agency_name" not in df.columns:
        df["agency_name"] = "(Unknown)"
    if "borough" not in df.columns:
        df["borough"] = "Unspecified"

    # hours_to_close
    if "hours_to_close" not in df.columns:
        if {"created_date","closed_date"}.issubset(df.columns):
            df["hours_to_close"] = (
                (df["closed_date"] - df["created_date"])
                .dt.total_seconds() / 3600.0
            )
        else:
            df["hours_to_close"] = np.nan

    # Add helpers
    df["day_of_week"] = df["created_date"].dt.day_name()
    df["hour"]        = df["created_date"].dt.hour
    # Friendly status bucket
    df["status_bucket"] = (
        df["status"].str.lower()
        .map(lambda s: "Closed" if "closed" in s else ("In Progress" if "progress" in s else ("Open" if "open" in s else s.title())))
        .fillna("Unspecified")
    )
    return df, picked

df, data_file_name = load_data()

# -----------------------------
# Sidebar filters
# -----------------------------
st.sidebar.header("Filters", divider="grey")
st.sidebar.success(f"Loaded data from **{data_file_name}**")

days = ["All"] + list(pd.Categorical(df["day_of_week"], 
                 categories=["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"]).dropna().unique())
day_choice = st.sidebar.selectbox("Day of Week", days, index=0)

hour_min, hour_max = st.sidebar.slider("Hour range (24h)", 0, 23, (0, 23))
boroughs_all = sorted(df["borough"].dropna().unique().tolist())
borough_choice = st.sidebar.multiselect("Borough(s)", boroughs_all, default=[])
top_n = st.sidebar.slider("Top complaint types to show", 5, 30, 20)

# Apply filters
filtered = df.copy()
if day_choice != "All":
    filtered = filtered[filtered["day_of_week"] == day_choice]
filtered = filtered[(filtered["hour"] >= hour_min) & (filtered["hour"] <= hour_max)]
if borough_choice:
    filtered = filtered[filtered["borough"].isin(borough_choice)]

# -----------------------------
# Header & KPIs
# -----------------------------
st.markdown(
    f"""
    <h1 style="display:flex;align-items:center;gap:10px;">
      <span>📞</span>
      NYC 311 Service Requests Explorer
    </h1>
    <p style="color:#6b7280;">
      Explore complaint types, resolution times, and closure rates by day and hour — powered by a compressed local dataset (<code>.csv.gz</code>).
    </p>
    """,
    unsafe_allow_html=True
)

k1, k2, k3, k4 = st.columns(4)
k1.metric("Rows (after filters)", f"{len(filtered):,}")
pct_closed = (filtered["status_bucket"].eq("Closed").mean() * 100) if len(filtered) else 0.0
k2.metric("% Closed", f"{pct_closed:.1f}%")
med_hrs = filtered["hours_to_close"].median() if filtered["hours_to_close"].notna().any() else np.nan
k3.metric("Median Hours to Close", "—" if pd.isna(med_hrs) else f"{med_hrs:.2f}")
top_type = "—"
if not filtered.empty:
    top_counts_local = filtered["complaint_type"].value_counts()
    if not top_counts_local.empty:
        top_type = top_counts_local.index[0]
k4.metric("Top Complaint Type", top_type)

st.divider()

# ======================================================
# SECTION 1 — Top types bar + status donut + narrative
# ======================================================
st.subheader("Top Complaint Types")
st.caption("What issues are most frequently reported under the current filters?")

counts = (
    filtered["complaint_type"]
    .value_counts()
    .head(top_n)
    .rename_axis("complaint_type")
    .reset_index(name="count")
)

# Safe narrative
if counts.empty:
    st.info("No records for the current filters.")
else:
    lead_row = counts.iloc[0]
    lead_type = str(lead_row["complaint_type"])
    lead_ct   = int(lead_row["count"])
    st.markdown(
        f"**Narrative:** **{lead_type}** leads with **{lead_ct:,}** requests. "
        f"Use the filters (day, hour, borough) to see how the pattern changes."
    )

    # Bar
    fig_bar = px.bar(
        counts,
        x="count",
        y="complaint_type",
        orientation="h",
        color="count",
        color_continuous_scale=px.colors.sequential.Sunset,
        title=f"Top {min(top_n, len(counts))} Complaint Types",
    )
    fig_bar.update_layout(
        height=520, yaxis_title=None, xaxis_title="Requests (count)",
        coloraxis_showscale=False, margin=dict(l=10,r=10,t=60,b=10),
        title_x=0.02, title_font_size=20
    )
    fig_bar.update_yaxes(autorange="reversed")
    c1, c2 = st.columns([2,1])
    c1.plotly_chart(fig_bar, use_container_width=True)

    # Status donut
    status_counts = (
        filtered["status_bucket"].value_counts()
        .rename_axis("status")
        .reset_index(name="count")
    )
    fig_donut = px.pie(
        status_counts, names="status", values="count",
        hole=0.55, color="status",
        color_discrete_map={
            "Closed":GOOD, "In Progress":ACCENT, "Open":PRIMARY, "Unspecified":"#9CA3AF"
        },
        title="Status Breakdown"
    )
    fig_donut.update_traces(textinfo="percent+label")
    fig_donut.update_layout(height=520, title_x=0.05, margin=dict(l=10,r=10,t=60,b=10))
    c2.plotly_chart(fig_donut, use_container_width=True)

st.divider()

# ======================================================
# SECTION 2 — Resolution time by complaint type (box)
# ======================================================
st.subheader("Resolution Time by Complaint Type (hours)")
st.caption("How long do different complaint types take to close? Outliers clipped at 99th percentile for readability.")

if filtered["hours_to_close"].notna().any():
    temp = filtered[filtered["hours_to_close"].notna()].copy()
    q99 = temp["hours_to_close"].quantile(0.99)
    temp = temp[temp["hours_to_close"] <= q99]

    # Keep only top types for clarity
    top_set = set(counts["complaint_type"]) if not counts.empty else set()
    if top_set:
        temp = temp[temp["complaint_type"].isin(top_set)]

    fig_box = px.box(
        temp, x="complaint_type", y="hours_to_close", points=False,
        color="complaint_type", color_discrete_sequence=px.colors.qualitative.Set3
    )
    fig_box.update_layout(
        height=520, xaxis_title="Complaint Type", yaxis_title="Hours to Close",
        showlegend=False, margin=dict(l=10,r=10,t=10,b=120)
    )
    fig_box.update_xaxes(tickangle=-45)
    st.plotly_chart(fig_box, use_container_width=True)
else:
    st.info("No resolution time data available for current filters.")

st.divider()

# ======================================================
# SECTION 3 — Day × Hour Heatmap (with clear colorbar)
# ======================================================
st.subheader("When are requests made? (Day × Hour)")
st.caption("Hover shows **Number of requests**. X-axis uses 24h clock, Y-axis is day of week.")

# Build pivot
heat = (
    filtered.assign(day=filtered["day_of_week"], hr=filtered["hour"])
    .groupby(["day","hr"], dropna=False).size().reset_index(name="count")
)

# order days
order_days = ["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"]
heat["day"] = pd.Categorical(heat["day"], categories=order_days, ordered=True)
heat = heat.sort_values(["day","hr"])

if not heat.empty:
    fig_heat = px.imshow(
        heat.pivot(index="day", columns="hr", values="count").fillna(0).values,
        x=[f"{h:02d}:00" for h in range(24)],
        y=order_days,
        color_continuous_scale="YlOrRd",
        origin="upper",
        aspect="auto",
        labels=dict(color="Number of requests")
    )
    fig_heat.update_layout(
        height=520, margin=dict(l=10,r=10,t=10,b=10),
        coloraxis_colorbar_title="Number of requests",
    )
    # Improve hover (build our own grid)
    z = heat.pivot(index="day", columns="hr", values="count").reindex(order_days).fillna(0).values
    hover = []
    for i, d in enumerate(order_days):
        row = []
        for h in range(24):
            row.append(f"Day: {d}<br>Hour: {h:02d}:00<br><b>Number of requests:</b> {int(z[i,h])}")
        hover.append(row)
    fig_heat.data[0].hovertemplate = hover
    st.plotly_chart(fig_heat, use_container_width=True)
else:
    st.info("No data to render heatmap for current filters.")

st.divider()

# ======================================================
# SECTION 4 — Animation 1: Bar race across the day
# ======================================================
st.subheader("Animation — How top complaint types evolve through the day")
st.caption("Press ▶️ to play. Shows **top complaint types by hour** (current filters).")

if not filtered.empty:
    race_df = (
        filtered.groupby(["hour","complaint_type"], dropna=False)
        .size().reset_index(name="count")
    )
    # keep only types that appear in top_n across all hours (optional)
    # to keep it legible, we just limit to the top_n most frequent overall
    keep = (
        filtered["complaint_type"].value_counts().head(min(12, top_n)).index
    )
    race_df = race_df[race_df["complaint_type"].isin(keep)]

    fig_race = px.bar(
        race_df, x="count", y="complaint_type",
        color="complaint_type", orientation="h",
        animation_frame="hour", range_x=[0, max(1, race_df["count"].max() * 1.1)],
        color_discrete_sequence=px.colors.qualitative.Bold,
        title="Top complaint types by hour (24h)"
    )
    fig_race.update_layout(
        height=560, yaxis={"categoryorder":"total ascending"},
        margin=dict(l=10,r=10,t=60,b=10), title_x=0.02
    )
    st.plotly_chart(fig_race, use_container_width=True)
else:
    st.info("No data available to animate.")

st.divider()

# ======================================================
# SECTION 5 — Animation 2: Bubble animation
# count vs median hours, by complaint type, across the day
# ======================================================
st.subheader("Animation — Workload vs speed (bubble)")
st.caption("Press ▶️ to play. Each bubble is a complaint type. X = number of requests, Y = median hours to close, bubble size = request volume; frame = hour.")

if filtered["hours_to_close"].notna().any():
    agg = (
        filtered.groupby(["hour","complaint_type"], dropna=False)
        .agg(count=("complaint_type","size"),
             med_hours=("hours_to_close","median"))
        .reset_index()
    )
    # keep most frequent types overall
    keep2 = filtered["complaint_type"].value_counts().head(min(12, top_n)).index
    agg = agg[agg["complaint_type"].isin(keep2)]

    fig_bubble = px.scatter(
        agg, x="count", y="med_hours",
        size="count", color="complaint_type",
        animation_frame="hour", size_max=50,
        color_discrete_sequence=px.colors.qualitative.Set2,
        labels={"count":"Requests (count)","med_hours":"Median hours to close"},
        title="Volume vs. Resolution Speed by Hour"
    )
    fig_bubble.update_layout(height=560, margin=dict(l=10,r=10,t=60,b=10), title_x=0.02)
    st.plotly_chart(fig_bubble, use_container_width=True)
else:
    st.info("Not enough resolution-time data to build the bubble animation.")

st.divider()

# ======================================================
# SECTION 6 — Fancy Map (Folium) with clustering + heat
# ======================================================
st.subheader("Geographic View — Where are the complaints?")
st.caption("Interactive map with **clustered points** (colored by status) and a **heat layer**. Hover popups show **type, status, borough, time**. For performance we sample up to 25k points.")

has_geo = {"latitude","longitude"}.issubset(filtered.columns)
if has_geo and filtered[["latitude","longitude"]].dropna().shape[0] > 0:
    # Sample to keep the map snappy
    map_df = filtered.dropna(subset=["latitude","longitude"]).copy()
    if len(map_df) > 25000:
        map_df = map_df.sample(25000, random_state=42)

    # Center on NYC approx
    center = [40.7128, -74.0060]
    m = folium.Map(location=center, zoom_start=10, tiles="cartodbpositron")

    # Heat layer (recent density)
    heat_data = map_df[["latitude","longitude"]].values.tolist()
    if len(heat_data) > 0:
        HeatMap(heat_data, radius=10, blur=15, min_opacity=0.3).add_to(m)

    # Clustered markers, colored by status
    cluster = MarkerCluster().add_to(m)

    def status_color(s: str) -> str:
        s = (s or "").lower()
        if "closed" in s:
            return "green"
        if "progress" in s:
            return "orange"
        if "open" in s:
            return "blue"
        return "gray"

    for _, row in map_df.iterrows():
        lat = row["latitude"]; lon = row["longitude"]
        if pd.isna(lat) or pd.isna(lon):
            continue
        ctype = str(row.get("complaint_type","(Unknown)"))
        stat  = str(row.get("status","Unspecified"))
        boro  = str(row.get("borough","Unspecified"))
        ts    = row.get("created_date")
        ts_txt = ts.strftime("%Y-%m-%d %H:%M") if pd.notna(ts) else ""
        popup = folium.Popup(
            folium.IFrame(
                html=f"<b>{ctype}</b><br>Status: {stat}<br>Borough: {boro}<br>Created: {ts_txt}",
                width=260, height=110
            ),
            max_width=260
        )
        folium.CircleMarker(
            location=[lat, lon],
            radius=4,
            color=status_color(stat),
            fill=True, fill_opacity=0.7,
            popup=popup
        ).add_to(cluster)

    st_folium(m, height=580, width=None)
else:
    st.info("No latitude/longitude available for the current filters to render the map.")

# ======================================================
# FOOTER TIP
# ======================================================
st.caption("Tip: Use filters (left) to focus the story by day, hour window, and borough(s). Charts and animations update instantly on your compressed local dataset.")



