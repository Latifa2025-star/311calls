# streamlit_311.py
import datetime as dt
from urllib.parse import urlencode

import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st

st.set_page_config(
    page_title="NYC 311 — What do New Yorkers complain about?",
    page_icon="🗽",
    layout="wide",
)

# ---------- Helpers ----------
DATASET = "https://data.cityofnewyork.us/resource/erm2-nwe9.json"

COLUMNS = [
    "created_date",
    "closed_date",
    "complaint_type",
    "descriptor",
    "agency",
    "status",
    "borough",
    "incident_zip",
    "latitude",
    "longitude",
]

def socrata_url(start: dt.datetime, end: dt.datetime, limit: int, boroughs: list[str]):
    where = [
        f"created_date between '{start.isoformat()}T00:00:00' and '{end.isoformat()}T23:59:59'",
        "latitude is not null",
        "longitude is not null",
    ]
    if boroughs:
        b = ", ".join([f"'{x}'" for x in boroughs])
        where.append(f"borough in ({b})")

    params = {
        "$select": ",".join(COLUMNS),
        "$where": " AND ".join(where),
        "$order": "created_date DESC",
        "$limit": limit,
    }
    return DATASET + "?" + urlencode(params)

@st.cache_data(ttl=3600, show_spinner=False)
def fetch_311(start_date: dt.date, end_date: dt.date, limit: int, boroughs: list[str]):
    url = socrata_url(start_date, end_date, limit, boroughs)
    df = pd.read_json(url, dtype_backend="pyarrow")  # fast + light
    if df.empty:  # guard
        return df
    # tidy types
    df["created_date"] = pd.to_datetime(df["created_date"], errors="coerce")
    df["closed_date"] = pd.to_datetime(df["closed_date"], errors="coerce")
    df["response_hours"] = (
        (df["closed_date"] - df["created_date"]).dt.total_seconds() / 3600
    )
    df["day"] = df["created_date"].dt.date
    df["borough"] = df["borough"].fillna("Unknown")
    df["complaint_type"] = df["complaint_type"].fillna("Unknown")
    return df

# ---------- Sidebar controls ----------
st.sidebar.title("Filters")
today = dt.date.today()
default_start = today - dt.timedelta(days=60)

start_date = st.sidebar.date_input("Start date", default_start, max_value=today)
end_date = st.sidebar.date_input("End date", today, min_value=start_date, max_value=today)

limit = st.sidebar.slider("Rows to fetch (kept small for speed)", 5_000, 30_000, 15_000, step=5_000)

# borough options (static list avoids an extra call)
BORO_OPTS = ["BRONX", "BROOKLYN", "MANHATTAN", "QUEENS", "STATEN ISLAND"]
boroughs = st.sidebar.multiselect("Boroughs", BORO_OPTS, default=[])

st.sidebar.caption("Tip: keep the date window modest and rows ≤30k for snappy maps.")

# ---------- Load data ----------
with st.spinner("Loading 311 data from NYC Open Data…"):
    df = fetch_311(start_date, end_date, limit, boroughs)

st.title("🗽 NYC 311 Service Requests — What are people complaining about?")
st.caption(
    f"Window: **{start_date} → {end_date}** · Rows loaded: **{len(df):,}** "
    "· Source: NYC Open Data “311 Service Requests” (erm2-nwe9)"
)
st.markdown("---")

if df.empty:
    st.warning("No rows returned. Try widening the date window or removing filters.")
    st.stop()

# ---------- KPIs ----------
c1, c2, c3, c4 = st.columns(4)
with c1:
    st.metric("Total Requests", f"{len(df):,}")
with c2:
    pct_closed = (df["status"].astype(str).str.lower().eq("closed").mean() * 100)
    st.metric("Closed (%)", f"{pct_closed:.1f}%")
with c3:
    med_hours = np.nanmedian(df["response_hours"])
    med_txt = "—" if np.isnan(med_hours) else f"{med_hours:.1f} h"
    st.metric("Median Response Time", med_txt)
with c4:
    top_type = df["complaint_type"].value_counts().idxmax()
    st.metric("Top Complaint", top_type)

