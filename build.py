import duckdb
from pathlib import Path

con = duckdb.connect('nyc_311.duckdb')

scripts = ['sql/01_raw_views.sql', 'sql/02_norm_views.sql', 'sql/03_sla_base_views.sql', 'sql/04_sla_compliance_views.sql']

for script in scripts:
    print("Running build")
    sql = Path(script).read_text()
    con.execute(sql)

con.close()
print("Build completed")
