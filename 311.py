# 311.py — NYC 311 Service Requests Explorer (Plotly-only version)
# Works on Streamlit Cloud without extra libs (no folium dependency).
# Data file expected: nyc311_12months.csv.gz  (in the repo root)

from __future__ import annotations
import pandas as pd
import numpy as np
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go

# ------------------------------- CONFIG ---------------------------------
DATA_FILE = "nyc311_12months.csv.gz"   # compressed CSV (gzip)
PAGE_TITLE = "NYC 311 Service Requests Explorer"
PRIMARY = "#4f46e5"  # indigo-600
ACCENT = "#f97316"   # orange-500
GREEN = "#10b981"    # emerald-500
RED = "#ef4444"      # red-500
YlOrRd = px.colors.sequential.YlOrRd

st.set_page_config(page_title=PAGE_TITLE, page_icon="📞", layout="wide")

# ------------------------------- HELPERS --------------------------------
@st.cache_data(show_spinner=False)
def load_data(path: str) -> pd.DataFrame:
    df = pd.read_csv(path, compression="gzip")
    # Soft normalization
    for c in ("created_date", "closed_date", "resolution_action_updated_date"):
        if c in df.columns:
            df[c] = pd.to_datetime(df[c], errors="coerce")
    if "status" in df.columns:
        df["status"] = df["status"].astype(str)
    if "complaint_type" in df.columns:
        df["complaint_type"] = df["complaint_type"].astype(str).fillna("(Unknown)")
    if "borough" in df.columns:
        df["borough"] = df["borough"].astype(str).replace({"": "Unspecified"}).fillna("Unspecified")

    # Derived fields
    if {"created_date","closed_date"}.issubset(df.columns):
        hrs = (df["closed_date"] - df["created_date"]).dt.total_seconds()/3600.0
        df["hours_to_close"] = hrs
    if "created_date" in df:
        df["day_of_week"] = df["created_date"].dt.day_name()
        df["hour"] = df["created_date"].dt.hour
        df["date"] = df["created_date"].dt.date
    # closed flag
    df["is_closed"] = df.get("status","").str.lower().str.contains("closed", na=False)
    return df

def fmt_int(x: float | int) -> str:
    try:
        return f"{int(x):,}"
    except Exception:
        return "—"

def narrative_paragraph(text: str):
    st.markdown(
        f"""<div style="background:#f8fafc;border-left:6px solid {PRIMARY};padding:12px 14px;margin:6px 0;border-radius:6px">
        <span style="font-size:0.96rem">{text}</span></div>""",
        unsafe_allow_html=True,
    )

def big_title(title: str, emoji: str="📊"):
    st.markdown(
        f"<h2 style='margin-top:0.6rem;margin-bottom:0.2rem;font-weight:800'>{emoji} {title}</h2>",
        unsafe_allow_html=True
    )

def safe_top_counts(df: pd.DataFrame, col: str, n: int) -> pd.DataFrame:
    if col not in df.columns or df.empty:
        return pd.DataFrame({col: [], "count": []})
    out = (df[col].value_counts().head(n)
           .rename_axis(col).reset_index(name="count"))
    return out

def ensure_nonempty(fig: go.Figure, msg="No data for current filters"):
    if fig is None:
        st.info(msg)
        return False
    return True

# ------------------------------- LOAD DATA ------------------------------
with st.spinner("Loading NYC 311 data…"):
    df_all = load_data(DATA_FILE)

# ------------------------------- SIDEBAR FILTERS ------------------------
st.sidebar.success(f"Loaded data from **{DATA_FILE}**")
day_sel = st.sidebar.selectbox("Day of Week", ["All"] + sorted(df_all["day_of_week"].dropna().unique().tolist()))
hr = st.sidebar.slider("Hour range (24h)", 0, 23, (0, 23))
boroughs = st.sidebar.multiselect(
    "Borough(s)",
    options=sorted(df_all["borough"].dropna().unique().tolist()),
    default=[],
)
top_n = st.sidebar.slider("Top complaint types to show", 5, 30, 20)

# Apply filters
df = df_all.copy()
if day_sel != "All":
    df = df[df["day_of_week"] == day_sel]
df = df[(df["hour"] >= hr[0]) & (df["hour"] <= hr[1])]
if boroughs:
    df = df[df["borough"].isin(boroughs)]

# ------------------------------- HEADER ---------------------------------
st.markdown(
    f"<h1 style='font-weight:900;margin:4px 0'>📞 {PAGE_TITLE}</h1>",
    unsafe_allow_html=True,
)
st.caption("Explore complaint types, resolution times, and closure rates by day and hour — powered by a compressed local dataset (.csv.gz).")

# Metrics
c1, c2, c3, c4 = st.columns(4)
c1.metric("Rows (after filters)", fmt_int(len(df)))
closed_pct = (df["is_closed"].mean() * 100) if len(df) else 0
c2.metric("% Closed", f"{closed_pct:,.1f}%")
med_hours = df["hours_to_close"].median() if "hours_to_close" in df and len(df) else None
c3.metric("Median Hours to Close", f"{med_hours:,.2f}" if med_hours==med_hours else "—")
lead_type = df["complaint_type"].mode().iloc[0] if ("complaint_type" in df and len(df)) else "—"
c4.metric("Top Complaint Type", lead_type)

