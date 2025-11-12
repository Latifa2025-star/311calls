import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
from folium import Map, CircleMarker, LayerControl
from folium.plugins import MarkerCluster
from streamlit_folium import st_folium

# ----------------------------
# Page config
# ----------------------------
st.set_page_config(
    page_title="NYC 311 Service Requests Explorer",
    page_icon="📞",
    layout="wide",
)
st.markdown(
    "<style> .smallcaps{font-variant-caps: all-small-caps;} .muted{color:#6b7280;} </style>",
    unsafe_allow_html=True,
)

st.title("📞 NYC 311 Service Requests Explorer")
st.caption(
    "Explore complaint types, resolution times, and closure rates by day and hour — powered by a compressed local dataset (.csv.gz)."
)

# ----------------------------
# Load data (cached)
# ----------------------------
@st.cache_data(show_spinner=True)
def load_data():
    df = pd.read_csv("nyc311_12months.csv.gz", compression="gzip", low_memory=False)
    # required fields
    for col in ["created_date", "closed_date"]:
        if col in df:
            df[col] = pd.to_datetime(df[col], errors="coerce")

    if {"created_date", "closed_date"}.issubset(df.columns):
        hrs = (df["closed_date"] - df["created_date"]).dt.total_seconds() / 3600
        df["hours_to_close"] = hrs
    else:
        df["hours_to_close"] = np.nan

    df["day_of_week"] = df["created_date"].dt.day_name()
    df["hour"] = df["created_date"].dt.hour
    # normalize status a bit
    if "status" in df:
        df["status"] = df["status"].astype(str).str.strip().str.title()
    if "borough" in df:
        df["borough"] = df["borough"].astype(str).str.strip().str.upper()

    return df

df = load_data()
st.success(f"Loaded data from `nyc311_12months.csv.gz`  •  Rows: {len(df):,}")

# ----------------------------
# Sidebar filters
# ----------------------------
st.sidebar.header("Filters")

# Day filter
day_options = ["All"] + sorted(df["day_of_week"].dropna().unique().tolist())
day_filter = st.sidebar.selectbox("Day of Week", day_options, index=0)

# Hour range
hour_min, hour_max = st.sidebar.slider("Hour range (24h)", 0, 23, (0, 23))

# Boroughs
borough_options = ["All"] + sorted([b for b in df["borough"].dropna().unique() if b != "UNSPECIFIED"])
borough_select = st.sidebar.multiselect("Borough(s)", borough_options, default=["All"])

# Top N for charts
top_n = st.sidebar.slider("Top complaint types to show", 5, 30, 20)

# ----------------------------
# Apply filters
# ----------------------------
df_f = df.copy()

if day_filter != "All":
    df_f = df_f[df_f["day_of_week"] == day_filter]

df_f = df_f[(df_f["hour"] >= hour_min) & (df_f["hour"] <= hour_max)]

if len(borough_select) > 0 and "All" not in borough_select:
    df_f = df_f[df_f["borough"].isin(borough_select)]

# ----------------------------
# KPIs
# ----------------------------
c1, c2, c3, c4 = st.columns(4)

rows_after = len(df_f)
pct_closed = (
    df_f["status"].eq("Closed").mean() * 100 if "status" in df_f and rows_after else np.nan
)
median_hours = (
    float(np.nanmedian(df_f["hours_to_close"])) if rows_after else np.nan
)
top_type = df_f["complaint_type"].mode()[0] if rows_after else "N/A"

c1.metric("Rows (after filters)", f"{rows_after:,}")
c2.metric("% Closed", "N/A" if np.isnan(pct_closed) else f"{pct_closed:.1f}%")
c3.metric("Median Hours to Close", "N/A" if np.isnan(median_hours) else f"{median_hours:.2f}")
c4.metric("Top Complaint Type", top_type)

# High-level narrative
if rows_after:
    top3 = df_f["complaint_type"].value_counts().head(3)
    top3_text = ", ".join([f"**{i}** ({v:,})" for i, v in top3.items()])
    st.markdown(
        f"**At a glance:** Most common issues under current filters are {top3_text}. "
        f"Median time to close is **{0 if np.isnan(median_hours) else median_hours:.1f} hours**, "
        f"and **{0 if np.isnan(pct_closed) else pct_closed:.1f}%** of requests are closed."
    )
else:
    st.warning("No data for the selected filters.")

st.markdown("---")

