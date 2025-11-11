from __future__ import annotations
st.metric("Median Hours to Close", f"{median_hours:,.1f}" if pd.notnull(median_hours) else "—")
with col4:
top_type = df["complaint_type"].mode().iloc[0] if "complaint_type" in df and not df["complaint_type"].empty else "—"
st.metric("Top Complaint Type", top_type)


st.markdown("---")


# --- Charts


# Time series by day
if "created_date" in df:
ts = (df
.assign(day=lambda x: x["created_date"].dt.date)
.groupby("day", as_index=False)
.size())
fig_ts = px.line(ts, x="day", y="size", markers=True, title="Requests Over Time (sample)")
st.plotly_chart(fig_ts, use_container_width=True)


# Top complaint types
topn = (df["complaint_type"].value_counts().head(15).reset_index()
.rename(columns={"index":"complaint_type", "complaint_type":"count"}))
fig_bar = px.bar(topn, x="count", y="complaint_type", orientation="h", title="Top 15 Complaint Types (sample)")
st.plotly_chart(fig_bar, use_container_width=True)


# Borough breakdown
if "borough" in df:
bor = df["borough"].value_counts().reset_index().rename(columns={"index":"borough", "borough":"count"})
fig_b = px.bar(bor, x="borough", y="count", title="Requests by Borough (sample)")
st.plotly_chart(fig_b, use_container_width=True)


# Resolution time by complaint type (box)
if "hours_to_close" in df:
sub = df.dropna(subset=["hours_to_close"]).copy()
# clip extreme hours to 99th percentile for readability
q99 = sub["hours_to_close"].quantile(0.99)
sub = sub[sub["hours_to_close"] <= q99]
fig_box = px.box(sub, x="complaint_type", y="hours_to_close", points=False,
title="Hours to Close by Complaint Type (clipped at 99th pct)")
fig_box.update_layout(xaxis_tickangle=-45)
st.plotly_chart(fig_box, use_container_width=True)


# --- Map
if {"latitude", "longitude"}.issubset(df.columns):
map_df = df.dropna(subset=["latitude", "longitude"]).copy()
st.subheader("Map of Requests (sample)")
st.caption("Zoom to explore. Large samples are semi-transparent for context.")
layer = pdk.Layer(
"ScatterplotLayer",
data=map_df,
get_position="[longitude, latitude]",
get_radius=20,
radius_min_pixels=1,
radius_max_pixels=30,
opacity=0.25,
pickable=True,
)
view_state = pdk.ViewState(latitude=40.7128, longitude=-74.0060, zoom=9)
st.pydeck_chart(pdk.Deck(layers=[layer], initial_view_state=view_state, tooltip={"text": "{complaint_type}\n{borough}"}))


st.markdown("---")


# --- Data table & download
st.subheader("Sampled Records")
st.dataframe(df[[c for c in df.columns if c in [
"created_date","closed_date","status","agency_name","complaint_type","descriptor","borough","incident_zip","latitude","longitude","hours_to_close"
]]].head(1000))


# Download full sample
csv_buf = io.StringIO()
df.to_csv(csv_buf, index=False)
st.download_button("Download current sample as CSV", csv_buf.getvalue(), file_name="nyc311_sample.csv", mime="text/csv")


st.caption("Note: This app displays a sampled slice for speed. Adjust filters and sample size in the sidebar.")
