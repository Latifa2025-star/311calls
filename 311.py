# 311calls.py
import pandas as pd
import numpy as np
import plotly.express as px
import streamlit as st

st.set_page_config(page_title="NYC 311 – Where are the complaints?", page_icon="📞", layout="wide")

@st.cache_data(show_spinner=True)
def load_311(limit=50000, year_from=2023):
    # Pull a light subset for speed
    url = (
        "https://data.cityofnewyork.us/resource/erm2-nwe9.csv"
        f"?$select=created_date,closed_date,agency,complaint_type,descriptor,"
        f"borough,latitude,longitude"
        f"&$where=created_date >= '{year_from}-01-01T00:00:00.000' AND latitude IS NOT NULL"
        f"&$limit={limit}"
    )
    df = pd.read_csv(url, low_memory=False)

    # Basic cleaning
    df["created_date"] = pd.to_datetime(df["created_date"], errors="coerce")
    df["closed_date"] = pd.to_datetime(df["closed_date"], errors="coerce")

    # Coerce lat/lon to numeric and drop invalids
    for c in ("latitude", "longitude"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna(subset=["latitude", "longitude"])

    # NYC bounding box (screens out weird points)
    df = df.query("40.3 < latitude < 41.2 and -75 < longitude < -73.3")

    # Light derived features
    df["date"] = df["created_date"].dt.date
    df["month"] = df["created_date"].dt.to_period("M").dt.to_timestamp()

    return df

st.title("📞 Where are the complaints? (sampled for performance)")

# Sidebar controls
with st.sidebar:
    st.markdown("### Data options")
    year_from = st.number_input("Start year", min_value=2016, max_value=2025, value=2023, step=1)
    limit = st.slider("Rows to load", 10_000, 200_000, 50_000, 10_000)
    st.caption("Tip: increase for more detail, decrease for speed.")
    st.markdown("---")
    st.markdown("### Map options")
    color_by = st.selectbox("Color complaints by", ["complaint_type", "borough"])
    sample_for_map = st.slider("Map sample points", 2_000, 30_000, 10_000, 2_000)
    radius = st.slider("Heatmap radius", 4, 30, 10, 1)

df = load_311(limit=limit, year_from=year_from)

# ====== 1) COMPLAINTS OVER TIME ======
left, right = st.columns([2,1])
with left:
    by_month = df.groupby("month").size().reset_index(name="count")
    fig_time = px.line(
        by_month, x="month", y="count",
        markers=True, title="Requests per month",
        color_discrete_sequence=["#4C78A8"]
    )
    fig_time.update_layout(margin=dict(l=10, r=10, t=50, b=0))
    st.plotly_chart(fig_time, width="stretch", height=360)

# ====== 2) TOP COMPLAINT TYPES ======
with right:
    top_n = (
        df["complaint_type"].fillna("Unknown")
        .value_counts().head(15).sort_values(ascending=True)
        .rename_axis("complaint_type").reset_index(name="count")
    )
    fig_bar = px.bar(
        top_n, x="count", y="complaint_type", orientation="h",
        title="Top 15 complaint types",
        color="count", color_continuous_scale="Sunset"
    )
    fig_bar.update_layout(coloraxis_showscale=False, margin=dict(l=10, r=10, t=50, b=0))
    st.plotly_chart(fig_bar, width="stretch", height=360)

# ====== 3) SCATTER MAP (fixed) ======
st.markdown("### 📍 Points on map (sampled)")

# Sample for performance
geo = df[["latitude", "longitude", "complaint_type", "borough", "created_date"]].copy()
if len(geo) > sample_for_map:
    geo = geo.sample(sample_for_map, random_state=42)

fig_map = px.scatter_mapbox(
    geo,
    lat="latitude", lon="longitude",
    color=color_by,
    hover_data={"latitude": ":.5f", "longitude": ":.5f", "created_date": True},
    zoom=9, height=560,
    title=f"Geography of Requests (showing {len(geo):,} points)",
)
fig_map.update_layout(
    mapbox_style="open-street-map",
    margin=dict(l=0, r=0, t=60, b=0),
    legend_title=color_by.replace("_", " ").title(),
)
st.plotly_chart(fig_map, width="stretch")

# ====== 4) DENSITY HEATMAP (smooth hotspot view) ======
st.markdown("### 🔥 Density heatmap (hotspots)")
geo_for_heat = df[["latitude", "longitude", "complaint_type"]]
if len(geo_for_heat) > 20_000:
    geo_for_heat = geo_for_heat.sample(20_000, random_state=42)

fig_heat = px.density_mapbox(
    geo_for_heat,
    lat="latitude", lon="longitude",
    radius=radius,
    center=dict(lat=40.7128, lon=-74.0060),
    zoom=9, height=560,
    title="Complaint hotspots (density map)",
    color_continuous_scale="OrRd"
)
fig_heat.update_layout(mapbox_style="carto-positron", margin=dict(l=0, r=0, t=60, b=0))
st.plotly_chart(fig_heat, width="stretch")
