import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
from streamlit_folium import st_folium
import folium
from folium.plugins import MarkerCluster

# -------------------------------
# Page setup
# -------------------------------
st.set_page_config(
    page_title="NYC 311 Service Requests Explorer",
    page_icon="📞",
    layout="wide",
)

TITLE = "📞 NYC 311 Service Requests Explorer"
st.markdown(f"<h1 style='margin-bottom:0.2rem'>{TITLE}</h1>", unsafe_allow_html=True)
st.caption(
    "Explore complaint types, resolution times, and closure rates by day and hour — powered by a compressed local dataset."
)

# -------------------------------
# Data loader (robust)
# -------------------------------
@st.cache_data(show_spinner=True)
def load_data():
    # Try common filenames so you don't have to change code if you swap files
    for fname in ["nyc311_12months.csv.gz", "nyc311_12months.csv",
                  "nyc311_sample.csv.gz", "nyc311_sample.csv"]:
        try:
            if fname.endswith(".gz"):
                df = pd.read_csv(fname, compression="gzip", low_memory=False)
            else:
                df = pd.read_csv(fname, low_memory=False)
            source = fname
            break
        except Exception:
            df, source = None, None
    if df is None:
        raise FileNotFoundError(
            "No local CSV found. Place `nyc311_12months.csv.gz` (or a small sample) beside 311.py."
        )

    # Parse datetimes
    for c in ["created_date", "closed_date"]:
        if c in df:
            df[c] = pd.to_datetime(df[c], errors="coerce")

    # Derived fields
    if {"created_date", "closed_date"}.issubset(df.columns):
        df["hours_to_close"] = (df["closed_date"] - df["created_date"]).dt.total_seconds() / 3600

    if "created_date" in df:
        df["hour"] = df["created_date"].dt.hour
        df["day_of_week"] = df["created_date"].dt.day_name()

    # Normalize some columns we use a lot
    for col in ["status", "complaint_type", "borough"]:
        if col in df:
            df[col] = df[col].fillna("Unspecified")

    return df, source

df, source = load_data()
st.success(f"Loaded data from `{source}`")

# -------------------------------
# Sidebar filters
# -------------------------------
st.sidebar.header("Filters")

day_options = ["All"] + sorted(df["day_of_week"].dropna().unique()) if "day_of_week" in df else ["All"]
day_pick = st.sidebar.selectbox("Day of Week", day_options, index=0)

hour_range = st.sidebar.slider("Hour range (24h)", 0, 23, (0, 23))
boro_options = ["All"] + sorted(df["borough"].dropna().unique()) if "borough" in df else ["All"]
boro_pick = st.sidebar.multiselect("Borough(s)", boro_options, default=["All"])

top_n = st.sidebar.slider("Top complaint types to show", 5, 30, 20)

# -------------------------------
# Apply filters
# -------------------------------
df_f = df.copy()

if day_pick != "All" and "day_of_week" in df_f:
    df_f = df_f[df_f["day_of_week"] == day_pick]

if "hour" in df_f:
    df_f = df_f[(df_f["hour"] >= hour_range[0]) & (df_f["hour"] <= hour_range[1])]

if "All" not in boro_pick and "borough" in df_f:
    df_f = df_f[df_f["borough"].isin(boro_pick)]

# -------------------------------
# KPI row
# -------------------------------
c1, c2, c3, c4 = st.columns(4)
rows_after = len(df_f)
c1.metric("Rows (after filters)", f"{rows_after:,}")

if "status" in df_f:
    pct_closed = df_f["status"].eq("Closed").mean() * 100 if rows_after else 0.0
else:
    pct_closed = 0.0
c2.metric("% Closed", f"{pct_closed:.1f}%")

median_hours = df_f["hours_to_close"].median() if "hours_to_close" in df_f and rows_after else np.nan
c3.metric("Median Hours to Close", "-" if np.isnan(median_hours) else f"{median_hours:.2f}")

top_type = df_f["complaint_type"].mode()[0] if "complaint_type" in df_f and rows_after else "—"
c4.metric("Top Complaint Type", top_type)

# -------------------------------
# Helper: warm palette
# -------------------------------
WARM = ["#8B0000","#B22222","#DC143C","#FF4500","#FF7F50","#FFA500","#FFB347","#FFD580"]

# --------------------------------
# TOP COMPLAINT TYPES (with narrative)
# --------------------------------
st.subheader("📊 Top Complaint Types")
st.caption("What issues are most frequently reported under the current filters?")

