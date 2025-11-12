# 311.py — NYC 311 Explorer (polished + narratives + animations + map legend)

import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
from streamlit_folium import st_folium
import folium
from folium.plugins import MarkerCluster, HeatMap

# -----------------------------------------------------------
# Page setup
# -----------------------------------------------------------
st.set_page_config(
    page_title="NYC 311 Service Requests Explorer",
    page_icon="📞",
    layout="wide",
)

TITLE = "📞 NYC 311 Service Requests Explorer"
SUB = (
    "Explore complaint types, resolution times, and closure rates by day and hour — "
    "powered by a compressed local dataset (`.csv.gz`)."
)
WARM = px.colors.sequential.OrRd  # warm palette for bars/heat
QUAL_WARM = px.colors.qualitative.Set3  # qualitative palette for categories

st.title(TITLE)
st.caption(SUB)

# -----------------------------------------------------------
# Load data
# -----------------------------------------------------------
@st.cache_data(show_spinner=True)
def load_data(path="nyc311_12months.csv.gz"):
    df = pd.read_csv(path, compression="gzip", low_memory=False)
    # Datetimes
    df["created_date"] = pd.to_datetime(df["created_date"], errors="coerce")
    df["closed_date"] = pd.to_datetime(df["closed_date"], errors="coerce")
    # Derived
    df["hours_to_close"] = (df["closed_date"] - df["created_date"]).dt.total_seconds() / 3600
    df["day_of_week"] = df["created_date"].dt.day_name()
    df["hour"] = df["created_date"].dt.hour
    # Clean borough text (some datasets have blanks)
    df["borough"] = df["borough"].fillna("Unspecified")
    return df

df = load_data()
st.success("✅ Loaded data from `nyc311_12months.csv.gz`")

# -----------------------------------------------------------
# Sidebar filters
# -----------------------------------------------------------
st.sidebar.header("Filters")

day_sel = st.sidebar.selectbox(
    "Day of Week",
    options=["All"] + sorted(df["day_of_week"].dropna().unique())
)

hr_sel = st.sidebar.slider("Hour range (24h)", 0, 23, (0, 23))

borough_all = ["All"] + sorted(df["borough"].dropna().unique())
borough_sel = st.sidebar.multiselect("Borough(s)", options=borough_all, default=["All"])

top_n = st.sidebar.slider("Top complaint types to show", 5, 30, 20)

# -----------------------------------------------------------
# Filter helper
# -----------------------------------------------------------
def apply_filters(data: pd.DataFrame) -> pd.DataFrame:
    d = data.copy()
    if day_sel != "All":
        d = d[d["day_of_week"] == day_sel]
    d = d[(d["hour"] >= hr_sel[0]) & (d["hour"] <= hr_sel[1])]
    if "All" not in borough_sel:
        d = d[d["borough"].isin(borough_sel)]
    return d

df_f = apply_filters(df)

# -----------------------------------------------------------
# KPI cards + “at a glance” narrative
# -----------------------------------------------------------
total_rows = len(df_f)
pct_closed = (df_f["status"].eq("Closed").mean() * 100.0) if total_rows else 0.0
median_hrs = df_f["hours_to_close"].median() if total_rows else np.nan
top_type = df_f["complaint_type"].mode()[0] if total_rows else "N/A"

k1, k2, k3, k4 = st.columns(4)
k1.metric("Rows (after filters)", f"{total_rows:,}")
k2.metric("% Closed", f"{pct_closed:.1f}%")
k3.metric("Median Hours to Close", f"{median_hrs:.2f}" if pd.notnull(median_hrs) else "N/A")
k4.metric("Top Complaint Type", top_type)

if total_rows:
    top3 = df_f["complaint_type"].value_counts().head(3)
    slow_type = (
        df_f.groupby("complaint_type", dropna=True)["hours_to_close"]
        .median()
        .sort_values(ascending=False)
        .head(1)
    )
    slow_name = slow_type.index[0]
    slow_val = slow_type.iloc[0]
    st.markdown(
        f"**At a glance:** Most frequent issues right now are "
        f"**{top3.index[0]}** ({top3.iloc[0]:,}), **{top3.index[1]}**, and **{top3.index[2]}**. "
        f"Overall closure rate is **{pct_closed:.1f}%** with a median resolution time of **{median_hrs:.1f} hours**. "
        f"Slowest to resolve (median) is **{slow_name}** at **{slow_val:.1f} hours**."
    )
else:
    st.info("No rows under current filters.")

st.markdown("---")

# -----------------------------------------------------------
# Top complaint types (bar)
# -----------------------------------------------------------
st.subheader("📊 Top Complaint Types")
st.caption("What issues are most frequently reported under the current filters?")

