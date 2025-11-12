import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
from streamlit_folium import st_folium
import folium

# ===================
# PAGE SETUP
# ===================
st.set_page_config(
    page_title="NYC 311 Service Requests Explorer",
    layout="wide",
    page_icon="📞",
)

st.title("📞 NYC 311 Service Requests Explorer")
st.caption(
    "Explore complaint types, resolution times, and closure rates by day and hour — powered by a compressed local dataset (.csv.gz)."
)

# ===================
# LOAD DATA
# ===================
@st.cache_data
def load_data():
    df = pd.read_csv("nyc311_12months.csv.gz", compression="gzip", low_memory=False)
    df["created_date"] = pd.to_datetime(df["created_date"], errors="coerce")
    df["closed_date"] = pd.to_datetime(df["closed_date"], errors="coerce")
    df["hours_to_close"] = (
        (df["closed_date"] - df["created_date"]).dt.total_seconds() / 3600
    )
    df["hour"] = df["created_date"].dt.hour
    df["day_of_week"] = df["created_date"].dt.day_name()
    return df

df = load_data()
st.success("✅ Loaded data from `nyc311_12months.csv.gz`")

# ===================
# SIDEBAR FILTERS
# ===================
st.sidebar.header("Filters")

days = ["All"] + sorted(df["day_of_week"].dropna().unique())
day_filter = st.sidebar.selectbox("Day of Week", days)

hour_range = st.sidebar.slider("Hour range (24h)", 0, 23, (0, 23))
boroughs = ["All"] + sorted(df["borough"].dropna().unique())
borough_filter = st.sidebar.multiselect("Borough(s)", boroughs, default=["All"])

top_n = st.sidebar.slider("Top complaint types to show", 5, 30, 20)

# ===================
# FILTER DATA
# ===================
df_f = df.copy()
if day_filter != "All":
    df_f = df_f[df_f["day_of_week"] == day_filter]
df_f = df_f[(df_f["hour"] >= hour_range[0]) & (df_f["hour"] <= hour_range[1])]
if "All" not in borough_filter:
    df_f = df_f[df_f["borough"].isin(borough_filter)]

# ===================
# KPI METRICS
# ===================
total_rows = len(df_f)
pct_closed = df_f["status"].eq("Closed").mean() * 100 if "status" in df_f else np.nan
median_time = df_f["hours_to_close"].median()
top_type = df_f["complaint_type"].mode()[0] if not df_f.empty else "N/A"

col1, col2, col3, col4 = st.columns(4)
col1.metric("Rows (after filters)", f"{total_rows:,}")
col2.metric("% Closed", f"{pct_closed:.1f}%")
col3.metric("Median Hours to Close", f"{median_time:.2f}")
col4.metric("Top Complaint Type", top_type)

# ===================
# NARRATIVE
# ===================
if not df_f.empty:
    top_complaints = df_f["complaint_type"].value_counts().head(3)
    narrative = (
        f"**At a glance:** Most frequent issues are **{top_complaints.index[0]}** "
        f"({top_complaints.iloc[0]:,} reports), followed by **{top_complaints.index[1]}** "
        f"and **{top_complaints.index[2]}**. "
        f"The median resolution time is about **{median_time:.1f} hours**, with "
        f"a closure rate of **{pct_closed:.1f}%**."
    )
    st.markdown(narrative)
else:
    st.warning("No data available for selected filters.")

# ===================
# TOP COMPLAINT TYPES
# ===================
st.subheader("📊 Top Complaint Types")
st.caption("What issues are most frequently reported under the current filters?")

if not df_f.empty:
    counts = (
        df_f["complaint_type"].value_counts().reset_index().head(top_n)
    )
    counts.columns = ["Complaint Type", "Count"]

    fig_bar = px.bar(
        counts,
        x="Count",
        y="Complaint Type",
        orientation="h",
        text="Count",
        color="Count",
        color_continuous_scale="YlOrRd",
        title=f"Top {top_n} Complaint Types",
    )
    fig_bar.update_layout(
        yaxis=dict(autorange="reversed", title=None),
        xaxis_title="Requests (count)",
        title_font=dict(size=18),
    )
    fig_bar.update_traces(texttemplate="%{text:,}", textposition="outside")
    st.plotly_chart(fig_bar, use_container_width=True)
