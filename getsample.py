from __future__ import annotations
import argparse
from datetime import datetime, timedelta
import os
import pandas as pd
from utils import fetch_311_sample


if __name__ == "__main__":
parser = argparse.ArgumentParser(description="Create a local NYC 311 sample CSV")
parser.add_argument("--rows", type=int, default=10000)
parser.add_argument("--days", type=int, default=120, help="Lookback window in days")
parser.add_argument("--outfile", type=str, default="sample.csv")
args = parser.parse_args()


end = datetime.utcnow()
start = end - timedelta(days=args.days)
df = fetch_311_sample(start, end, boroughs=None, complaint_types=None, status_list=None, max_rows=args.rows)
if df.empty:
raise SystemExit("No data returned — try increasing days or check your network/token.")
df.to_csv(args.outfile, index=False)
print(f"Wrote {len(df):,} rows to {args.outfile}")
