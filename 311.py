from __future__ import annotations
if status_list and len(status_list) > 0:
sq = ",".join([f"'{s}'" for s in status_list])
where_clauses.append(f"status in ({sq})")


where = " AND ".join(where_clauses)


if client is None:
raise RuntimeError("sodapy is not available — cannot query API.")


# Pull a capped set ordered by recency for responsiveness
results = client.get(
DATASET_ID,
where=where,
select=",".join(CORE_COLUMNS),
order="created_date DESC",
limit=max_rows,
)


df = pd.DataFrame.from_records(results)
if df.empty:
return df


# Normalize types
dt_cols = ["created_date", "closed_date", "resolution_action_updated_date"]
for c in dt_cols:
if c in df:
df[c] = pd.to_datetime(df[c], errors="coerce")


num_cols = ["latitude", "longitude"]
for c in num_cols:
if c in df:
df[c] = pd.to_numeric(df[c], errors="coerce")


# Derive metrics
if "closed_date" in df and "created_date" in df:
df["hours_to_close"] = (df["closed_date"] - df["created_date"]).dt.total_seconds() / 3600.0


if "borough" in df:
df["borough"].fillna("Unknown", inplace=True)


return df




def load_local_sample(path: str = "sample.csv") -> pd.DataFrame:
if not os.path.exists(path):
return pd.DataFrame()
df = pd.read_csv(path)
# Coerce types similar to API path
for c in ["created_date", "closed_date", "resolution_action_updated_date"]:
if c in df:
df[c] = pd.to_datetime(df[c], errors="coerce")
for c in ["latitude", "longitude"]:
if c in df:
df[c] = pd.to_numeric(df[c], errors="coerce")
if "hours_to_close" not in df and {"closed_date","created_date"}.issubset(df.columns):
df["hours_to_close"] = (df["closed_date"] - df["created_date"]).dt.total_seconds() / 3600.0
return df
