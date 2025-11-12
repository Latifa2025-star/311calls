# ================================
# NYC 311 Interactive Explorer App
# ================================
import streamlit as st
import pandas as pd
import plotly.express as px

# App configuration
st.set_page_config(
    page_title="NYC 311 Explorer",
    page_icon="📞",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.title("📞 NYC 311 Service Requests Explorer")
st.markdown("#### Explore complaint types, resolution times, and closure rates by day and hour — powered by real NYC Open Data.")

# ---- Load your data ----
@st.cache_data
def load_data():
    # Load your processed 12-month sample
    df = pd.read_csv("nyc311_12months.csv")
    df["created_date"] = pd.to_datetime(df["created_date"], errors="coerce")
    df["closed_date"] = pd.to_datetime(df["closed_date"], errors="coerce")
    df["day_of_week"] = df["created_date"].dt.day_name()
    df["hour"] = df["created_date"].dt.hour
    df["is_closed"] = df["status"].str.lower().str.contains("closed")
    return df

df = load_data()

# ---- Sidebar filters ----
st.sidebar.header("🎛️ Filters")

day_filter = st.sidebar.selectbox(
    "Select Day of Week:",
    ["All"] + list(df["day_of_week"].dropna().unique())
)

hour_filter = st.sidebar.slider("Select Hour Range:", 0, 23, (0, 23))
top_n = st.sidebar.slider("Show Top Complaint Types:", 5, 20, 10)

# ---- Apply filters ----
filtered = df.copy()
if day_filter != "All":
    filtered = filtered[filtered["day_of_week"] == day_filter]

filtered = filtered[
    (filtered["hour"] >= hour_filter[0]) & (filtered["hour"] <= hour_filter[1])
]

# ---- Metrics ----
st.markdown("### 📊 Overview Metrics")

col1, col2, col3 = st.columns(3)
col1.metric("Rows", f"{len(filtered):,}")
closed_pct = (filtered["is_closed"].mean() * 100) if len(filtered) > 0 else 0
col2.metric("% Closed", f"{closed_pct:.1f}%")
median_hours = filtered["hours_to_close"].median() if "hours_to_close" in filtered else None
col3.metric("Median Hours to Close", f"{median_hours:.2f}" if median_hours else "N/A")

# ---- Top Complaint Types ----
st.markdown("### 🔝 Top Complaint Types")

top_types = (
    filtered["complaint_type"]
    .value_counts()
    .nlargest(top_n)
    .reset_index()
    .rename(columns={"index": "Complaint Type", "complaint_type": "Count"})
)

fig_bar = px.bar(
    top_types,
    x="Count",
    y="Complaint Type",
    orientation="h",
    color="Count",
    color_continuous_scale="sunsetdark",
    title=f"Top {top_n} Complaint Types — NYC 311 ({day_filter if day_filter!='All' else 'All Days'})",
)
fig_bar.update_layout(
    height=500,
    xaxis_title="Number of Requests",
    yaxis_title=None,
    yaxis=dict(autorange="reversed"),
    title_font=dict(size=22, family="Arial Black"),
    coloraxis_showscale=False,
)
st.plotly_chart(fig_bar, use_container_width=True)

# ---- Complaint Duration Scatter ----
st.markdown("### ⏱️ Resolution Time by Complaint Type")

if "hours_to_close" in filtered.columns:
    fig_scatter = px.scatter(
        filtered,
        x="complaint_type",
        y="hours_to_close",
        color="status",
        hover_data=["descriptor", "borough", "agency_name"],
        color_discrete_sequence=px.colors.qualitative.Vivid,
        title="Complaint Duration & Status",
    )
    fig_scatter.update_layout(
        xaxis_title="Complaint Type",
        yaxis_title="Hours to Close",
        height=550,
        title_font=dict(size=22, family="Arial Black"),
        margin=dict(t=50, b=50),
    )
    st.plotly_chart(fig_scatter, use_container_width=True)

# ---- Map of Complaints ----
st.markdown("### 🗺️ Geographic Distribution")

if {"latitude", "longitude"}.issubset(filtered.columns):
    fig_map = px.density_mapbox(
        filtered.dropna(subset=["latitude", "longitude"]),
        lat="latitude",
        lon="longitude",
        z=None,
        radius=7,
        hover_name="complaint_type",
        color_continuous_scale="Inferno",
        mapbox_style="carto-positron",
        zoom=9,
        opacity=0.7,
        title="Complaint Density Across NYC",
    )
    fig_map.update_layout(height=600, margin=dict(t=60, b=0))
    st.plotly_chart(fig_map, use_container_width=True)



