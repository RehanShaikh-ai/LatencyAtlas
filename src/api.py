"""
LatencyAtlas — Live Dashboard API
──────────────────────────────────
Serves SLA summary data to dashboard.html.

- Default: DuckDB (nyc_311.duckdb + v_sla), no MySQL required.
- Optional: set USE_MYSQL=1 and MySQL env vars to use pre-aggregated tables.

Run: python api.py
Dashboard: http://localhost:5050/
"""

import logging
import math
import os
from datetime import datetime
from decimal import Decimal
from pathlib import Path

import duckdb
import mysql.connector
import pandas as pd
from dotenv import load_dotenv
from flask import Flask, jsonify, send_from_directory
from flask_cors import CORS

_ROOT = Path(__file__).resolve().parent.parent
DUCKDB_PATH = Path(os.getenv("DUCKDB_PATH", str(_ROOT / "nyc_311.duckdb")))

load_dotenv(dotenv_path=_ROOT / ".env")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger(__name__)

app = Flask(__name__, static_folder=str(_ROOT / "static"), static_url_path="/static")
CORS(app)

MYSQL_CONFIG = {
    "host": os.getenv("MYSQL_HOST", "localhost"),
    "user": os.getenv("MYSQL_USER", "root"),
    "password": os.getenv("MYSQL_PASSWORD", ""),
    "database": os.getenv("MYSQL_DATABASE", "latencyatlas_db"),
}

_USE_MYSQL = os.getenv("USE_MYSQL", "0").lower() in ("1", "true", "yes")

# Severity in v_sla: Excellent / Compliant = on track; Breach / Extreme Breach = not
_COMPLIANT = "severity IN ('Excellent', 'Compliant')"
_BREACHED = "severity IN ('Breach', 'Extreme Breach')"