else:
    st.info("No complaints to display for selected filters.")

# ===================
# STATUS PIE CHART
# ===================
if "status" in df_f:
    st.subheader("📈 Status Breakdown")
    status_counts = (
        df_f["status"].value_counts().reset_index().rename(columns={"index": "status", "status": "count"})
    ).drop_duplicates()
    fig_pie = px.pie(
        status_counts,
        values="count",
        names="status",
        hole=0.5,
        color_discrete_sequence=px.colors.qualitative.Set3,
    )
    fig_pie.update_traces(textinfo="label+percent", pull=[0.05]*len(status_counts))
    st.plotly_chart(fig_pie, use_container_width=True)

# ===================
# RESOLUTION TIME BY TYPE
# ===================
st.subheader("⏱️ Resolution Time by Complaint Type")
st.caption("Compare how long each type of complaint typically takes to resolve.")

if not df_f.empty:
    fig_box = px.box(
        df_f,
        x="complaint_type",
        y="hours_to_close",
        points=False,
        color="complaint_type",
        title="Resolution Time (hours)",
    )
    fig_box.update_layout(
        xaxis=dict(showticklabels=True, tickangle=45, title=None),
        yaxis_title="Hours to Close",
        showlegend=False,
        title_font=dict(size=18),
    )
    st.plotly_chart(fig_box, use_container_width=True)

# ===================
# HEATMAP (Day × Hour)
# ===================
st.subheader("🔥 When Are Requests Made?")
st.caption("Interactive heatmap showing request patterns by hour and day of week.")

heat = (
    df_f.groupby(["day_of_week", "hour"])
    .size()
    .reset_index(name="Number of Requests")
)
if not heat.empty:
    fig_heat = px.density_heatmap(
        heat,
        x="hour",
        y="day_of_week",
        z="Number of Requests",
        color_continuous_scale="YlOrRd",
        title="Requests by Hour and Day",
    )
    fig_heat.update_traces(hovertemplate="Hour %{x}:00<br>Day: %{y}<br>Requests: %{z}")
    fig_heat.update_layout(
        xaxis_title="Hour of Day (24h)",
        yaxis_title="Day of Week",
        title_font=dict(size=18),
    )
    st.plotly_chart(fig_heat, use_container_width=True)

# ===================
# ANIMATED BUBBLE CHART
# ===================
st.subheader("🎬 Complaint Activity Over Time")
st.caption("Animated bubble chart showing complaint growth throughout the day.")

if not df_f.empty:
    df_anim = (
        df_f.groupby(["hour", "complaint_type"])
        .size()
        .reset_index(name="Requests")
    )
    fig_bubble = px.scatter(
        df_anim,
        x="hour",
        y="complaint_type",
        size="Requests",
        color="complaint_type",
        animation_frame="hour",
        size_max=60,
        title="Complaints Over the Day (Animated)",
    )
    fig_bubble.update_layout(
        xaxis_title="Hour of Day",
        yaxis_title=None,
        showlegend=False,
        title_font=dict(size=18),
    )
    st.plotly_chart(fig_bubble, use_container_width=True)

# ===================
# GEOGRAPHIC MAP (Folium)
# ===================
st.subheader("🗺️ Complaint Hotspots Across NYC")
st.caption("Explore where complaints are concentrated geographically.")

if not df_f.empty and {"latitude", "longitude"}.issubset(df_f.columns):
    m = folium.Map(location=[40.7128, -74.0060], zoom_start=11)
    for _, row in df_f.sample(min(500, len(df_f))).iterrows():
        popup_text = (
            f"<b>{row['complaint_type']}</b><br>"
            f"Status: {row.get('status', 'Unknown')}<br>"
            f"Hours to Close: {row.get('hours_to_close', 'N/A'):.2f}"
        )
        folium.CircleMarker(
            location=[row["latitude"], row["longitude"]],
            radius=3,
            color="crimson" if row.get("status") != "Closed" else "green",
            fill=True,
            fill_opacity=0.6,
            popup=popup_text,
        ).add_to(m)
    st_folium(m, width=1200, height=600)
else:
    st.info("No geographic coordinates available in this dataset.")

st.markdown("---")
st.caption("Tip: Use filters on the left to focus by day, hour, and borough. Charts update instantly on your compressed dataset.")
