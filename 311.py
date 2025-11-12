# 311.py
# NYC 311 Service Requests Explorer
# Streamlit app with robust narratives, warm visuals, animations, and an interactive map.

import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import folium
from streamlit_folium import st_folium

# -------------------------------
# Page config
# -------------------------------
st.set_page_config(
    page_title="NYC 311 Service Requests Explorer",
    layout="wide",
    page_icon="📞",
)

# -------------------------------
# Helpers
# -------------------------------
HOUR_ORDER = list(range(24))
WARM = px.colors.sequential.OrRd_r  # warm palette
MAP_TILE = "cartodbpositron"

def fmt_int(x):
    try:
        return f"{int(x):,}"
    except Exception:
        return "—"

def safe_mode(s: pd.Series, default="N/A"):
    try:
        return s.mode(dropna=True).iloc[0]
    except Exception:
        return default

# -------------------------------
# Load data (cached)
# -------------------------------
@st.cache_data(show_spinner=True)
def load_data(path: str) -> pd.DataFrame:
    df = pd.read_csv(path, compression="gzip", low_memory=False)
    # Dates
    df["created_date"] = pd.to_datetime(df.get("created_date"), errors="coerce")
    df["closed_date"] = pd.to_datetime(df.get("closed_date"), errors="coerce")
    # Derivatives
    df["hour"] = df["created_date"].dt.hour
    df["day_of_week"] = df["created_date"].dt.day_name()
    if "status" not in df:
        df["status"] = "Unknown"
    # Resolution time (hours)
    df["resolution_time"] = (
        (df["closed_date"] - df["created_date"]).dt.total_seconds() / 3600
    )
    # Standardize critical columns
    for c in ["complaint_type", "borough", "latitude", "longitude"]:
        if c not in df.columns:
            df[c] = np.nan
    return df

with st.spinner("Loading NYC 311 data…"):
    df_full = load_data("nyc311_12months.csv.gz")

st.title("📞 NYC 311 Service Requests Explorer")
st.caption(
    "Explore complaint types, resolution times, and closure rates by day and hour — powered by your compressed dataset (`.csv.gz`)."
)

# -------------------------------
# Sidebar: filters
# -------------------------------
st.sidebar.header("Filters")
day_choice = st.sidebar.selectbox("Day of Week", ["All"] + sorted(df_full["day_of_week"].dropna().unique().tolist()))
hour_min, hour_max = st.sidebar.slider("Hour range (24h)", 0, 23, (0, 23))
borough_choices = st.sidebar.multiselect(
    "Borough(s)",
    options=sorted(df_full["borough"].dropna().unique().tolist()),
    default=sorted(df_full["borough"].dropna().unique().tolist()),
)
top_n = st.sidebar.slider("Top complaint types to show", 5, 30, 20)

# -------------------------------
# Apply filters
# -------------------------------
df = df_full.copy()
df = df[df["hour"].between(hour_min, hour_max)]
if day_choice != "All":
    df = df[df["day_of_week"] == day_choice]
if borough_choices:
    df = df[df["borough"].isin(borough_choices)]

# Guard for empty
if df.empty:
    st.warning("No rows match your current filters. Try broadening them.")
    st.stop()

# -------------------------------
# KPI row
# -------------------------------
total_rows = len(df)
pct_closed = (df["status"] == "Closed").mean() * 100 if "status" in df else np.nan
median_hours = df["resolution_time"].median()
top_type_overall = safe_mode(df["complaint_type"])

k1, k2, k3, k4 = st.columns(4)
k1.metric("Rows (after filters)", fmt_int(total_rows))
k2.metric("% Closed", f"{pct_closed:.1f}%")
k3.metric("Median Hours to Close", f"{0 if pd.isna(median_hours) else median_hours:.2f}")
k4.metric("Top Complaint Type", top_type_overall)

# Quick at-a-glance narrative
top_bor = safe_mode(df["borough"])
peak_hour_overall = (
    df.groupby("hour").size().reindex(HOUR_ORDER, fill_value=0).idxmax()
    if not df.empty else "—"
)
st.markdown(
    f"**At a glance:** Requests peak around **{peak_hour_overall}:00**. "
    f"Most common issue: **{top_type_overall}**. "
    f"Median closure time: **{0 if pd.isna(median_hours) else median_hours:.1f} hours**. "
    f"Top borough (by count): **{top_bor}**."
)