def _sanitize_for_json(obj):
    """
    Browsers reject JSON.parse() on Python's NaN/Infinity tokens. Recursively
    replace non-finite floats and normalize numpy/Decimal scalars.
    """
    if obj is None:
        return None
    if isinstance(obj, dict):
        return {k: _sanitize_for_json(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_sanitize_for_json(v) for v in obj]
    if isinstance(obj, bool):
        return obj
    if isinstance(obj, int) and not isinstance(obj, bool):
        return obj
    if isinstance(obj, Decimal):
        try:
            x = float(obj)
            return None if (math.isnan(x) or math.isinf(x)) else x
        except (TypeError, ValueError):
            return None
    if isinstance(obj, float):
        return None if (math.isnan(obj) or math.isinf(obj)) else obj
    try:
        import numpy as np

        if isinstance(obj, (np.integer, np.int64, np.int32)):
            return int(obj)
        if isinstance(obj, (np.floating, np.float64)):
            x = float(obj)
            return None if (math.isnan(x) or math.isinf(x)) else x
    except ImportError:
        pass
    if hasattr(obj, "item"):
        try:
            return _sanitize_for_json(obj.item())
        except (ValueError, TypeError, AttributeError):
            return None
    return obj


def _use_mysql() -> bool:
    return _USE_MYSQL


def get_mysql_conn():
    return mysql.connector.connect(**MYSQL_CONFIG)


def mysql_query(sql: str) -> list[dict]:
    conn = get_mysql_conn()
    cursor = conn.cursor(dictionary=True)
    cursor.execute(sql)
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    return rows


def _df_to_records(df: pd.DataFrame) -> list[dict]:
    """Make pandas/numpy values JSON-serializable."""
    if df.empty:
        return []
    records = df.to_dict("records")
    for row in records:
        for k, v in list(row.items()):
            if v is None or (isinstance(v, float) and pd.isna(v)):
                row[k] = None
            elif isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
                row[k] = None
            elif hasattr(v, "item"):
                try:
                    row[k] = v.item()
                except (ValueError, AttributeError):
                    pass
    return records


def duckdb_query(con: duckdb.DuckDBPyConnection, sql: str) -> list[dict]:
    df = con.execute(sql).fetchdf()
    return _df_to_records(df)


def build_payload_mysql() -> dict:
    sla_rows = mysql_query("SELECT total_requests AS total, compliant, breached, compliance_rate FROM kpi_summary LIMIT 1")
    sla = sla_rows[0] if sla_rows else {}

    borough_rows = mysql_query("SELECT borough, total, breached, breach_rate FROM borough_breach ORDER BY breach_rate DESC")

    agency_rows = mysql_query("SELECT agency_name, total, breached, breach_rate FROM agency_breach ORDER BY breached DESC")

    variability_rows = mysql_query("SELECT borough, avg_hrs, stddev_hrs, min_hrs, max_hrs FROM response_variability ORDER BY avg_hrs DESC")

    complaint_rows = mysql_query("SELECT complaint_type, total, breached, breach_rate FROM complaint_types ORDER BY total DESC")

    trend_rows = mysql_query("SELECT month, compliance_rate FROM monthly_trend ORDER BY month ASC")

    return _assemble_payload(
        sla,
        borough_rows,
        agency_rows,
        variability_rows,
        complaint_rows,
        trend_rows,
        "MySQL — LatencyAtlas pipeline",
    )


def build_payload_duckdb(con: duckdb.DuckDBPyConnection) -> dict:
    sla_rows = duckdb_query(
        con,
        f"""
        SELECT
            COUNT(*)::BIGINT AS total,
            SUM(CASE WHEN {_COMPLIANT} THEN 1 ELSE 0 END)::BIGINT AS compliant,
            SUM(CASE WHEN {_BREACHED} THEN 1 ELSE 0 END)::BIGINT AS breached,
            ROUND(
                100.0 * SUM(CASE WHEN {_COMPLIANT} THEN 1 ELSE 0 END) / NULLIF(COUNT(*), 0),
                2
            ) AS compliance_rate
        FROM v_sla
        """,
    )
    sla = sla_rows[0] if sla_rows else {}

    borough_rows = duckdb_query(
        con,
        f"""
        SELECT
            borough,
            COUNT(*)::BIGINT AS total,
            SUM(CASE WHEN {_BREACHED} THEN 1 ELSE 0 END)::BIGINT AS breached,
            ROUND(
                100.0 * SUM(CASE WHEN {_BREACHED} THEN 1 ELSE 0 END) / NULLIF(COUNT(*), 0),
                2
            ) AS breach_rate
        FROM v_sla
        WHERE borough IS NOT NULL AND borough != 'Unspecified'
        GROUP BY borough
        ORDER BY breach_rate DESC
        """,
    )

    agency_rows = duckdb_query(
        con,
        f"""
        SELECT
            agency_name,
            COUNT(*)::BIGINT AS total,
            SUM(CASE WHEN {_BREACHED} THEN 1 ELSE 0 END)::BIGINT AS breached,
            ROUND(
                100.0 * SUM(CASE WHEN {_BREACHED} THEN 1 ELSE 0 END) / NULLIF(COUNT(*), 0),
                2
            ) AS breach_rate
        FROM v_sla
        GROUP BY agency_name
        ORDER BY breached DESC
        LIMIT 6
        """,
    )

    variability_rows = duckdb_query(
        con,
        """
        SELECT
            borough,
            ROUND(AVG(resolution_minutes) / 60.0, 2) AS avg_hrs,
            ROUND(STDDEV_SAMP(resolution_minutes) / 60.0, 2) AS stddev_hrs,
            ROUND(MIN(resolution_minutes) / 60.0, 2) AS min_hrs,
            ROUND(MAX(resolution_minutes) / 60.0, 2) AS max_hrs
        FROM v_sla
        WHERE borough IS NOT NULL AND borough != 'Unspecified'
        GROUP BY borough
        ORDER BY avg_hrs DESC
        """,
    )

    complaint_rows = duckdb_query(
        con,
        f"""
        SELECT
            complaint_type,
            COUNT(*)::BIGINT AS total,
            SUM(CASE WHEN {_BREACHED} THEN 1 ELSE 0 END)::BIGINT AS breached,
            ROUND(
                100.0 * SUM(CASE WHEN {_BREACHED} THEN 1 ELSE 0 END) / NULLIF(COUNT(*), 0),
                2
            ) AS breach_rate
        FROM v_sla
        GROUP BY complaint_type
        ORDER BY total DESC
        LIMIT 8
        """,
    )

    trend_rows = duckdb_query(
        con,
        f"""
        SELECT
            strftime(created_ts, '%Y-%m') AS month,
            ROUND(
                100.0 * SUM(CASE WHEN {_COMPLIANT} THEN 1 ELSE 0 END) / NULLIF(COUNT(*), 0),
                2
            ) AS compliance_rate
        FROM v_sla
        GROUP BY month
        ORDER BY month ASC
        """,
    )

    return _assemble_payload(
        sla,
        borough_rows,
        agency_rows,
        variability_rows,
        complaint_rows,
        trend_rows,
        "DuckDB — v_sla (LatencyAtlas build)",
    )


def _assemble_payload(
    sla: dict,
    borough_rows: list,
    agency_rows: list,
    variability_rows: list,
    complaint_rows: list,
    trend_rows: list,
    source: str,
) -> dict:
    cr = float(sla.get("compliance_rate") or 0)
    return {
        "meta": {
            "generated_at": datetime.utcnow().isoformat() + "Z",
            "source": source,
        },
        "kpi": {
            "total_requests": int(sla.get("total") or 0),
            "compliant": int(sla.get("compliant") or 0),
            "breached": int(sla.get("breached") or 0),
            "compliance_rate": cr,
            "breach_rate": round(100 - cr, 2),
        },
        "borough_breach": borough_rows,
        "agency_breach": agency_rows,
        "variability": variability_rows,
        "complaint_types": complaint_rows,
        "trend": trend_rows,
    }


@app.route("/", methods=["GET"])
def index():
    return send_from_directory(_ROOT, "dashboard.html")


@app.route("/api/dashboard", methods=["GET"])
def dashboard():
    if _use_mysql():
        try:
            payload = build_payload_mysql()
            logger.info("Dashboard payload (MySQL) OK")
            return jsonify(_sanitize_for_json(payload)), 200
        except Exception as e:
            logger.warning("MySQL unavailable (%s); trying DuckDB", e)

    if not DUCKDB_PATH.is_file():
        msg = (
            f"DuckDB file not found: {DUCKDB_PATH}. "
            "Run build.py (DATA_ROOT in .env) or set DUCKDB_PATH / USE_MYSQL=1."
        )
        logger.error(msg)
        return jsonify({"error": msg}), 503

    try:
        with duckdb.connect(str(DUCKDB_PATH), read_only=True) as con:
            payload = build_payload_duckdb(con)
        logger.info("Dashboard payload (DuckDB) OK")
        return jsonify(_sanitize_for_json(payload)), 200
    except Exception as e:
        logger.error("Dashboard API error", exc_info=True)
        return jsonify({"error": str(e)}), 500


@app.route("/api/health", methods=["GET"])
def health():
    if _use_mysql():
        try:
            conn = get_mysql_conn()
            conn.close()
            return jsonify({"status": "ok", "backend": "mysql", "db": "connected"}), 200
        except Exception as e:
            return jsonify({"status": "error", "backend": "mysql", "detail": str(e)}), 503

    if not DUCKDB_PATH.is_file():
        return jsonify(
            {
                "status": "error",
                "backend": "duckdb",
                "detail": f"missing file {DUCKDB_PATH}",
            }
        ), 503

    try:
        with duckdb.connect(str(DUCKDB_PATH), read_only=True) as con:
            con.execute("SELECT 1 FROM v_sla LIMIT 1")
        return jsonify({"status": "ok", "backend": "duckdb", "db": "connected"}), 200
    except Exception as e:
        return jsonify({"status": "error", "backend": "duckdb", "detail": str(e)}), 503


if __name__ == "__main__":
    logger.info("Starting LatencyAtlas API on http://localhost:5050")
    logger.info(
        "Backend: %s (set USE_MYSQL=1 for MySQL)",
        "MySQL" if _use_mysql() else f"DuckDB ({DUCKDB_PATH})",
    )
    app.run(host="0.0.0.0", port=5050, debug=False)
