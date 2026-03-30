"""
mysql_setup.py
──────────────
Creates and populates MySQL summary tables from DuckDB v_sla.
Run once (or re-run to refresh) after build.py has completed.

Usage:
    python src/mysql_setup.py
"""

import logging
import os
from pathlib import Path

import duckdb
import mysql.connector
from dotenv import load_dotenv

_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(dotenv_path=_ROOT / ".env")

(_ROOT / "logs").mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[logging.FileHandler(_ROOT / "logs/mysql_setup.log"), logging.StreamHandler()],
    force=True,
)
logger = logging.getLogger(__name__)

DUCKDB_PATH = _ROOT / "nyc_311.duckdb"

MYSQL_CONFIG = {
    "host":     os.getenv("MYSQL_HOST", "localhost"),
    "user":     os.getenv("MYSQL_USER", "root"),
    "password": os.getenv("MYSQL_PASSWORD", ""),
}
DB_NAME = os.getenv("MYSQL_DATABASE", "latencyatlas_db")

_COMPLIANT = "severity IN ('Excellent', 'Compliant')"
_BREACHED  = "severity IN ('Breach', 'Extreme Breach')"

# ── DDL ──────────────────────────────────────────────────────────────────────

DDL = """
CREATE TABLE IF NOT EXISTS kpi_summary (
    total_requests  BIGINT,
    compliant       BIGINT,
    breached        BIGINT,
    compliance_rate DECIMAL(6,2),
    breach_rate     DECIMAL(6,2)
);

CREATE TABLE IF NOT EXISTS borough_breach (
    borough     VARCHAR(64),
    total       BIGINT,
    breached    BIGINT,
    breach_rate DECIMAL(6,2)
);

CREATE TABLE IF NOT EXISTS agency_breach (
    agency_name VARCHAR(128),
    total       BIGINT,
    breached    BIGINT,
    breach_rate DECIMAL(6,2)
);

CREATE TABLE IF NOT EXISTS response_variability (
    borough     VARCHAR(64),
    avg_hrs     DECIMAL(10,2),
    stddev_hrs  DECIMAL(10,2),
    min_hrs     DECIMAL(10,2),
    max_hrs     DECIMAL(10,2)
);

CREATE TABLE IF NOT EXISTS complaint_types (
    complaint_type  VARCHAR(128),
    total           BIGINT,
    breached        BIGINT,
    breach_rate     DECIMAL(6,2)
);

CREATE TABLE IF NOT EXISTS monthly_trend (
    month           VARCHAR(7),
    compliance_rate DECIMAL(6,2)
);
"""

# ── DuckDB queries ────────────────────────────────────────────────────────────

QUERIES = {
    "kpi_summary": f"""
        SELECT
            COUNT(*)::BIGINT AS total_requests,
            SUM(CASE WHEN {_COMPLIANT} THEN 1 ELSE 0 END)::BIGINT AS compliant,
            SUM(CASE WHEN {_BREACHED}  THEN 1 ELSE 0 END)::BIGINT AS breached,
            ROUND(100.0 * SUM(CASE WHEN {_COMPLIANT} THEN 1 ELSE 0 END) / NULLIF(COUNT(*),0), 2) AS compliance_rate,
            ROUND(100.0 * SUM(CASE WHEN {_BREACHED}  THEN 1 ELSE 0 END) / NULLIF(COUNT(*),0), 2) AS breach_rate
        FROM v_sla
    """,
    "borough_breach": f"""
        SELECT
            borough,
            COUNT(*)::BIGINT AS total,
            SUM(CASE WHEN {_BREACHED} THEN 1 ELSE 0 END)::BIGINT AS breached,
            ROUND(100.0 * SUM(CASE WHEN {_BREACHED} THEN 1 ELSE 0 END) / NULLIF(COUNT(*),0), 2) AS breach_rate
        FROM v_sla
        WHERE borough IS NOT NULL AND borough != 'Unspecified'
        GROUP BY borough
        ORDER BY breach_rate DESC
    """,
    "agency_breach": f"""
        SELECT
            agency_name,
            COUNT(*)::BIGINT AS total,
            SUM(CASE WHEN {_BREACHED} THEN 1 ELSE 0 END)::BIGINT AS breached,
            ROUND(100.0 * SUM(CASE WHEN {_BREACHED} THEN 1 ELSE 0 END) / NULLIF(COUNT(*),0), 2) AS breach_rate
        FROM v_sla
        GROUP BY agency_name
        ORDER BY breached DESC
        LIMIT 6
    """,
    "response_variability": """
        SELECT
            borough,
            ROUND(AVG(resolution_minutes) / 60.0, 2)          AS avg_hrs,
            ROUND(STDDEV_SAMP(resolution_minutes) / 60.0, 2)  AS stddev_hrs,
            ROUND(MIN(resolution_minutes) / 60.0, 2)          AS min_hrs,
            ROUND(MAX(resolution_minutes) / 60.0, 2)          AS max_hrs
        FROM v_sla
        WHERE borough IS NOT NULL AND borough != 'Unspecified'
        GROUP BY borough
        ORDER BY avg_hrs DESC
    """,
    "complaint_types": f"""
        SELECT
            complaint_type,
            COUNT(*)::BIGINT AS total,
            SUM(CASE WHEN {_BREACHED} THEN 1 ELSE 0 END)::BIGINT AS breached,
            ROUND(100.0 * SUM(CASE WHEN {_BREACHED} THEN 1 ELSE 0 END) / NULLIF(COUNT(*),0), 2) AS breach_rate
        FROM v_sla
        GROUP BY complaint_type
        ORDER BY total DESC
        LIMIT 8
    """,
    "monthly_trend": f"""
        SELECT
            strftime(created_ts, '%Y-%m') AS month,
            ROUND(100.0 * SUM(CASE WHEN {_COMPLIANT} THEN 1 ELSE 0 END) / NULLIF(COUNT(*),0), 2) AS compliance_rate
        FROM v_sla
        GROUP BY month
        ORDER BY month ASC
    """,
}


def get_conn(database=None):
    cfg = {**MYSQL_CONFIG}
    if database:
        cfg["database"] = database
    return mysql.connector.connect(**cfg)


def main():
    logger.info("==============================================")
    logger.info("Starting MySQL setup")

    # create database if it doesn't exist
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(f"CREATE DATABASE IF NOT EXISTS `{DB_NAME}`")
    cur.close()
    conn.close()
    logger.info(f"Database '{DB_NAME}' ready")

    conn = get_conn(database=DB_NAME)
    cur = conn.cursor()

    # create tables
    for statement in DDL.strip().split(";"):
        statement = statement.strip()
        if statement:
            cur.execute(statement)
    conn.commit()
    logger.info("Tables created")

    # pull from DuckDB and push to MySQL
    with duckdb.connect(str(DUCKDB_PATH), read_only=True) as duck:
        for table, query in QUERIES.items():
            logger.info(f"Populating {table}...")
            rows = duck.execute(query).fetchall()
            cols = [d[0] for d in duck.execute(query).description]

            cur.execute(f"TRUNCATE TABLE `{table}`")
            if rows:
                placeholders = ", ".join(["%s"] * len(cols))
                cur.executemany(f"INSERT INTO `{table}` VALUES ({placeholders})", rows)
            conn.commit()
            logger.info(f"  >> {len(rows)} rows inserted into {table}")

    cur.close()
    conn.close()
    logger.info("MySQL setup completed successfully!")
    logger.info("Set USE_MYSQL=1 in .env and restart api.py")


if __name__ == "__main__":
    main()
