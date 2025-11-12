import streamlit as st
import pandas as pd
import plotly.express as px
import folium
from streamlit_folium import st_folium

st.set_page_config(page_title="NYC 311 Explorer", layout="wide")

@st.cache_data
def load_data():
    df = pd.read_csv("nyc311_12months.csv.gz", compression="gzip", low_memory=False)
    df['created_date'] = pd.to_datetime(df['created_date'], errors='coerce')
    df['closed_date'] = pd.to_datetime(df['closed_date'], errors='coerce')
    df['hour'] = df['created_date'].dt.hour
    df['day_of_week'] = df['created_date'].dt.day_name()
    df['resolution_time'] = (df['closed_date'] - df['created_date']).dt.total_seconds() / 3600
    df = df.dropna(subset=['complaint_type'])
    return df

df = load_data()

st.title("📞 NYC 311 Service Requests Explorer")

# Filters
col1, col2, col3 = st.sidebar.columns(1)
day = st.sidebar.selectbox("Day of Week", ["All"] + list(df['day_of_week'].unique()))
hour_range = st.sidebar.slider("Hour range (24h)", 0, 23, (0, 23))
boroughs = st.sidebar.multiselect("Borough(s)", df['borough'].dropna().unique(), default=df['borough'].dropna().unique())
top_n = st.sidebar.slider("Top complaint types to show", 5, 30, 10)

filtered = df[
    (df['hour'].between(hour_range[0], hour_range[1])) &
    (df['borough'].isin(boroughs)) &
    ((df['day_of_week'] == day) if day != "All" else True)
]

# Summary stats
total_rows = len(filtered)
pct_closed = (filtered['status'] == 'Closed').mean() * 100
median_hours = filtered['resolution_time'].median()
top_type = filtered['complaint_type'].value_counts().idxmax()

st.markdown(f"**Rows (after filters):** {total_rows:,}  **% Closed:** {pct_closed:.1f}%  **Median Hours to Close:** {median_hours:.2f}  **Top Complaint Type:** {top_type}")

# Top Complaints
st.subheader("📊 Top Complaint Types")
counts = filtered['complaint_type'].value_counts().reset_index()
counts.columns = ['complaint_type', 'count']
counts = counts.head(top_n)

lead = counts.iloc[0]
st.markdown(
    f"**Narrative:** The leading issue is **{lead['complaint_type']}** "
    f"with **{lead['count']:,} reports**, showing that it’s the most frequent concern under current filters."
)

fig_bar = px.bar(
    counts,
    x="count", y="complaint_type",
    orientation="h",
    title=f"Top {top_n} Complaint Types",
    color="count",
    color_continuous_scale=px.colors.sequential.OrRd_r
)
st.plotly_chart(fig_bar, use_container_width=True)

# Status Breakdown
st.subheader("📈 Status Breakdown")
status_counts = filtered['status'].value_counts().reset_index()
status_counts.columns = ['status', 'count']

fig_pie = px.pie(status_counts, names="status", values="count", hole=0.5,
                 color_discrete_sequence=px.colors.qualitative.Set3)
st.plotly_chart(fig_pie, use_container_width=True)

# Animated complaints by hour
st.subheader("▶️ How do complaints evolve through the day?")
hourly = filtered.groupby(['hour', 'complaint_type']).size().reset_index(name='count')
fig_anim = px.bar(
    hourly,
    x="count", y="complaint_type",
    color="complaint_type",
    animation_frame="hour",
    range_x=[0, hourly['count'].max()],
    title="How requests evolve through the day (press ▶ to play)",
    color_discrete_sequence=px.colors.sequential.OrRd_r
)
fig_anim.update_layout(xaxis_title="Requests (count)", yaxis_title="Complaint Type")
st.plotly_chart(fig_anim, use_container_width=True)

peak_hour = hourly.groupby('hour')['count'].sum().idxmax()
st.markdown(f"**Narrative:** Complaint peaks typically occur around **{peak_hour}:00** hours.")

# Resolution Time by Complaint
st.subheader("⏱️ Resolution Time by Complaint Type")
fig_box = px.box(
    filtered, x="complaint_type", y="resolution_time", points="all",
    color="complaint_type", title="Resolution Time (hours)"
)
fig_box.update_layout(xaxis_title="Complaint Type", yaxis_title="Hours to Close")
st.plotly_chart(fig_box, use_container_width=True)

# Interactive Map
st.subheader("🗺️ Complaint Locations (Interactive Map)")
sample = filtered.dropna(subset=['latitude', 'longitude']).sample(min(1000, len(filtered)))
map_center = [sample['latitude'].median(), sample['longitude'].median()]

m = folium.Map(location=map_center, zoom_start=11, tiles="cartodbpositron")
for _, row in sample.iterrows():
    color = "green" if row['status'] == "Closed" else ("orange" if "Progress" in row['status'] else "red")
    popup_text = f"""
    <b>Complaint:</b> {row['complaint_type']}<br>
    <b>Status:</b> {row['status']}<br>
    <b>Borough:</b> {row['borough']}<br>
    <b>Created:</b> {row['created_date']}<br>
    <b>Resolution Time:</b> {row['resolution_time']:.2f} hours
    """
    folium.CircleMarker(
        location=[row['latitude'], row['longitude']],
        radius=5, color=color, fill=True, fill_opacity=0.6,
        popup=popup_text
    ).add_to(m)

legend_html = """
<div style="position: fixed; bottom: 40px; left: 40px; width: 180px; height: 110px;
background-color: white; border:2px solid grey; z-index:9999; font-size:14px; padding:10px;">
<b>Legend</b><br>
🟢 Closed<br>🟠 In Progress<br>🔴 Open
</div>
"""
m.get_root().html.add_child(folium.Element(legend_html))

st_folium(m, width=1100, height=600)


