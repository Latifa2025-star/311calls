# 311.py  — NYC 311 Service Requests Explorer
# -------------------------------------------
# Built for Streamlit Cloud. Ships with a local compressed CSV (nyc311_12months.csv.gz).
# Warm color palette, dynamic narratives, stable charts, and an interactive map.

import os
import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st
import folium
from streamlit_folium import st_folium

# ---------------------------
# Page & global styling
# ---------------------------
st.set_page_config(
    page_title="NYC 311 Service Requests Explorer",
    page_icon="📞",
    layout="wide",
)

WARM = px.colors.sequential.OrRd  # warm palette
WARM_R = px.colors.sequential.OrRd_r

st.title("📞 NYC 311 Service Requests Explorer")
st.caption(
    "Explore complaint types, resolution times, and closure rates by day and hour — "
    "powered by a compressed local dataset (`.csv.gz`)."
)

# ---------------------------
# Data loading (cached)
# ---------------------------
@st.cache_data(show_spinner=True)
def load_data():
    # prefer compressed file in repo
    fname_gz = "nyc311_12months.csv.gz"
    fname_csv = "nyc311_12months.csv"

    if os.path.exists(fname_gz):
        df = pd.read_csv(fname_gz, compression="gzip", low_memory=False)
        source = fname_gz
    elif os.path.exists(fname_csv):
        df = pd.read_csv(fname_csv, low_memory=False)
        source = fname_csv
    else:
        raise FileNotFoundError(
            "Could not find nyc311_12months.csv(.gz) in the repo. "
            "Upload the file next to 311.py and redeploy."
        )

    # Minimal normalization
    for c in ("created_date", "closed_date"):
        if c in df.columns:
            df[c] = pd.to_datetime(df[c], errors="coerce")

    # Status column normalization (robust to casing/None)
    if "status" in df.columns:
        df["status"] = df["status"].astype(str).str.strip().replace({"nan": "Unspecified"})
    else:
        df["status"] = "Unspecified"

    # Derived fields
    df["hour"] = df["created_date"].dt.hour
    df["day_of_week"] = df["created_date"].dt.day_name()
    df["resolution_time"] = (
        (df["closed_date"] - df["created_date"]).dt.total_seconds() / 3600
    )

    # clean lat/long if present
    for c in ("latitude", "longitude"):
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")

    # keep only rows with a complaint type
    if "complaint_type" in df.columns:
        df = df.dropna(subset=["complaint_type"])
    else:
        raise ValueError("Expected a 'complaint_type' column in the dataset.")

    return df, source


try:
    df, source_name = load_data()
    st.success(f"✅ Loaded data from `{source_name}`")
except Exception as e:
    st.error(str(e))
    st.stop()

# ---------------------------
# Sidebar filters (simple & reliable)
# ---------------------------
st.sidebar.header("Filters")

days = ["All"] + sorted(df["day_of_week"].dropna().unique().tolist())
day_filter = st.sidebar.selectbox("Day of Week", days, index=0)

hour_filter = st.sidebar.slider("Hour range (24h)", 0, 23, (0, 23))

all_boroughs = sorted(df["borough"].dropna().unique().tolist()) if "borough" in df.columns else []
if all_boroughs:
    boroughs = st.sidebar.multiselect("Borough(s)", all_boroughs, default=all_boroughs)
else:
    boroughs = []  # no borough column in data

top_n = st.sidebar.slider("Top complaint types to show", 5, 30, 20)

# ---------------------------
# Apply filters
# ---------------------------
df_f = df.copy()

# day
if day_filter != "All":
    df_f = df_f[df_f["day_of_week"] == day_filter]

# hour
df_f = df_f[(df_f["hour"] >= hour_filter[0]) & (df_f["hour"] <= hour_filter[1])]

# borough(s)
if all_boroughs and boroughs:
    df_f = df_f[df_f["borough"].isin(boroughs)]

# ---------------------------
# KPIs
# ---------------------------
k1, k2, k3, k4 = st.columns(4)
total_rows = int(df_f.shape[0])
pct_closed = float((df_f["status"] == "Closed").mean() * 100) if total_rows else 0.0
median_hours = float(df_f["resolution_time"].median()) if total_rows else np.nan
top_type = df_f["complaint_type"].mode()[0] if total_rows else "—"

k1.metric("Rows (after filters)", f"{total_rows:,}")
k2.metric("% Closed", f"{pct_closed:.1f}%")
k3.metric("Median Hours to Close", "—" if np.isnan(median_hours) else f"{median_hours:.2f}")
k4.metric("Top Complaint Type", top_type)