# -------------------------------
# Top complaint types
# -------------------------------
st.subheader("📊 Top Complaint Types")
st.caption("What issues are most frequently reported under the current filters?")

counts = (
    df["complaint_type"]
    .value_counts(dropna=False)
    .reset_index(name="count")
    .rename(columns={"index": "complaint_type"})
    .head(top_n)
)

# Robust narrative (never KeyErrors)
if not counts.empty:
    lead_row = counts.iloc[0]
    st.markdown(
        f"**Narrative:** **{lead_row.get('complaint_type', 'N/A')}** leads with "
        f"**{fmt_int(lead_row.get('count', 0))}** requests. "
        f"Together, the top {len(counts)} categories account for "
        f"**{fmt_int(counts['count'].sum())}** reports in the selected slice."
    )

fig_bar = px.bar(
    counts,
    x="count",
    y="complaint_type",
    orientation="h",
    color="count",
    color_continuous_scale=WARM,
    title=f"Top {len(counts)} Complaint Types",
)
fig_bar.update_layout(
    yaxis=dict(autorange="reversed", title=None),
    xaxis_title="Requests (count)",
)
fig_bar.update_traces(text=counts["count"], texttemplate="%{text:,}", textposition="outside")
st.plotly_chart(fig_bar, use_container_width=True)

# -------------------------------
# Status Breakdown (pie)
# -------------------------------
st.subheader("📈 Status Breakdown")
st.caption("How are requests currently tracked (Closed, In Progress, etc.) under the filters?")

status_counts = (
    df["status"].fillna("Unknown")
    .value_counts()
    .reset_index(name="count")
    .rename(columns={"index": "status"})
)[["status", "count"]]  # ensure unique col names & order

fig_pie = px.pie(
    status_counts,
    names="status",
    values="count",
    hole=0.55,
    color_discrete_sequence=px.colors.qualitative.Set3,
)
fig_pie.update_traces(textinfo="label+percent", pull=[0.04] * len(status_counts))
st.plotly_chart(fig_pie, use_container_width=True)

# -------------------------------
# Resolution time (boxplot)
# -------------------------------
st.subheader("⏱️ Resolution Time by Complaint Type")
st.caption("Compare how long each type of complaint typically takes to resolve (in hours).")

# Limit extreme outliers for readability (optional)
df_box = df.copy()
# Keep only finite values
df_box = df_box[np.isfinite(df_box["resolution_time"])]
fig_box = px.box(
    df_box,
    x="complaint_type",
    y="resolution_time",
    points=False,
    color="complaint_type",
    color_discrete_sequence=px.colors.qualitative.Set2,
    title="Resolution Time (hours)",
)
fig_box.update_layout(
    xaxis_title="Complaint Type",
    yaxis_title="Hours to Close",
    showlegend=False,
)
st.plotly_chart(fig_box, use_container_width=True)

# Narrative for boxplot
if not df_box.empty:
    med_by_type = (
        df_box.groupby("complaint_type")["resolution_time"]
        .median()
        .sort_values()
    )
    slowest = med_by_type.idxmax()
    fastest = med_by_type.idxmin()
    st.markdown(
        f"**Narrative:** Fastest to close (median) appears to be **{fastest}**, "
        f"while **{slowest}** tends to take the longest."
    )

# -------------------------------
# Animated bar: how requests evolve through the day
# -------------------------------
st.subheader("▶️ How do complaints evolve through the day?")
st.caption("Press **Play** to watch requests change by hour (top categories shown for clarity).")

# Focus animation on the top few complaint types for readability
top_for_anim = counts["complaint_type"].head(6).tolist()
df_anim = (
    df[df["complaint_type"].isin(top_for_anim)]
    .groupby(["hour", "complaint_type"])
    .size()
    .reset_index(name="count")
)
# ensure all hours appear even if 0
df_anim = (
    df_anim.set_index(["hour", "complaint_type"])
    .reindex(pd.MultiIndex.from_product([HOUR_ORDER, top_for_anim], names=["hour", "complaint_type"]))
    .fillna(0)
    .reset_index()
)

