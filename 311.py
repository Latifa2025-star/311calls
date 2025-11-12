# 311.py
import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
from plotly.colors import qualitative
from streamlit_folium import st_folium
import folium
from folium.plugins import MarkerCluster
import branca

# ---------------------------
# Page config & theme
# ---------------------------
st.set_page_config(
    page_title="NYC 311 Service Requests Explorer",
    page_icon="📞",
    layout="wide",
)
WARM = ["#B30000", "#E34A33", "#FC8D59", "#FDBB84", "#FDD49E", "#FEE8C8"]

st.markdown(
    """
    <style>
      .smallcaps{font-variant: small-caps;}
      .muted{color:#6b7280}
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("📞 NYC 311 Service Requests Explorer")
st.caption("Explore complaint types, resolution times, and closure rates by day & hour — powered by a compressed local dataset (.csv.gz).")

# ---------------------------
# Data
# ---------------------------
@st.cache_data(show_spinner=True)
def load_data(path: str):
    df = pd.read_csv(path, compression="gzip", low_memory=False)
    # Parse dates safely
    for c in ["created_date", "closed_date", "resolution_action_updated_date"]:
        if c in df:
            df[c] = pd.to_datetime(df[c], errors="coerce")

    # Derived fields
    if {"created_date", "closed_date"}.issubset(df.columns):
        df["hours_to_close"] = (df["closed_date"] - df["created_date"]).dt.total_seconds() / 3600.0
    else:
        df["hours_to_close"] = np.nan

    if "created_date" in df:
        df["hour"] = df["created_date"].dt.hour
        df["day_of_week"] = df["created_date"].dt.day_name()
        df["month"] = df["created_date"].dt.to_period("M").astype(str)

    # Clean text columns likely used in UI
    for c in ["status", "borough", "complaint_type", "agency_name"]:
        if c in df:
            df[c] = df[c].astype(str)

    return df

DATA_PATH = "nyc311_12months.csv.gz"
df = load_data(DATA_PATH)
st.success(f"Loaded data from `{DATA_PATH}`")

# ---------------------------
# Sidebar filters
# ---------------------------
st.sidebar.header("Filters")

day_options = ["All"] + sorted(df["day_of_week"].dropna().unique())
sel_day = st.sidebar.selectbox("Day of Week", day_options, index=0)

hr_from, hr_to = st.sidebar.slider("Hour range (24h)", 0, 23, (0, 23))
boros = ["All"] + sorted(df["borough"].dropna().unique())
sel_boros = st.sidebar.multiselect("Borough(s)", boros, default=["All"])
top_n = st.sidebar.slider("Top complaint types to show", 5, 30, 20)

# ---------------------------
# Apply filters
# ---------------------------
xdf = df.copy()

if sel_day != "All":
    xdf = xdf[xdf["day_of_week"] == sel_day]

xdf = xdf[(xdf["hour"] >= hr_from) & (xdf["hour"] <= hr_to)]

if len(sel_boros) > 0 and "All" not in sel_boros:
    xdf = xdf[xdf["borough"].isin(sel_boros)]

# ---------------------------
# KPI line
# ---------------------------
rows = len(xdf)
pct_closed = (xdf["status"].str.lower().eq("closed").mean() * 100) if rows else 0.0
median_hrs = float(np.nanmedian(xdf["hours_to_close"])) if rows else np.nan
top_type = xdf["complaint_type"].mode().iat[0] if rows else "—"

c1, c2, c3, c4 = st.columns(4)
c1.metric("Rows (after filters)", f"{rows:,}")
c2.metric("% Closed", f"{pct_closed:.1f}%")
c3.metric("Median Hours to Close", "-" if np.isnan(median_hrs) else f"{median_hrs:.2f}")
c4.metric("Top Complaint Type", top_type)

# ---------------------------
# Helper: warm discrete colors
# ---------------------------
def warm_palette(n):
    # Cycle through WARM palette if more categories than colors
    base = WARM
    if n <= len(base):
        return base[:n]
    # extend by repeating lighter tints
    reps = (n // len(base)) + 1
    out = (base * reps)[:n]
    return out

# ---------------------------
# Section: Top complaint types (bar)
# ---------------------------
st.subheader("📊 Top Complaint Types")
st.caption("What issues are most frequently reported under the current filters?")
if rows == 0:
    st.info("No data for current filters.")
else:
    counts = (
        xdf["complaint_type"]
        .value_counts(dropna=False)
        .reset_index()
        .rename(columns={"index": "Complaint Type", "complaint_type": "Count"})
        .head(top_n)
    )

    # Narrative
    lead = counts.iloc[0]
    st.markdown(
        f"**Narrative:** **{lead['Complaint Type']}** leads with **{int(lead['Count']):,}** requests "
        f"under the selected filters."
    )

    fig_bar = px.bar(
        counts,
        x="Count",
        y="Complaint Type",
        orientation="h",
        color="Complaint Type",
        color_discrete_sequence=warm_palette(len(counts)),
        text="Count",
        title=f"Top {top_n} Complaint Types",
    )
    fig_bar.update_layout(
        yaxis=dict(autorange="reversed", title=None),
        xaxis_title="Requests (count)",
        title_font=dict(size=18)
    )
    fig_bar.update_traces(texttemplate="%{text:,}", textposition="outside")
    st.plotly_chart(fig_bar, use_container_width=True)

# ---------------------------
# Section: Status breakdown (pie) — robust against column name issues
# ---------------------------
st.subheader("📈 Status Breakdown")
st.caption("How are requests currently tracked (Closed, In Progress, etc.) under the filters?")
if rows:
    # Build a very clean DF with unique column names
    sc = (
        xdf["status"]
        .fillna("Unknown")
        .value_counts()
        .reset_index()
        .rename(columns={"index": "Status", "status": "Count"})
    )
    # Ensure uniqueness (narwhals DuplicateError happens if duplicate col names)
    sc = sc.loc[:, ["Status", "Count"]]

    # Narrative
    s_lead = sc.iloc[0]
    st.markdown(
        f"**Narrative:** The most common status is **{s_lead['Status']}** "
        f"with **{int(s_lead['Count']):,}** records. Overall **{pct_closed:.1f}%** of requests are closed."
    )

    fig_pie = px.pie(
        sc, values="Count", names="Status",
        hole=0.55, color="Status",
        color_discrete_sequence=qualitative.Set3,
        title="Status Breakdown"
    )
    fig_pie.update_traces(textinfo="label+percent", pull=[0.05]*len(sc))
    st.plotly_chart(fig_pie, use_container_width=True)
else:
    st.info("No data for current filters.")

# ---------------------------
# Section: Resolution time by complaint (box)
# ---------------------------
st.subheader("⏱️ Resolution Time by Complaint Type")
st.caption("Compare how long each type of complaint typically takes to resolve.")
if rows and "hours_to_close" in xdf:
    # keep only finite values
    bx = xdf[np.isfinite(xdf["hours_to_close"])]
    if len(bx):
        # Narrative: slowest/fastest medians
        med = (
            bx.groupby("complaint_type")["hours_to_close"]
            .median()
            .sort_values(ascending=False)
        )
        slow = med.index[0] if len(med) else "—"
        fast = med.index[-1] if len(med) else "—"
        st.markdown(
            f"**Narrative:** Slowest median resolution appears for **{slow}**, "
            f"while **{fast}** tends to resolve fastest."
        )

        fig_box = px.box(
            bx, x="complaint_type", y="hours_to_close",
            color="complaint_type",
            color_discrete_sequence=warm_palette(bx["complaint_type"].nunique()),
            points=False, title="Resolution Time (hours)"
        )
        fig_box.update_layout(
            xaxis=dict(showticklabels=True, tickangle=45, title=None),
            yaxis_title="Hours to Close",
            showlegend=False,
            title_font=dict(size=18)
        )
        st.plotly_chart(fig_box, use_container_width=True)
    else:
        st.info("No valid resolution-time values for current filters.")
else:
    st.info("No valid resolution-time values for current filters.")

# ---------------------------
# Section: Heatmap (Day × Hour)
# ---------------------------
st.subheader("🔥 When are requests made?")
st.caption("Interactive heatmap showing request patterns by hour and day of week.")
if rows:
    heat = (
        xdf.groupby(["day_of_week", "hour"])
        .size()
        .reset_index(name="Requests")
    )
    if len(heat):
        fig_heat = px.density_heatmap(
            heat, x="hour", y="day_of_week", z="Requests",
            color_continuous_scale="YlOrRd", title="Requests by Hour and Day"
        )
        fig_heat.update_traces(hovertemplate="Hour %{x}:00<br>Day: %{y}<br>Requests: %{z}")
        fig_heat.update_layout(
            xaxis_title="Hour of Day (24h)",
            yaxis_title="Day of Week",
            title_font=dict(size=18)
        )
        # Narrative
        maxcell = heat.loc[heat["Requests"].idxmax()]
        st.markdown(
            f"**Narrative:** Peak demand in this view occurs around **{int(maxcell['hour']):02d}:00** "
            f"on **{maxcell['day_of_week']}** with **{int(maxcell['Requests']):,}** requests."
        )
        st.plotly_chart(fig_heat, use_container_width=True)
    else:
        st.info("No requests by hour/day for current filters.")
else:
    st.info("No data for current filters.")

# ---------------------------
# Section: Animated bar race (the one you asked to keep)
# ---------------------------
st.subheader("▶️ How do complaints evolve through the day?")
st.caption("Press **Play** to watch requests change by hour (we focus on top categories so the animation stays clear).")
if rows:
    # Focus on top K complaint types overall in current view
    TOPK = 6
    topcats = (
        xdf["complaint_type"].value_counts().head(TOPK).index.tolist()
    )
    anim = (
        xdf[xdf["complaint_type"].isin(topcats)]
        .groupby(["hour", "complaint_type"])
        .size()
        .reset_index(name="Requests")
    )
    if len(anim):
        fig_anim = px.bar(
            anim,
            x="Requests",
            y="complaint_type",
            animation_frame="hour",
            orientation="h",
            color="complaint_type",
            color_discrete_sequence=warm_palette(len(topcats)),
            title="How requests evolve through the day (press ▶ to play)",
            range_x=[0, max(anim["Requests"].max()*1.1, 1)],
        )
        fig_anim.update_layout(
            yaxis=dict(autorange="reversed", title="Complaint Type"),
            xaxis_title="Requests (count)",
            title_font=dict(size=18),
            showlegend=False
        )
        st.plotly_chart(fig_anim, use_container_width=True)
        # Narrative (hour with max requests)
        peak = (
            anim.groupby("hour")["Requests"].sum().idxmax()
            if len(anim) else None
        )
        if peak is not None:
            st.markdown(f"**Narrative:** Across the highlighted categories, **{peak:02d}:00** sees the most requests.")
    else:
        st.info("Not enough data to animate for current filters.")
else:
    st.info("No data for current filters.")

# ---------------------------
# Section: Bubble animation (spaced on hour)
# ---------------------------
st.subheader("🫧 Bubble view: complaints by hour (animated)")
st.caption("Each bubble size reflects the request count for that complaint type at the given hour.")
if rows:
    bub = (
        xdf.groupby(["hour", "complaint_type"])
        .size()
        .reset_index(name="Requests")
    )
    if len(bub):
        fig_bubble = px.scatter(
            bub, x="hour", y="complaint_type", size="Requests",
            color="complaint_type",
            animation_frame="hour",
            size_max=60, range_x=[-0.5, 23.5],
            color_discrete_sequence=warm_palette(bub["complaint_type"].nunique()),
            title="Complaints Over the Day (Animated Bubbles)"
        )
        fig_bubble.update_layout(
            xaxis_title="Hour of Day",
            yaxis_title=None,
            title_font=dict(size=18),
            showlegend=False
        )
        st.plotly_chart(fig_bubble, use_container_width=True)
    else:
        st.info("Not enough data to animate bubbles.")
else:
    st.info("No data for current filters.")

# ---------------------------
# Section: Map with legend + rich tooltips
# ---------------------------
st.subheader("🗺️ Complaint hotspots across NYC")
st.caption("Green = Closed, Orange = In Progress, Red = Open, Gray = Other. Click a marker for details.")

if rows and {"latitude", "longitude"}.issubset(xdf.columns):
    # Sample for performance
    SAMPLE = min(2000, len(xdf))
    mdf = xdf.dropna(subset=["latitude", "longitude"]).sample(SAMPLE, random_state=42)

    # Map base
    m = folium.Map(location=[40.7128, -74.0060], zoom_start=11, tiles="cartodbpositron")
    cluster = MarkerCluster().add_to(m)

    def status_color(s):
        s = (s or "").lower()
        if s == "closed": return "green"
        if s == "in progress": return "orange"
        if s == "open": return "red"
        return "gray"

    for _, r in mdf.iterrows():
        popup = folium.Popup(
            html=(
                f"<b>{r.get('complaint_type','')}</b><br>"
                f"Borough: {r.get('borough','')}<br>"
                f"Status: {r.get('status','')}<br>"
                f"Hours to Close: {'' if pd.isna(r.get('hours_to_close')) else round(float(r['hours_to_close']),2)}"
            ),
            max_width=250
        )
        tooltip = folium.Tooltip(
            f"{r.get('complaint_type','')} — {r.get('status','')} ({r.get('borough','')})"
        )
        folium.CircleMarker(
            location=[float(r["latitude"]), float(r["longitude"])],
            radius=4,
            color=status_color(r.get("status")),
            fill=True, fill_opacity=0.7,
            popup=popup, tooltip=tooltip
        ).add_to(cluster)

    # Legend
    legend_html = """
      <div style='position: fixed; bottom: 40px; left: 40px; z-index:9999;
                  background: white; padding: 10px 14px; border:1px solid #ccc; border-radius:8px;'>
        <b>Legend</b><br>
        <span style='color:green;'>●</span> Closed<br>
        <span style='color:orange;'>●</span> In Progress<br>
        <span style='color:red;'>●</span> Open<br>
        <span style='color:gray;'>●</span> Other
      </div>
    """
    m.get_root().html.add_child(branca.element.Element(legend_html))

    st_folium(m, height=550, width=None)
else:
    st.info("No coordinates available in this dataset for the current filters.")

st.markdown("---")
st.caption("Tip: If you ever see the small runner icon near “Share”, it just means the app is refreshing after you changed a filter. Caching keeps it quick.")