# ------------------------------- TOP TYPES & STATUS ---------------------
big_title("Top Complaint Types")
st.caption("What issues are most frequently reported under the current filters?")

counts = safe_top_counts(df, "complaint_type", top_n)
lead_txt = "No dominant complaint in current filters."
if not counts.empty:
    lead = counts.iloc[0]
    lead_txt = f"**{lead['complaint_type']}** leads with **{fmt_int(lead['count'])}** requests."
narrative_paragraph(lead_txt)

colL, colR = st.columns([2,1], gap="large")

with colL:
    if not counts.empty:
        fig_bar = px.bar(
            counts.sort_values("count"),
            x="count", y="complaint_type", orientation="h",
            color="count",
            color_continuous_scale=YlOrRd,
            labels={"count":"Requests (count)", "complaint_type":"Complaint Type"},
            title=f"Top {min(top_n,len(counts))} Complaint Types",
        )
        fig_bar.update_layout(height=520, coloraxis_showscale=False,
                              xaxis_title="Requests (count)", yaxis_title=None,
                              margin=dict(l=10,r=10,t=60,b=10))
        st.plotly_chart(fig_bar, use_container_width=True)
    else:
        st.info("No data for current filters.")

with colR:
    if "status" in df.columns and not df.empty:
        status_counts = (df["status"].value_counts().reset_index()
                         .rename(columns={"index":"status","status":"count"}))
        fig_pie = px.pie(
            status_counts, values="count", names="status",
            hole=0.55, color_discrete_sequence=px.colors.qualitative.Set3,
            title="Status Breakdown"
        )
        fig_pie.update_traces(textinfo="percent+label")
        fig_pie.update_layout(height=520, margin=dict(l=10,r=10,t=60,b=10))
        st.plotly_chart(fig_pie, use_container_width=True)
    else:
        st.info("No status information available.")

# ------------------------ RESOLUTION TIME (BOXPLOT) ---------------------
big_title("Resolution Time by Complaint Type (hours)")
st.caption("How long do issues take to close? Boxes show median and IQR; whiskers show spread (outliers clipped at 99th percentile for readability).")

if "hours_to_close" in df.columns and not df.empty:
    g = df.dropna(subset=["hours_to_close"]).copy()
    if not g.empty:
        q99 = g["hours_to_close"].quantile(0.99)
        g = g[g["hours_to_close"] <= q99]
        # show top K frequent types for readability
        keep_types = df["complaint_type"].value_counts().head(18).index.tolist()
        g = g[g["complaint_type"].isin(keep_types)]
        fig_box = px.box(
            g, x="complaint_type", y="hours_to_close",
            color="complaint_type", points=False,
            color_discrete_sequence=px.colors.qualitative.Vivid,
            labels={"hours_to_close":"Hours to Close","complaint_type":"Complaint Type"},
        )
        fig_box.update_layout(showlegend=False, height=520, margin=dict(l=10,r=10,t=10,b=120))
        fig_box.update_xaxes(tickangle=45, tickfont=dict(size=12))
        st.plotly_chart(fig_box, use_container_width=True)
        # Narrative
        med_tbl = (g.groupby("complaint_type")["hours_to_close"]
                   .median().sort_values().head(3))
        slow_tbl = (g.groupby("complaint_type")["hours_to_close"]
                    .median().sort_values().tail(3))
        narrative_paragraph(
            f"Fastest median close times: **{', '.join([f'{k} ({v:.1f}h)' for k,v in med_tbl.items()])}**. "
            f"Slowest: **{', '.join([f'{k} ({v:.1f}h)' for k,v in slow_tbl.items()])}**."
        )
    else:
        st.info("No resolution time data in current filters.")
else:
    st.info("No resolution time data available in dataset.")

# ------------------------------ HEATMAP ---------------------------------
big_title("When are requests made? (Day × Hour)")
st.caption("Hover shows **Requests (count)**. Use filters to focus by day, hour window, and borough.")

if {"day_of_week","hour"}.issubset(df.columns) and not df.empty:
    day_order = ["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"]
    H = (df.groupby(["day_of_week","hour"]).size()
         .rename("Requests").reset_index())
    H["day_of_week"] = pd.Categorical(H["day_of_week"], categories=day_order, ordered=True)
    H = H.sort_values(["day_of_week","hour"])
    fig_heat = px.density_heatmap(
        H, x="hour", y="day_of_week", z="Requests",
        color_continuous_scale=YlOrRd, nbinsx=24, nbinsy=7,
        labels={"hour":"Hour of Day (24h)", "day_of_week":"Day of Week", "Requests":"Requests"},
        hovertemplate="<b>%{y}</b> • %{x}:00<br>Requests: %{z}<extra></extra>",
    )
    fig_heat.update_layout(height=520, margin=dict(l=10,r=10,t=10,b=10),
                           coloraxis_colorbar=dict(title="Requests"))
    st.plotly_chart(fig_heat, use_container_width=True)