fig_anim = px.bar(
    df_anim,
    x="count",
    y="complaint_type",
    color="complaint_type",
    animation_frame="hour",
    category_orders={"hour": HOUR_ORDER, "complaint_type": top_for_anim},
    range_x=[0, max(1, int(df_anim["count"].max() * 1.05))],
    color_discrete_sequence=WARM,
    title="How requests evolve through the day (press ▶ to play)",
)
fig_anim.update_layout(xaxis_title="Requests (count)", yaxis_title="Complaint Type")
st.plotly_chart(fig_anim, use_container_width=True)

peak_hour = (
    df_anim.groupby("hour")["count"].sum().reindex(HOUR_ORDER, fill_value=0).idxmax()
    if not df_anim.empty else "—"
)
st.markdown(f"**Narrative:** Within these categories, overall activity peaks around **{peak_hour}:00**.")

# -------------------------------
# Heatmap (Day × Hour)
# -------------------------------
st.subheader("🔥 When are requests made? (Day × Hour)")
heat = (
    df.groupby(["day_of_week", "hour"])
    .size()
    .reset_index(name="Number of Requests")
)
if not heat.empty:
    fig_heat = px.density_heatmap(
        heat,
        x="hour",
        y="day_of_week",
        z="Number of Requests",
        category_orders={"hour": HOUR_ORDER},
        color_continuous_scale=WARM,
        title="Requests by Hour and Day",
    )
    fig_heat.update_traces(
        hovertemplate="Day: %{y}<br>Hour: %{x}:00<br>Requests: %{z}"
    )
    fig_heat.update_layout(xaxis_title="Hour (24h)", yaxis_title="Day of Week")
    st.plotly_chart(fig_heat, use_container_width=True)

# -------------------------------
# Interactive map with legend + rich popups
# -------------------------------
st.subheader("🗺️ Complaint Locations (interactive map)")
st.caption("Colors show status: 🟢 Closed, 🟠 In Progress, 🔴 Open/Other. Click a point for details.")

df_geo = df.dropna(subset=["latitude", "longitude"]).copy()
if df_geo.empty:
    st.info("No geographic coordinates available for this slice.")
else:
    # Sample up to 1500 points for performance
    df_geo = df_geo.sample(min(1500, len(df_geo)), random_state=42)

    center = [df_geo["latitude"].median(), df_geo["longitude"].median()]
    m = folium.Map(location=center, zoom_start=11, tiles=MAP_TILE)

    def status_to_color(s: str) -> str:
        if str(s).lower().strip() == "closed":
            return "green"
        if "progress" in str(s).lower():
            return "orange"
        return "red"

    for _, r in df_geo.iterrows():
        color = status_to_color(r.get("status", "Other"))
        popup = folium.Popup(
            html=(
                f"<b>Complaint:</b> {r.get('complaint_type','N/A')}<br>"
                f"<b>Status:</b> {r.get('status','N/A')}<br>"
                f"<b>Borough:</b> {r.get('borough','N/A')}<br>"
                f"<b>Created:</b> {r.get('created_date','N/A')}<br>"
                f"<b>Resolution Time:</b> "
                f"{'N/A' if pd.isna(r.get('resolution_time')) else f'{r.get('resolution_time'):.2f} h'}"
            ),
            max_width=300,
        )
        folium.CircleMarker(
            location=[r["latitude"], r["longitude"]],
            radius=4,
            color=color,
            fill=True,
            fill_opacity=0.65,
            popup=popup,
        ).add_to(m)

    # Legend
    legend_html = """
    <div style="
        position: fixed; bottom: 30px; left: 30px; z-index: 9999;
        background: white; padding: 10px 14px; border: 1px solid #999; border-radius: 6px;
        font-size: 14px; box-shadow: 0 1px 4px rgba(0,0,0,.2);
    ">
      <b>Legend</b><br>
      🟢 Closed<br>
      🟠 In Progress<br>
      🔴 Open / Other
    </div>
    """
    m.get_root().html.add_child(folium.Element(legend_html))
    st_folium(m, width=1100, height=600)

st.markdown("---")
st.caption("Tip: Adjust filters in the left panel. All narratives and visuals update instantly based on your selection.")