# ===========================
# Top Complaint Types (bar)
# ===========================
st.subheader("📊 Top Complaint Types")
st.caption("What issues are most frequently reported under the current filters?")

if total_rows:
    counts = (
        df_f["complaint_type"].value_counts()
        .reset_index()
        .rename(columns={"index": "complaint_type", "complaint_type": "count"})
        .head(top_n)
    )

    # narrative (safe)
    if not counts.empty:
        lead_row = counts.iloc[0]
        st.markdown(
            f"**Narrative:** **{lead_row['complaint_type']}** leads with "
            f"**{int(lead_row['count']):,}** requests under the current filters."
        )

    fig_bar = px.bar(
        counts,
        x="count",
        y="complaint_type",
        orientation="h",
        text="count",
        color="count",
        color_continuous_scale=WARM_R,
        title=f"Top {top_n} Complaint Types",
    )
    fig_bar.update_layout(
        yaxis=dict(autorange="reversed", title=None),
        xaxis_title="Requests (count)",
        title_font=dict(size=18),
        coloraxis_showscale=False,
        margin=dict(l=10, r=10, t=50, b=10),
    )
    fig_bar.update_traces(texttemplate="%{text:,}", textposition="outside", hovertemplate="%{y}<br>Requests: %{x:,}")
    st.plotly_chart(fig_bar, use_container_width=True)
else:
    st.info("No rows for the selected filters.")

# ===========================
# Status Breakdown (pie)
# ===========================
st.subheader("📈 Status Breakdown")
st.caption("How are requests currently tracked (Closed, In Progress, etc.) under the filters?")

if total_rows:
    status_counts = (
        df_f["status"].fillna("Unspecified").value_counts().reset_index()
        .rename(columns={"index": "status", "status": "count"})
    )
    # Ensure unique column names (avoids narwhals DuplicateError)
    status_counts = status_counts.loc[:, ["status", "count"]]

    fig_pie = px.pie(
        status_counts,
        names="status",
        values="count",
        hole=0.52,
        color="status",
        color_discrete_sequence=px.colors.qualitative.Set3,
        title="Overall Status Mix",
    )
    fig_pie.update_traces(textinfo="label+percent", pull=0.03, hovertemplate="%{label}: %{value:,} requests")
    fig_pie.update_layout(margin=dict(l=10, r=10, t=50, b=10))
    st.plotly_chart(fig_pie, use_container_width=True)

    # narrative
    top_status = status_counts.iloc[0]
    st.markdown(
        f"**Narrative:** The most common status is **{top_status['status']}** "
        f"with **{int(top_status['count']):,}** requests."
    )
else:
    st.info("Status breakdown unavailable for the current selection.")

# ===========================================
# Animated bar: complaints by hour (0 → 23)
# ===========================================
st.subheader("▶️ How do complaints evolve through the day?")
st.caption("Press **Play** to watch requests change by hour (top categories shown for clarity).")

if total_rows:
    # focus on the top 6 categories for clarity
    top6 = (
        df_f["complaint_type"].value_counts()
        .head(6)
        .index.tolist()
    )
    df_anim = df_f[df_f["complaint_type"].isin(top6)][["hour", "complaint_type"]].copy()

    # aggregate counts per hour & type
    hourly = (
        df_anim.groupby(["hour", "complaint_type"])
        .size()
        .reset_index(name="count")
    )

    # make sure every hour 0..23 exists for each category
    all_hours = pd.Index(range(24), name="hour")
    hourly = (
        hourly.set_index(["hour", "complaint_type"])
        .reindex(pd.MultiIndex.from_product([all_hours, top6], names=["hour", "complaint_type"]), fill_value=0)
        .reset_index()
    )

    # Animated horizontal bar
    fig_anim = px.bar(
        hourly,
        x="count",
        y="complaint_type",
        color="complaint_type",
        orientation="h",
        animation_frame="hour",
        category_orders={"complaint_type": top6},
        range_x=[0, max(1, int(hourly["count"].max() * 1.1))],
        color_discrete_sequence=WARM,
        title="How requests evolve through the day (press ▶ to play)",
    )
    fig_anim.update_layout(
        xaxis_title="Requests (count)",
        yaxis_title="Complaint Type",
        title_font=dict(size=18),
        margin=dict(l=10, r=10, t=50, b=10),
        showlegend=False,
    )
    # force the slider to show 0..23
    # (Streamlit renders the Plotly slider; we ensure animation frames exist for all hours above)
    st.plotly_chart(fig_anim, use_container_width=True)

    # narrative (peak hour)
    hour_totals = hourly.groupby("hour")["count"].sum()
    peak_hour = int(hour_totals.idxmax()) if hour_totals.sum() > 0 else 0
    st.markdown(f"**Narrative:** Within the shown categories, peaks typically occur around **{peak_hour:02d}:00**.")