# ----------------------------
# Top Complaint Types (bar)
# ----------------------------
st.subheader("📊 Top Complaint Types")
st.caption("What issues are most frequently reported under the current filters?")
if rows_after:
    counts = df_f["complaint_type"].value_counts().reset_index()
    counts.columns = ["Complaint Type", "Count"]
    counts = counts.head(top_n)

    # narrative for this chart
    lead_row = counts.iloc[0] if len(counts) else None
    if lead_row is not None:
        st.markdown(
            f"_Narrative:_ **{lead_row['Complaint Type']}** leads with **{lead_row['Count']:,}** requests."
        )

    fig_bar = px.bar(
        counts,
        x="Count",
        y="Complaint Type",
        orientation="h",
        text="Count",
        color="Count",
        color_continuous_scale="YlOrRd",
        title=f"Top {min(top_n, len(counts))} Complaint Types",
    )
    fig_bar.update_layout(
        yaxis=dict(autorange="reversed", title=None),
        xaxis_title="Requests (count)",
        title_font=dict(size=18),
        margin=dict(l=10, r=10, t=60, b=10),
    )
    fig_bar.update_traces(texttemplate="%{text:,}", textposition="outside", cliponaxis=False)
    st.plotly_chart(fig_bar, use_container_width=True)
else:
    st.info("No complaints to display.")

# ----------------------------
# Status Breakdown — fixes DuplicateError
# ----------------------------
if rows_after and "status" in df_f:
    st.subheader("📈 Status Breakdown")
    sc = (
        df_f["status"]
        .fillna("Unspecified")
        .value_counts(dropna=False)
        .rename_axis("Status")
        .reset_index(name="Count")
    )
    # Unique, ordered labels
    sc = sc.groupby("Status", as_index=False)["Count"].sum()

    # narrative
    biggest = sc.sort_values("Count", ascending=False).iloc[0]
    st.markdown(
        f"_Narrative:_ **{biggest['Status']}** represents **{biggest['Count']:,}** requests "
        f"({biggest['Count'] / max(1, sc['Count'].sum()):.1%} of filtered data)."
    )

    fig_pie = px.pie(
        sc,
        values="Count",
        names="Status",
        hole=0.5,
        color_discrete_sequence=px.colors.qualitative.Set3,
    )
    fig_pie.update_traces(textinfo="label+percent", pull=[0.05] * len(sc))
    fig_pie.update_layout(margin=dict(l=0, r=0, t=20, b=0))
    st.plotly_chart(fig_pie, use_container_width=True)

st.markdown("---")

# ----------------------------
# Resolution Time (box, outlier-clipped); bigger, clear labels
# ----------------------------
st.subheader("⏱️ Resolution Time by Complaint Type")
st.caption("Compare how long each type of complaint typically takes to resolve.")

if rows_after and "hours_to_close" in df_f:
    # clip outliers for readability
    s = df_f["hours_to_close"].copy()
    s = s.mask(s < 0, np.nan)  # drop negatives
    hi = np.nanpercentile(s, 99.5) if s.notna().any() else np.nan
    df_box = df_f.copy()
    if not np.isnan(hi):
        df_box["hours_to_close"] = df_box["hours_to_close"].clip(upper=hi)

    fig_box = px.box(
        df_box.dropna(subset=["hours_to_close"]),
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
        margin=dict(l=10, r=10, t=60, b=0),
    )
    st.plotly_chart(fig_box, use_container_width=True)

    st.markdown(
        "_Narrative:_ Boxes show the middle 50% of times; whiskers show spread. "
        "Tall boxes indicate more variability in closure time for that complaint."
    )

st.markdown("---")

# ----------------------------
# Heatmap (Day × Hour) with meaningful hover label
# ----------------------------
st.subheader("🔥 When are requests made?")
st.caption("Heatmap of requests by hour and day of week.")

if rows_after:
    # order days
    day_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    heat = (
        df_f.groupby(["day_of_week", "hour"])
        .size()
        .reset_index(name="Number of Requests")
    )
    # keep only known days in order
    heat = heat[heat["day_of_week"].isin(day_order)]
    heat["day_of_week"] = pd.Categorical(heat["day_of_week"], categories=day_order, ordered=True)

    fig_heat = px.density_heatmap(
        heat,
        x="hour",
        y="day_of_week",
        z="Number of Requests",
        color_continuous_scale="YlOrRd",
        nbinsx=24,
        title="Requests by Hour and Day",
    )
    fig_heat.update_traces(
        hovertemplate="Hour %{x}:00<br>Day: %{y}<br>Requests: %{z:,}<extra></extra>"
    )
    fig_heat.update_layout(
        xaxis_title="Hour of Day (24h)",
        yaxis_title="Day of Week",
        title_font=dict(size=18),
        margin=dict(l=10, r=10, t=60, b=10),
    )
    st.plotly_chart(fig_heat, use_container_width=True)

    # narrative
    if len(heat):
        peak = heat.sort_values("Number of Requests", ascending=False).iloc[0]
        st.markdown(
            f"_Narrative:_ Peak activity is at **{int(peak['hour']):02d}:00 on {peak['day_of_week']}**, "
            f"with **{int(peak['Number of Requests']):,}** requests."
        )