if rows_after and "complaint_type" in df_f:
    counts = (
        df_f["complaint_type"]
        .value_counts()
        .head(top_n)
        .rename_axis("Complaint Type")
        .reset_index(name="Count")
    )

    if not counts.empty:
        lead = counts.iloc[0]
        st.markdown(
            f"**Narrative:** **{lead['Complaint Type']}** leads with **{int(lead['Count']):,}** requests "
            f"under the current filters. The top {min(top_n, len(counts))} categories together account for "
            f"**{int(counts['Count'].sum()):,}** calls."
        )

        fig_bar = px.bar(
            counts,
            x="Count",
            y="Complaint Type",
            orientation="h",
            text="Count",
            color="Count",
            color_continuous_scale=WARM,
            title=f"Top {min(top_n, len(counts))} Complaint Types",
        )
        fig_bar.update_traces(texttemplate="%{text:,}", textposition="outside", cliponaxis=False)
        fig_bar.update_layout(
            yaxis=dict(autorange="reversed", title=None),
            xaxis_title="Requests (count)",
            title_font=dict(size=18)
        )
        st.plotly_chart(fig_bar, use_container_width=True)
    else:
        st.info("No complaint types found for these filters.")
else:
    st.info("No data available for these filters.")

# --------------------------------
# STATUS BREAKDOWN (pie) with narrative
# --------------------------------
st.subheader("📈 Status Breakdown")
st.caption("How are requests currently tracked (Closed, In Progress, etc.) under the filters?")

if rows_after and "status" in df_f:
    status_counts = (
        df_f["status"]
        .fillna("Unspecified")
        .value_counts()
        .rename_axis("Status")
        .reset_index(name="Count")
    )

    if not status_counts.empty:
        lead = status_counts.iloc[0]
        st.markdown(
            f"**Narrative:** **{lead['Status']}** is the largest status with **{int(lead['Count']):,}** requests. "
            f"Overall closure rate is **{pct_closed:.1f}%**."
        )

        # Ensure unique, proper column names for Plotly’s new backend
        status_counts = pd.DataFrame(status_counts.loc[:, ["Status", "Count"]])

        fig_pie = px.pie(
            status_counts, values="Count", names="Status",
            hole=0.5, color_discrete_sequence=px.colors.qualitative.Set3,
            title="Status Breakdown"
        )
        fig_pie.update_traces(textinfo="label+percent")
        st.plotly_chart(fig_pie, use_container_width=True)
    else:
        st.info("No status data for these filters.")
else:
    st.info("No status column in data or no rows after filters.")

# --------------------------------
# RESOLUTION TIME BY TYPE (box) with narrative
# --------------------------------
st.subheader("⏱️ Resolution Time by Complaint Type")
st.caption("Compare how long each type of complaint typically takes to resolve.")

if rows_after and {"complaint_type","hours_to_close"}.issubset(df_f.columns):
    # Keep chart readable: show the top 20 complaint types by count
    top_for_box = (
        df_f["complaint_type"]
        .value_counts()
        .head(20)
        .index
    )
    df_box = df_f[df_f["complaint_type"].isin(top_for_box)]

    fig_box = px.box(
        df_box, x="complaint_type", y="hours_to_close",
        color="complaint_type", points=False,
        color_discrete_sequence=px.colors.qualitative.Set2,
        title="Resolution Time (hours)"
    )
    fig_box.update_layout(
        xaxis=dict(title=None, tickangle=45),
        yaxis_title="Hours to Close",
        showlegend=False,
        title_font=dict(size=18),
    )
    st.plotly_chart(fig_box, use_container_width=True)

    # Narrative: slowest 3 by median
    med = (
        df_box.groupby("complaint_type")["hours_to_close"]
        .median()
        .sort_values(ascending=False)
        .head(3)
    )
    if len(med) > 0:
        bullets = " • ".join([f"**{k}** (~{v:.1f}h)" for k, v in med.items()])
        st.markdown(f"**Narrative:** Slowest to resolve (median) → {bullets}.")
else:
    st.info("Not enough information to compute resolution times for these filters.")

# --------------------------------
# HEATMAP Day × Hour with narrative
# --------------------------------
st.subheader("🔥 When are requests made?")
st.caption("Heatmap showing request patterns by hour and day of week.")

if rows_after and {"day_of_week","hour"}.issubset(df_f.columns):
    order_days = ["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"]
    heat = (
        df_f.groupby(["day_of_week","hour"])
        .size()
        .reset_index(name="Number of Requests")
    )
    # Keep weekday order
    heat["day_of_week"] = pd.Categorical(heat["day_of_week"], categories=order_days, ordered=True)
    heat = heat.sort_values(["day_of_week","hour"])

    fig_heat = px.density_heatmap(
        heat, x="hour", y="day_of_week", z="Number of Requests",
        color_continuous_scale="YlOrRd", title="Requests by Hour and Day",
    )
    fig_heat.update_traces(
        hovertemplate="Hour: %{x}:00<br>Day: %{y}<br>Requests: %{z}"
    )
    fig_heat.update_layout(
        xaxis_title="Hour of Day (24h)",
        yaxis_title="Day of Week",
        title_font=dict(size=18),
    )
    st.plotly_chart(fig_heat, use_container_width=True)

    # Narrative: busiest cell
    hot = heat.sort_values("Number of Requests", ascending=False).head(1)
    if len(hot):
        st.markdown(
            f"**Narrative:** Busiest time is **{hot.iloc[0]['day_of_week']} {int(hot.iloc[0]['hour']):02d}:00** "
            f"with **{int(hot.iloc[0]['Number of Requests']):,}** requests."
        )

