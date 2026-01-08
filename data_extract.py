from sodapy import Socrata
import pandas as pd
import os
from dotenv import load_dotenv

load_dotenv()
client = Socrata("data.cityofnewyork.us", app_token=os.getenv('SOCRATA_APP_TOKEN'))

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
LIMIT 20_000_000
"""

results = client.get("erm2-nwe9", query=query)

df = pd.DataFrame.from_records(results)
print(len(df))
df.to_parquet('NYC311.parquet', index=False)