if total_rows:
    counts = df_f["complaint_type"].value_counts().reset_index()
    counts.columns = ["Complaint Type", "Count"]
    lead = counts.iloc[0] if len(counts) else None

    if lead is not None:
        st.markdown(
            f"**Narrative:** **{lead['Complaint Type']}** leads with **{lead['Count']:,}** requests."
        )

    fig_bar = px.bar(
        counts.head(top_n),
        x="Count",
        y="Complaint Type",
        orientation="h",
        text="Count",
        color="Count",
        color_continuous_scale=WARM,
        title=f"Top {min(top_n, len(counts))} Complaint Types",
    )
    fig_bar.update_layout(
        yaxis=dict(autorange="reversed", title=None),
        xaxis_title="Requests (count)",
        title_font=dict(size=18),
    )
    fig_bar.update_traces(texttemplate="%{text:,}", textposition="outside")
    st.plotly_chart(fig_bar, use_container_width=True)
else:
    st.info("No complaints to display.")

st.markdown("---")

# -----------------------------------------------------------
# Status breakdown (Pie) — fix duplicate column names
# -----------------------------------------------------------
st.subheader("📈 Status Breakdown")
st.caption("How are requests currently tracked (Closed, In Progress, etc.) under the filters?")

if total_rows and "status" in df_f:
    status_counts = (
        df_f["status"]
        .fillna("Unspecified")
        .value_counts()
        .reset_index()
        .rename(columns={"index": "Status", "status": "Count"})
    )
    # Ensure unique/clean column names (avoids narwhals DuplicateError)
    status_counts = pd.DataFrame(status_counts.loc[:, ["Status", "Count"]])

    if len(status_counts):
        lead_status = status_counts.sort_values("Count", ascending=False).iloc[0]
        st.markdown(
            f"**Narrative:** **{lead_status['Status']}** accounts for **{lead_status['Count']:,}** requests."
        )

        fig_pie = px.pie(
            status_counts,
            values="Count",
            names="Status",
            hole=0.5,
            color_discrete_sequence=QUAL_WARM,
            title="Status Breakdown",
        )
        fig_pie.update_traces(textinfo="label+percent", pull=[0.05] * len(status_counts))
        st.plotly_chart(fig_pie, use_container_width=True)
    else:
        st.info("No status data available under current filters.")
else:
    st.info("No status data available under current filters.")

st.markdown("---")

# -----------------------------------------------------------
# Resolution time by complaint type (box)
# -----------------------------------------------------------
st.subheader("⏱️ Resolution Time by Complaint Type")
st.caption("Compare how long each type of complaint typically takes to resolve.")

if total_rows:
    fig_box = px.box(
        df_f.dropna(subset=["hours_to_close"]),
        x="complaint_type",
        y="hours_to_close",
        color="complaint_type",
        points=False,
        title="Resolution Time (hours)",
    )
    fig_box.update_layout(
        xaxis=dict(title=None, tickangle=45),
        yaxis_title="Hours to Close",
        showlegend=False,
        title_font=dict(size=18),
    )
    st.plotly_chart(fig_box, use_container_width=True)
else:
    st.info("No resolution time data under current filters.")

st.markdown("---")

# -----------------------------------------------------------
# Heatmap (Day × Hour)
# -----------------------------------------------------------
st.subheader("🔥 When Are Requests Made?")
st.caption("Heatmap of request intensity by hour & weekday (hover shows **Number of requests**).")

if total_rows:
    heat = (
        df_f.groupby(["day_of_week", "hour"])
        .size()
        .reset_index(name="Number of requests")
    )
    fig_heat = px.density_heatmap(
        heat, x="hour", y="day_of_week", z="Number of requests",
        color_continuous_scale=WARM, title="Requests by Hour and Day",
    )
    fig_heat.update_traces(hovertemplate="Hour %{x}:00<br>Day: %{y}<br>Requests: %{z}")
    fig_heat.update_layout(
        xaxis_title="Hour of Day (24h)",
        yaxis_title="Day of Week",
        title_font=dict(size=18),
    )
    st.plotly_chart(fig_heat, use_container_width=True)

st.markdown("---")

# -----------------------------------------------------------
# Animated bar race (complaints by hour) — warm colors
# -----------------------------------------------------------
st.subheader("▶️ How do complaints evolve through the day?")
st.caption("Press **Play** to watch request counts change by hour (top categories shown for clarity).")

