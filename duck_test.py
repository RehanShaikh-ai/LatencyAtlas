import duckdb

con = duckdb.connect()

query = """
SELECT
  agency,
  COUNT(*) AS complaints
FROM 'NYC311.parquet'
GROUP BY agency
ORDER BY complaints DESC
"""

df = con.execute(query).fetchdf()
print(df.head())