else:
    st.info("Not enough data to animate hourly changes for the current filters.")

# ==================================
# Resolution time by complaint type
# ==================================
st.subheader("⏱️ Resolution Time by Complaint Type")
st.caption("Compare how long each type of complaint typically takes to resolve.")

if total_rows and df_f["resolution_time"].notna().any():
    fig_box = px.box(
        df_f.dropna(subset=["resolution_time"]),
        x="complaint_type",
        y="resolution_time",
        color="complaint_type",
        points=False,
        title="Resolution Time (hours)",
        color_discrete_sequence=px.colors.qualitative.Set2,
    )
    fig_box.update_layout(
        xaxis_title=None,
        yaxis_title="Hours to Close",
        showlegend=False,
        title_font=dict(size=18),
        margin=dict(l=10, r=10, t=50, b=10),
    )
    fig_box.update_xaxes(tickangle=45)
    st.plotly_chart(fig_box, use_container_width=True)

    med = df_f["resolution_time"].median()
    st.markdown(
        f"**Narrative:** Median resolution time across the selection is **{med:.2f} hours**. "
        f"Categories with longer tails may indicate complex or backlog-prone issues."
    )
else:
    st.info("No resolution-time data available for the current selection.")

# ===========================
# Interactive geographic map
# ===========================
st.subheader("🗺️ Complaint Hotspots Across NYC")
st.caption("Markers show complaint locations. Colors indicate status; click a marker for details.")

has_geo = {"latitude", "longitude"}.issubset(df_f.columns)
if total_rows and has_geo:
    df_geo = df_f.dropna(subset=["latitude", "longitude"])
    if df_geo.empty:
        st.info("No geographic coordinates in the filtered data.")
    else:
        # Limit points for performance
        sample_n = min(1500, len(df_geo))
        smp = df_geo.sample(sample_n, random_state=42)

        # center map at median coordinates
        center = [float(smp["latitude"].median()), float(smp["longitude"].median())]
        m = folium.Map(location=center, zoom_start=11, tiles="cartodbpositron")

        # marker colors by status
        def status_color(s):
            s = str(s)
            if s == "Closed":
                return "green"
            if "Progress" in s:
                return "orange"
            if s in ("Open", "Started", "Assigned", "Pending"):
                return "red"
            return "blue"  # fallback / Unspecified

        for _, r in smp.iterrows():
            pop = (
                f"<b>Complaint:</b> {r['complaint_type']}<br>"
                f"<b>Status:</b> {r.get('status', 'Unspecified')}<br>"
                f"<b>Borough:</b> {r.get('borough', '—')}<br>"
                f"<b>Created:</b> {r.get('created_date', '—')}<br>"
                f"<b>Hours to Close:</b> "
                f"{'—' if pd.isna(r.get('resolution_time')) else f'{r.get('resolution_time'):.2f}'}"
            )
            folium.CircleMarker(
                location=[float(r["latitude"]), float(r["longitude"])],
                radius=4,
                color=status_color(r.get("status")),
                fill=True,
                fill_opacity=0.7,
                popup=folium.Popup(pop, max_width=300),
            ).add_to(m)

        # Legend
        legend_html = """
        <div style="
             position: fixed; bottom: 40px; left: 40px; width: 200px; z-index:9999;
             background: white; border: 1px solid #999; border-radius: 6px; padding: 10px;
             font-size: 14px; box-shadow: 0 2px 6px rgba(0,0,0,.2);">
          <b>Legend</b><br>
          🟢 Closed<br>
          🟠 In Progress<br>
          🔴 Open/Assigned/Started/Pending<br>
          🔵 Unspecified/Other
        </div>
        """
        m.get_root().html.add_child(folium.Element(legend_html))

        st_folium(m, width=1100, height=600)
else:
    st.info("Map not available (missing latitude/longitude in the current selection).")

st.markdown("---")
st.caption(
    "Tip: Adjust the filters in the sidebar to focus your analysis. "
    "All narratives and charts update automatically."
)