if total_rows:
    # Aggregate by hour & type
    hr_type = df_f.groupby(["hour", "complaint_type"]).size().reset_index(name="Count")
    # Keep a stable top-K set (by total across hours) so animation isn't noisy
    top_overall = (
        hr_type.groupby("complaint_type")["Count"].sum().sort_values(ascending=False).head(6).index
    )
    hr_type = hr_type[hr_type["complaint_type"].isin(top_overall)]

    # Ensure order for bars (largest on top)
    latest_hour = int(hr_type["hour"].max()) if len(hr_type) else 0
    order_now = (
        hr_type[hr_type["hour"] == latest_hour]
        .sort_values("Count", ascending=False)["complaint_type"]
        .tolist()
    )

    fig_race = px.bar(
        hr_type.sort_values("Count"),
        x="Count",
        y="complaint_type",
        color="complaint_type",
        animation_frame="hour",
        orientation="h",
        color_discrete_sequence=WARM,
        title="How requests evolve through the day (press ► to play)",
        category_orders={"complaint_type": order_now},
    )
    fig_race.update_layout(
        yaxis_title="Complaint Type",
        xaxis_title="Requests (count)",
        title_font=dict(size=18),
        showlegend=False,
        transition={"duration": 400},
    )
    st.plotly_chart(fig_race, use_container_width=True)

st.markdown("---")

# -----------------------------------------------------------
# Geographic map — markers + cluster + legend + insights
# -----------------------------------------------------------
st.subheader("🗺️ Complaint Hotspots Across NYC")
st.caption("Zoom & hover to explore; markers are colored by **status**. Click a marker for details.")

def status_color(s: str) -> str:
    s = (s or "").lower()
    if "closed" in s:
        return "#2ca25f"   # green
    if "progress" in s:
        return "#fb6a4a"   # orange/red
    if "open" in s:
        return "#ef3b2c"   # red
    return "#9e9ac8"       # neutral purple

if total_rows and {"latitude", "longitude"}.issubset(df_f.columns):
    # Sample for performance
    sample = df_f.dropna(subset=["latitude", "longitude"]).sample(min(2000, len(df_f)), random_state=1)

    m = folium.Map(location=[40.7128, -74.0060], zoom_start=11, tiles="cartodbpositron")
    cluster = MarkerCluster().add_to(m)

    for _, r in sample.iterrows():
        col = status_color(str(r.get("status", "")))
        popup = folium.Popup(
            html=(
                f"<b>Complaint:</b> {r.get('complaint_type','N/A')}<br>"
                f"<b>Status:</b> {r.get('status','N/A')}<br>"
                f"<b>Hours to close:</b> {('%.2f' % r.get('hours_to_close')) if pd.notnull(r.get('hours_to_close')) else 'N/A'}<br>"
                f"<b>Borough:</b> {r.get('borough','N/A')}<br>"
                f"<b>Created:</b> {r.get('created_date')}"
            ),
            max_width=300,
        )
        tooltip = (
            f"{r.get('complaint_type','N/A')} • {r.get('borough','N/A')} • "
            f"{r.get('status','N/A')}"
        )
        folium.CircleMarker(
            location=[r["latitude"], r["longitude"]],
            radius=4, color=col, fill=True, fill_opacity=0.7,
            popup=popup, tooltip=tooltip
        ).add_to(cluster)

    # Optional heat layer for density
    heat_data = sample[["latitude", "longitude"]].values.tolist()
    HeatMap(heat_data, radius=12, blur=20, name="Density heat").add_to(m)
    folium.LayerControl(collapsed=False).add_to(m)

    # Legend (custom HTML)
    legend_html = """
    <div style="
        position: fixed; 
        bottom: 40px; left: 40px; z-index: 9999; 
        background: white; padding: 10px 12px; border: 1px solid #ccc; border-radius: 8px;
        box-shadow: 0 2px 6px rgba(0,0,0,.15); font-size: 13px;">
      <b>Legend</b><br>
      <span style="display:inline-block;width:12px;height:12px;background:#2ca25f;border-radius:50%;margin-right:6px;"></span> Closed<br>
      <span style="display:inline-block;width:12px;height:12px;background:#fb6a4a;border-radius:50%;margin-right:6px;"></span> In Progress<br>
      <span style="display:inline-block;width:12px;height:12px;background:#ef3b2c;border-radius:50%;margin-right:6px;"></span> Open<br>
      <span style="display:inline-block;width:12px;height:12px;background:#9e9ac8;border-radius:50%;margin-right:6px;"></span> Other/Unspecified
    </div>
    """
    m.get_root().html.add_child(folium.Element(legend_html))
    st_folium(m, height=620, width=None)
else:
    st.info("No geographic coordinates available under current filters.")

st.markdown("---")
st.caption("Tip: The runner icon (🏃) in the header just means the app is re-running to reflect your filters — it’s normal.")