st.markdown("---")

# ----------------------------
# Animated bar race (back, clean & smooth)
# ----------------------------
st.subheader("▶️ How do complaints evolve through the day?")
st.caption("Press **Play** to watch requests change by hour (top categories are shown for clarity).")

if rows_after:
    # choose the top K complaint types overall in filtered data
    topK_types = df_f["complaint_type"].value_counts().head(6).index.tolist()
    race = (
        df_f[df_f["complaint_type"].isin(topK_types)]
        .groupby(["hour", "complaint_type"])
        .size()
        .reset_index(name="Requests")
        .sort_values(["hour", "Requests"], ascending=[True, False])
    )

    # range for x so it doesn't jump
    x_max = max(100, race["Requests"].max()) if len(race) else 100

    fig_race = px.bar(
        race,
        x="Requests",
        y="complaint_type",
        orientation="h",
        animation_frame="hour",
        color="complaint_type",
        range_x=[0, x_max * 1.15],
        title="How requests evolve through the day (press ▶ to play)",
    )
    fig_race.update_layout(
        yaxis=dict(title="Complaint Type"),
        xaxis_title="Requests (count)",
        title_font=dict(size=18),
        margin=dict(l=10, r=10, t=60, b=10),
        showlegend=False,
    )
    st.plotly_chart(fig_race, use_container_width=True)

    # narrative
    if len(race):
        at_peak = race.sort_values("Requests", ascending=False).iloc[0]
        st.markdown(
            f"_Narrative:_ At **{int(at_peak['hour']):02d}:00**, "
            f"**{at_peak['complaint_type']}** leads with **{int(at_peak['Requests']):,}** requests."
        )

st.markdown("---")

# ----------------------------
# Geographical map with legend + clustering
# ----------------------------
st.subheader("🗺️ Complaint Hotspots Across NYC")
st.caption("Circle color shows status: **Green = Closed**, **Red = Not Closed**. Hover for details.")

if rows_after and {"latitude", "longitude"}.issubset(df_f.columns):
    # sample to keep the map responsive
    sample = df_f.dropna(subset=["latitude", "longitude"]).sample(
        n=min(1500, len(df_f)), random_state=42
    )

    m = Map(location=[40.7128, -74.0060], zoom_start=11, tiles="cartodbpositron")
    cluster = MarkerCluster().add_to(m)

    def color_for_status(s):
        return "green" if str(s).strip().lower() == "closed" else "red"

    for _, r in sample.iterrows():
        color = color_for_status(r.get("status", ""))
        popup = (
            f"<b>{r.get('complaint_type','N/A')}</b><br>"
            f"Borough: {r.get('borough','N/A')}<br>"
            f"Status: {r.get('status','N/A')}<br>"
            f"Hours to Close: {'' if pd.isna(r.get('hours_to_close')) else round(float(r['hours_to_close']),2)}"
        )
        CircleMarker(
            location=[float(r["latitude"]), float(r["longitude"])],
            radius=4,
            color=color,
            fill=True,
            fill_opacity=0.7,
            popup=popup,
        ).add_to(cluster)

    # Add a simple legend
    legend_html = """
    <div style="
        position: fixed; 
        bottom: 30px; left: 30px; z-index: 9999; 
        background: white; padding: 10px 14px; border:1px solid #ccc; border-radius:8px;">
      <b>Legend</b><br>
      <span style="display:inline-block;width:12px;height:12px;background:green;border-radius:50%;margin-right:6px;"></span> Closed<br>
      <span style="display:inline-block;width:12px;height:12px;background:red;border-radius:50%;margin-right:6px;"></span> Not Closed
    </div>
    """
    st_folium(m, width=1200, height=640)
    st.markdown(legend_html, unsafe_allow_html=True)

    # narrative: borough with most points on map sample
    if "borough" in sample:
        hot = sample["borough"].value_counts().idxmax()
        st.markdown(f"_Narrative:_ Most mapped complaints are in **{hot.title()}**.")
else:
    st.info("No geographic coordinates available for the current filters.")

st.markdown("---")
st.caption(
    "Tip: Filters (left) refine all visuals and narratives. Charts are cached for speed; if you upload a larger CSV, consider sampling for the map."
)


