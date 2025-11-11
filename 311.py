# app.py — Single‑file Streamlit app for NYC 311 (sampled)
# ---------------------------------------------------------
# Features
# - Sidebar filters (date range, borough, status, complaint types)
# - Server‑side sampling via Socrata SODA API ($limit)
# - KPIs (total, % closed, median hours to close, top type)
# - Charts: time series, top complaint types, borough breakdown, resolution time boxplot
# - Interactive map (pydeck)
# - Data preview + CSV download
# - Optional fallback: upload your own sample CSV
# - Works WITHOUT a token, but add X‑App‑Token for higher rate limits

from __future__ import annotations
import os
import io
import math
from datetime import datetime, timedelta, date
from typing import List, Optional

import pandas as pd
import numpy as np
import requests
import streamlit as st
import plotly.express as px
import pydeck as pdk

# ---------------------- CONFIG ----------------------
SODA_ENDPOINT = "https://data.cityofnewyork.us/resource/erm2-nwe9.json"
DATASET_ID = "erm2-nwe9"
DEFAULT_LIMIT = 15000  # server‑side max rows (adjustable in UI)

CORE_COLUMNS = [
    "created_date", "closed_date", "agency_name", "complaint_type", "descriptor",
    "status", "resolution_description", "resolution_action_updated_date",
    "borough", "incident_zip", "latitude", "longitude"
]

st.set_page_config(page_title="NYC 311 Explorer (Single‑file)", page_icon="📞", layout="wide")
st.title("📞 NYC 311 Service Requests — Single‑file Explorer (Sampled)")
st.caption("Fast, interactive insights on NYC 311 data with server‑side sampling for performance.")

