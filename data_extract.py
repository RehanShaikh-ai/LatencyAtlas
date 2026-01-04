from sodapy import Socrata
import pandas as pd

client = Socrata("data.cityofnewyork.us", app_token="QKhO8wnO3Ye0lGNoc1p0w2fLj")

query = """
SELECT
  unique_key,
  created_date,
  closed_date,
  agency,
  agency_name,
  complaint_type,
  descriptor,
  status,
  borough
WHERE created_date
  BETWEEN '2021-01-01T00:00:00' AND '2026-01-01T00:00:00'
ORDER BY created_date DESC
LIMIT 200000
"""

results = client.get("erm2-nwe9", query=query)

df = pd.DataFrame.from_records(results)
print(len(df))
df.to_parquet('NYC311.parquet', index=False)