st.markdown("")

# ---------- Controls for visuals ----------
left, right = st.columns([1, 3])
with left:
    topN = st.slider("Show Top N complaint types", 5, 20, 10)
with right:
    sort_by_time = st.toggle("Order top chart by median response time (instead of volume)", value=False)

# ---------- Top complaints (bar) ----------
group = (
    df.groupby("complaint_type")
    .agg(count=("complaint_type", "size"), median_hours=("response_hours", "median"))
    .reset_index()
)

if sort_by_time:
    group = group.sort_values("median_hours", ascending=True).head(topN)
else:
    group = group.sort_values("count", ascending=False).head(topN)

bar_title = "Top Complaints — by Volume" if not sort_by_time else "Top Complaints — by Median Response Time"
fig_bar = px.bar(
    group,
    x="complaint_type",
    y="count" if not sort_by_time else "median_hours",
    color="median_hours",
    color_continuous_scale="Sunset",
    labels={"complaint_type": "Complaint Type", "count": "Requests", "median_hours": "Median Hours"},
    title=bar_title,
)
fig_bar.update_layout(xaxis_tickangle=-30, margin=dict(t=60, r=10, l=10, b=10))
st.plotly_chart(fig_bar, width="stretch")

# ---------- Trend over time ----------
trend = (
    df.groupby(["day", "complaint_type"])
    .size()
    .reset_index(name="count")
    .sort_values("day")
)

fig_line = px.line(
    trend,
    x="day",
    y="count",
    color="complaint_type",
    line_group="complaint_type",
    markers=True,
    color_discrete_sequence=px.colors.qualitative.Set2,
    labels={"day": "Date", "count": "Requests"},
    title="Requests per Day (colored by complaint type)",
)
fig_line.update_layout(legend_title_text="Complaint", margin=dict(t=60, r=10, l=10, b=10))
st.plotly_chart(fig_line, width="stretch")

# ---------- Map ----------
st.subheader("Where are the complaints? (sampled for performance)")
map_sample = df.dropna(subset=["latitude", "longitude"]).copy()
if len(map_sample) > 10_000:
    map_sample = map_sample.sample(10_000, random_state=42)

fig_map = px.scatter_mapbox(
    map_sample,
    lat="latitude",
    lon="longitude",
    color="complaint_type",
    hover_data={"created_date": True, "status": True, "borough": True, "incident_zip": True},
    zoom=9,
    height=600,
    color_discrete_sequence=px.colors.qualitative.Set2,
    title=f"Geography of Requests (showing {len(map_sample):,} points)",
)
fig_map.update_layout(mapbox_style="open-street-map", margin=dict(t=60, r=0, l=0, b=0))
st.plotly_chart(fig_map, width="stretch")

# ---------- Borough splits ----------
st.subheader("Borough Breakdown")
boro = (
    df.groupby("borough")
    .agg(count=("complaint_type", "size"), median_hours=("response_hours", "median"))
    .reset_index()
    .sort_values("count", ascending=False)
)
cA, cB = st.columns(2)
with cA:
    fig_b1 = px.bar(
        boro,
        x="borough",
        y="count",
        color="count",
        color_continuous_scale="OrRd",
        title="Requests by Borough",
        labels={"borough": "Borough", "count": "Requests"},
    )
    fig_b1.update_layout(margin=dict(t=50, r=10, l=10, b=10))
    st.plotly_chart(fig_b1, width="stretch")
with cB:
    fig_b2 = px.bar(
        boro.sort_values("median_hours", ascending=True),
        x="borough",
        y="median_hours",
        color="median_hours",
        color_continuous_scale="Sunset",
        title="Median Response Time by Borough (hours)",
        labels={"borough": "Borough", "median_hours": "Median Hours"},
    )
    fig_b2.update_layout(margin=dict(t=50, r=10, l=10, b=10))
    st.plotly_chart(fig_b2, width="stretch")

st.markdown("---")
st.caption(
    "Built with Streamlit + Plotly using live data from NYC Open Data (dataset `erm2-nwe9`). "
    "This app fetches only a limited window + row count to keep maps responsive."
)