# --------------------------------
# ANIMATED BAR (keep the warm colors) + narrative
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

# --------------------------------
# GEOGRAPHIC MAP with legend + tooltips/popups
# --------------------------------
st.subheader("🗺️ Complaint Hotspots Across NYC")
st.caption("Map shows sampled complaints. Dot color = status (legend below). Click a dot for details.")

if rows_after and {"latitude","longitude"}.issubset(df_f.columns):
    # Sample to keep performance snappy
    sample_n = min(1500, len(df_f))
    df_map = df_f.dropna(subset=["latitude","longitude"]).sample(sample_n, random_state=42)

    # Simple status→color legend
    status_colors = {
        "Closed": "#2E7D32",          # green
        "In Progress": "#1E88E5",     # blue
        "Open": "#FB8C00",            # orange
        "Assigned": "#8E24AA",        # purple
        "Pending": "#F4511E",         # deep orange
        "Started": "#3949AB",         # indigo
        "Unspecified": "#9E9E9E",     # grey
    }
    def pick_color(s):
        return status_colors.get(s, "#9E9E9E")

    # Build map
    m = folium.Map(location=[40.7128, -74.0060], zoom_start=11, tiles="cartodbpositron")
    cluster = MarkerCluster().add_to(m)

    for _, r in df_map.iterrows():
        status = r.get("status", "Unspecified")
        color = pick_color(status)
        hrs = r.get("hours_to_close", np.nan)
        hrs_txt = "N/A" if pd.isna(hrs) else f"{hrs:.1f} h"
        created = r.get("created_date", "")
        created_txt = "" if pd.isna(created) else created.strftime("%Y-%m-%d %H:%M")

        popup_html = folium.Popup(
            folium.IFrame(
                f"""
                <b>{r.get('complaint_type','(Unknown)')}</b><br>
                Borough: {r.get('borough','-')}<br>
                Status: {status}<br>
                Hours to close: {hrs_txt}<br>
                Created: {created_txt}
                """,
                width=260, height=120
            ),
            max_width=260
        )
        tooltip = folium.Tooltip(
            f"{r.get('complaint_type','(Unknown)')} — {status} ({hrs_txt})",
            sticky=True
        )
        folium.CircleMarker(
            location=[r["latitude"], r["longitude"]],
            radius=4, color=color, fill=True, fill_color=color, fill_opacity=0.75,
            tooltip=tooltip, popup=popup_html
        ).add_to(cluster)

    # Add HTML legend
    legend_html = """
    <div style="
        position: fixed; 
        bottom: 30px; left: 30px; z-index: 9999;
        background: rgba(255,255,255,0.9);
        padding: 10px 12px; border: 1px solid #ccc; border-radius: 6px;
        font-size: 13px;">
      <b>Legend — Status</b><br>
      <div style="margin-top:6px">
        <span style="display:inline-block;width:10px;height:10px;background:#2E7D32;border-radius:50%"></span> Closed &nbsp;
        <span style="display:inline-block;width:10px;height:10px;background:#1E88E5;border-radius:50%"></span> In Progress &nbsp;
        <span style="display:inline-block;width:10px;height:10px;background:#FB8C00;border-radius:50%"></span> Open &nbsp;
        <span style="display:inline-block;width:10px;height:10px;background:#8E24AA;border-radius:50%"></span> Assigned &nbsp;
        <span style="display:inline-block;width:10px;height:10px;background:#F4511E;border-radius:50%"></span> Pending &nbsp;
        <span style="display:inline-block;width:10px;height:10px;background:#3949AB;border-radius:50%"></span> Started &nbsp;
        <span style="display:inline-block;width:10px;height:10px;background:#9E9E9E;border-radius:50%"></span> Unspecified
      </div>
    </div>
    """
    m.get_root().html.add_child(folium.Element(legend_html))
    st_folium(m, width=1200, height=600)
else:
    st.info("No latitude/longitude columns in the dataset (or no rows after filters).")

st.markdown("---")
st.caption("Tip: If the runner icon stays spinning for long, try narrowing filters or lowering chart item counts.")

