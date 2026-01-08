import duckdb

con = duckdb.connect("nyc_311.duckdb")

con.execute(
    """
CREATE OR REPLACE VIEW v_raw \
            AS
            SELECT *
            FROM read_parquet('NYC311.parquet') 
            """
)

con.execute(
    """
CREATE OR REPLACE VIEW v_norm
            AS 
            SELECT * ,
            CASE 
            
            WHEN lower(status) IN(
            'open', 
            'in progress', 
            'pending', 
            'started',
            'assigned') THEN 'Open'
            
            WHEN lower(status) = 'closed'
            THEN 'Closed'
            
            ELSE 'Unspecified'

            END AS normalized_status
            FROM v_raw
            
            """
)

con.execute(
    """
            SELECT *
            FROM v_norm 
            LIMIT 10 """
).fetch_df()

con.execute( """
    SELECT ((SELECT COUNT(*) FROM v_norm WHERE lower(normalized_status) = 'unspecified' )/ COUNT(*)) * 100 FROM v_norm        

""").fetchone()

con.execute( """SELECT
    COUNT(*) AS cnt
FROM v_norm;

""").fetchdf()