else:
    st.info("Insufficient data for heatmap.")

# ------------------------------ ANIMATIONS ------------------------------
big_title("Animated Stories")
tabs = st.tabs(["▶︎ Bar Race — Requests by Hour", "▶︎ Bubble — Speed & Volume"])

# 1) Animated bar race across hours
with tabs[0]:
    st.caption("Press play: shows how top complaint types rise and fall throughout the day.")
    if not df.empty:
        hourly = (df.groupby(["hour", "complaint_type"])
                  .size().rename("count").reset_index())
        # Keep only the top K overall types to reduce clutter
        top_overall = (hourly.groupby("complaint_type")["count"]
                       .sum().sort_values(ascending=False).head(10).index.tolist())
        hourly = hourly[hourly["complaint_type"].isin(top_overall)]
        if not hourly.empty:
            fig_anim = px.bar(
                hourly.sort_values("count"),
                x="count", y="complaint_type", orientation="h",
                color="complaint_type",
                animation_frame="hour",
                range_x=[0, hourly["count"].max()*1.1],
                labels={"count":"Requests (count)", "complaint_type":"Complaint Type", "hour":"Hour"},
                color_discrete_sequence=px.colors.qualitative.Bold,
            )
            fig_anim.update_layout(height=560, showlegend=False,
                                   xaxis_title="Requests (count)", yaxis_title=None,
                                   margin=dict(l=10,r=10,t=10,b=10))
            st.plotly_chart(fig_anim, use_container_width=True)
        else:
            st.info("No data for animation in current filters.")
    else:
        st.info("No data for animation in current filters.")

# 2) Animated bubble chart: by hour, size = volume, y = median hours_to_close
with tabs[1]:
    st.caption("Press play: each hour shows complaint types (bubble size = #requests, color = type, y = median hours to close).")
    if {"hours_to_close","hour","complaint_type"}.issubset(df.columns) and not df.empty:
        tmp = df.dropna(subset=["hours_to_close"]).copy()
        if not tmp.empty:
            g = (tmp.groupby(["hour","complaint_type"])
                 .agg(count=("complaint_type","size"),
                      median_hours=("hours_to_close","median"))
                 .reset_index())
            top_overall = (g.groupby("complaint_type")["count"]
                           .sum().sort_values(ascending=False).head(12).index.tolist())
            g = g[g["complaint_type"].isin(top_overall)]
            ymax = max(1.0, g["median_hours"].quantile(0.98))
            fig_bubbles = px.scatter(
                g, x="hour", y="median_hours", size="count", color="complaint_type",
                animation_frame="hour", range_x=[hr[0], hr[1]],
                range_y=[0, ymax*1.1],
                labels={"hour":"Hour of Day","median_hours":"Median Hours to Close","count":"Requests (count)"},
                color_discrete_sequence=px.colors.qualitative.Dark24,
                hover_data={"count":":,","complaint_type":True,"hour":True,"median_hours":":.2f"},
            )
            fig_bubbles.update_layout(height=560, margin=dict(l=10,r=10,t=10,b=10),
                                      showlegend=False)
            st.plotly_chart(fig_bubbles, use_container_width=True)
        else:
            st.info("No resolution-time data for animation in current filters.")
    else:
        st.info("Need hours_to_close for this animation (not found in current data/filters).")

# ------------------------------- MAPS -----------------------------------
big_title("Geometric Map — Where are complaints concentrated?")
st.caption("Toggle layer type. For performance, the point layer samples up to 10,000 rows. Hover for details. No Mapbox token required.")

if {"latitude","longitude"}.issubset(df.columns) and not df.empty:
    map_mode = st.radio("Map layer", ["Density (heat)", "Scatter (points)"], horizontal=True, index=0)
    mdf = df.dropna(subset=["latitude","longitude"]).copy()
    if map_mode == "Scatter (points)":
        if len(mdf) > 10000:
            mdf = mdf.sample(10000, random_state=42)
        fig_map = px.scatter_mapbox(
            mdf, lat="latitude", lon="longitude",
            color="complaint_type",
            hover_name="complaint_type",
            hover_data={"status":True, "borough":True, "hours_to_close":":.2f"},
            zoom=9, height=640,
            color_discrete_sequence=px.colors.qualitative.Set2,
        )
    else:
        # Density heat
        fig_map = px.density_mapbox(
            mdf, lat="latitude", lon="longitude", z=None,
            radius=12, hover_name="complaint_type",
            hover_data={"status":True,"borough":True},
            zoom=9, height=640,
            color_continuous_scale=YlOrRd,
        )
    fig_map.update_layout(mapbox_style="carto-positron", margin=dict(l=10,r=10,t=10,b=10))
    st.plotly_chart(fig_map, use_container_width=True)
else:
    st.info("No latitude/longitude present in current filters.")

# ------------------------------- FOOTER ---------------------------------
st.caption("Tip: Use the filters on the left to focus by day, hour window, and borough(s). Charts update instantly.")