# ---------------------- HELPERS ----------------------
def _quote_list(values: List[str]) -> str:
    # SODA expects single quotes; escape internal quotes
    safe = [f"'{v.replace("'", "''")}'" for v in values]
    return ",".join(safe)


def build_where(start_dt: datetime, end_dt: datetime, boroughs: Optional[List[str]],
                complaint_types: Optional[List[str]], statuses: Optional[List[str]]) -> str:
    clauses = [
        f"created_date >= '{start_dt.strftime('%Y-%m-%dT00:00:00')}'",
        f"created_date <= '{end_dt.strftime('%Y-%m-%dT23:59:59')}'",
        "latitude IS NOT NULL AND longitude IS NOT NULL",
    ]
    if boroughs:
        clauses.append(f"borough in ({_quote_list(boroughs)})")
    if complaint_types:
        clauses.append(f"complaint_type in ({_quote_list(complaint_types)})")
    if statuses:
        clauses.append(f"status in ({_quote_list(statuses)})")
    return " AND ".join(clauses)


def fetch_311_sample(start_dt: datetime, end_dt: datetime, boroughs=None, complaint_types=None,
                     statuses=None, limit: int = DEFAULT_LIMIT, app_token: Optional[str] = None) -> pd.DataFrame:
    params = {
        "$select": ",".join(CORE_COLUMNS),
        "$where": build_where(start_dt, end_dt, boroughs, complaint_types, statuses),
        "$order": "created_date DESC",
        "$limit": int(limit),
    }
    headers = {"Accept": "application/json"}
    if app_token:
        headers["X-App-Token"] = app_token

    r = requests.get(SODA_ENDPOINT, params=params, headers=headers, timeout=60)
    r.raise_for_status()
    data = r.json()
    df = pd.DataFrame.from_records(data)
    if df.empty:
        return df

    # Type coercion
    for c in ["created_date", "closed_date", "resolution_action_updated_date"]:
        if c in df.columns:
            df[c] = pd.to_datetime(df[c], errors="coerce")
    for c in ["latitude", "longitude"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")

    # Derived metrics
    if {"created_date", "closed_date"}.issubset(df.columns):
        df["hours_to_close"] = (df["closed_date"] - df["created_date"]).dt.total_seconds() / 3600.0

    if "complaint_type" in df.columns:
        df["complaint_type"].fillna("(Unknown)", inplace=True)
    if "borough" in df.columns:
        df["borough"].fillna("Unknown", inplace=True)

    return df


# ---------------------- SIDEBAR ----------------------
with st.sidebar:
    st.header("Filters")
    default_end = datetime.utcnow().date()
    default_start = default_end - timedelta(days=90)
    date_range = st.date_input(
        "Date range (created date)",
        value=(default_start, default_end),
        min_value=date(2010, 1, 1),
        max_value=default_end,
    )

    sample_size = st.slider("Max rows to fetch (server‑side)", 1000, 50000, DEFAULT_LIMIT, step=1000)

    boroughs = st.multiselect("Borough(s)", ["BRONX", "BROOKLYN", "MANHATTAN", "QUEENS", "STATEN ISLAND"], [])
    statuses = st.multiselect("Status", ["Open", "Closed"], [])
    types_text = st.text_input("Complaint types (comma‑separated)", "")
    complaint_types = [t.strip() for t in types_text.split(",") if t.strip()] if types_text else None

    st.markdown("---")
    st.subheader("Data source & fallback")
    st.caption("Optional Socrata X‑App‑Token improves reliability. You can also upload a local sample CSV.")
    token = st.text_input("Socrata App Token (optional)", value=os.environ.get("SODA_APP_TOKEN", ""), type="password")
    uploaded = st.file_uploader("Or upload a local sample CSV (same columns)", type=["csv"])

# ---------------------- DATA LOADING ----------------------
@st.cache_data(show_spinner=True, ttl=1800)
def load_data(start_dt: datetime, end_dt: datetime, boroughs, complaint_types, statuses, limit: int, token: str):
    try:
        df = fetch_311_sample(start_dt, end_dt, boroughs, complaint_types, statuses, limit=limit, app_token=token or None)
        return df
    except Exception as e:
        st.toast(f"API error: {e}", icon="⚠️")
        return pd.DataFrame()

start_dt = datetime.combine(date_range[0], datetime.min.time())
end_dt = datetime.combine(date_range[1], datetime.max.time())

if uploaded is not None:
    df = pd.read_csv(uploaded)
    # Coerce a bit for safety
    for c in ["created_date", "closed_date", "resolution_action_updated_date"]:
        if c in df.columns:
            df[c] = pd.to_datetime(df[c], errors="coerce")
    for c in ["latitude", "longitude"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    if {"created_date", "closed_date"}.issubset(df.columns) and "hours_to_close" not in df.columns:
        df["hours_to_close"] = (pd.to_datetime(df["closed_date"]) - pd.to_datetime(df["created_date"])) .dt.total_seconds()/3600.0
else:
    df = load_data(start_dt, end_dt, boroughs or None, complaint_types, statuses or None, sample_size, token)

if df.empty:
    st.warning("No data returned for the current filters (or API unavailable). Try widening the date range, adding a token, or uploading a local sample.")
    st.stop()

# ---------------------- KPIs ----------------------
col1, col2, col3, col4 = st.columns(4)
with col1:
    st.metric("Total Requests (sample)", f"{len(df):,}")
with col2:
    pct_closed = (df["status"].str.lower() == "closed").mean() * 100 if "status" in df.columns else np.nan
    st.metric("% Closed", f"{pct_closed:,.1f}%" if not math.isnan(pct_closed) else "—")
with col3:
    med_hours = df["hours_to_close"].median() if "hours_to_close" in df.columns else np.nan
    st.metric("Median Hours to Close", f"{med_hours:,.1f}" if pd.notnull(med_hours) else "—")
with col4:
    top_type = df["complaint_type"].mode().iloc[0] if "complaint_type" in df.columns and not df["complaint_type"].empty else "—"
    st.metric("Top Complaint Type", top_type)

st.markdown("---")

# ---------------------- CHARTS ----------------------
# 1) Time series by day
if "created_date" in df.columns:
    ts = (df.assign(day=lambda x: pd.to_datetime(x["created_date"]).dt.date)
             .groupby("day", as_index=False)
             .size())
    fig_ts = px.line(ts, x="day", y="size", markers=True, title="Requests Over Time (sample)")
    st.plotly_chart(fig_ts, use_container_width=True)

# 2) Top complaint types
if "complaint_type" in df.columns:
    topn = df["complaint_type"].value_counts().head(15).reset_index().rename(columns={"index":"complaint_type", "complaint_type":"count"})
    fig_bar = px.bar(topn, x="count", y="complaint_type", orientation="h", title="Top 15 Complaint Types (sample)")
    st.plotly_chart(fig_bar, use_container_width=True)

# 3) Borough breakdown
if "borough" in df.columns:
    bor = df["borough"].value_counts().reset_index().rename(columns={"index":"borough", "borough":"count"})
    fig_bor = px.bar(bor, x="borough", y="count", title="Requests by Borough (sample)")
    st.plotly_chart(fig_bor, use_container_width=True)

# 4) Resolution time by complaint type (box, clipped at 99th percentile)
if "hours_to_close" in df.columns and df["hours_to_close"].notna().any():
    sub = df.dropna(subset=["hours_to_close"]).copy()
    q99 = sub["hours_to_close"].quantile(0.99)
    sub = sub[sub["hours_to_close"] <= q99]
    fig_box = px.box(sub, x="complaint_type", y="hours_to_close", points=False,
                     title="Hours to Close by Complaint Type (clipped at 99th pct)")
    fig_box.update_layout(xaxis_tickangle=-45)
    st.plotly_chart(fig_box, use_container_width=True)

st.markdown("---")

# ---------------------- MAP ----------------------
if {"latitude", "longitude"}.issubset(df.columns):
    map_df = df.dropna(subset=["latitude", "longitude"]).copy()
    st.subheader("Map of Requests (sample)")
    st.caption("Zoom to explore. Points are semi‑transparent to reveal density.")
    layer = pdk.Layer(
        "ScatterplotLayer",
        data=map_df,
        get_position="[longitude, latitude]",
        get_radius=20,
        radius_min_pixels=1,
        radius_max_pixels=30,
        opacity=0.25,
        pickable=True,
    )
    view_state = pdk.ViewState(latitude=40.7128, longitude=-74.0060, zoom=9)
    st.pydeck_chart(pdk.Deck(layers=[layer], initial_view_state=view_state, tooltip={"text": "{complaint_type}\n{borough}"}))

st.markdown("---")

# ---------------------- DATA TABLE & DOWNLOAD ----------------------
st.subheader("Sampled Records")
show_cols = [c for c in [
    "created_date", "closed_date", "status", "agency_name", "complaint_type", "descriptor",
    "borough", "incident_zip", "latitude", "longitude", "hours_to_close"
] if c in df.columns]
st.dataframe(df[show_cols].head(1000))

csv_buf = io.StringIO()
df.to_csv(csv_buf, index=False)
st.download_button("Download current sample as CSV", csv_buf.getvalue(), file_name="nyc311_sample.csv", mime="text/csv")

st.caption("Note: This app fetches a sampled slice for speed. Increase the sample size in the sidebar for more points.")

