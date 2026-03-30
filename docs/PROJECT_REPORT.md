# LatencyAtlas — Project Report
**SLA Compliance and Response Variability Analysis using NYC 311 Service Requests**

---

## 1. Project Overview

LatencyAtlas is a decision-oriented business intelligence project that evaluates operational efficiency and SLA adherence across New York City agencies using real, API-sourced 311 service request data. The project is built around analytical correctness — business logic is enforced upstream in a layered SQL semantic layer, and the BI layer is kept strictly for visualization and decision-making.

The core question the project answers:

> *Are NYC agencies resolving service requests within acceptable timeframes, and where are the systemic failures?*

---

## 2. Data Source

| Property | Detail |
|----------|--------|
| Platform | NYC Open Data (Socrata) |
| Dataset | 311 Service Requests from 2020 to Present |
| Dataset ID | `erm2-nwe9` |
| Access Method | Socrata Open Data API via `sodapy` (Python) |
| Scope | 2021-01-01 to 2026-01-01 |
| Volume | Up to 20,000,000 records |
| Fields Ingested | `unique_key`, `created_date`, `closed_date`, `agency`, `agency_name`, `complaint_type`, `descriptor`, `status`, `borough` |

Data is ingested via authenticated API access using a Socrata app token stored in a `.env` file. Raw records are written directly to Parquet without any transformation at ingestion time.

---

## 3. Architecture

```
NYC Open Data API (Socrata)
        │
        ▼
  data_extract.py          <- API ingestion via sodapy
        │
        ▼
  NYC311.parquet            <- Immutable raw storage (columnar, compressed)
        │
        ▼
    build.py                <- Orchestrates DuckDB semantic layer construction
        │
        ▼
┌─────────────────────────────────┐
│         DuckDB (nyc_311.duckdb) │
│                                 │
│  v_raw          (01)            │
│  v_norm         (02)            │
│  v_sla_base     (03)            │
│  v_sla          (04)  <- final  │
└─────────────────────────────────┘
        │
        ▼
  mysql_setup.py           <- Populates MySQL summary tables from v_sla
        │
        ▼
┌─────────────────────────────────┐
│      MySQL (latencyatlas_db)    │
│                                 │
│  kpi_summary                    │
│  borough_breach                 │
│  agency_breach                  │
│  response_variability           │
│  complaint_types                │
│  monthly_trend                  │
└─────────────────────────────────┘
        │
        ▼
     api.py                <- Flask REST API serving aggregated JSON
        │
        ▼
  dashboard.html            <- Single-page BI dashboard (Chart.js)
        │
        ▼
  analysis.pbix             <- Power BI for deep-dive reporting
```

---

## 4. Storage Strategy

Raw data is stored in **Apache Parquet** format for the following reasons:

- Columnar layout enables fast analytical scans over specific fields without reading full rows
- Compressed on disk — significantly smaller than equivalent CSV
- Treated as **immutable** — raw files are never overwritten after ingestion, ensuring the source of truth can always be re-audited
- Queried directly by DuckDB via `read_parquet()` without any import step

CSV-based workflows are intentionally avoided throughout the pipeline.

---

## 5. Semantic Layer — SQL Views

The analytics layer is implemented as four layered DuckDB views, each with a single, well-defined responsibility. No view skips a layer — each builds strictly on the one below it.

### Layer 1 — `v_raw` (`01_raw_views.sql`)
Exposes the raw Parquet file as a SQL view with no filtering, casting, or transformation. Acts as the immutable source of truth within DuckDB. The Parquet path is injected at build time via a `{{DATA_PATH}}` placeholder.

### Layer 2 — `v_norm` (`02_norm_views.sql`)
Applies controlled semantic normalization:
- Casts `unique_key` to `BIGINT`
- Casts `created_date` and `closed_date` to `TIMESTAMP` as `created_ts` / `closed_ts`
- Derives `normalized_status` — maps raw status strings (`pending`, `in progress`, `assigned`, `open`, `started`) to `Open`, `Closed`, or `Unspecified`

No filtering or SLA logic is applied at this layer.

### Layer 3 — `v_sla_base` (`03_sla_base_views.sql`)
Enforces SLA eligibility:
- Filters to only `normalized_status = 'Closed'` records with a non-null `closed_ts`
- Derives `resolution_minutes` using `DATEDIFF('MINUTE', created_ts, closed_ts)`

Resolution time is calculated in **minutes** (not hours or days) to preserve maximum granularity for downstream bucketing.

### Layer 4 — `v_sla` (`04_sla_compliance_views.sql`)
Applies SLA classification using a `sla_config` CTE for configurable thresholds:

| Threshold | Minutes | Severity |
|-----------|---------|----------|
| <= 3 days | <= 4,320 | `Excellent` |
| <= 7 days | <= 10,080 | `Compliant` |
| <= 14 days | <= 20,160 | `Breach` |
| > 14 days | > 20,160 | `Extreme Breach` |

Derives two columns: `bucket` (time range label) and `severity` (compliance classification). The CTE-based config means SLA thresholds can be adjusted in one place without touching downstream logic.

**Compliant** = `Excellent` + `Compliant` severities  
**Breached** = `Breach` + `Extreme Breach` severities

---

## 6. MySQL Layer

`src/mysql_setup.py` reads from `v_sla` in DuckDB and writes pre-aggregated summary tables into MySQL. This separates the heavy OLAP computation (done once at setup time) from the live API queries (fast lookups against small summary tables).

### Tables

| Table | Rows | Description |
|-------|------|-------------|
| `kpi_summary` | 1 | Overall compliance rate, breach rate, total counts |
| `borough_breach` | 5 | Breach rate per NYC borough |
| `agency_breach` | 6 | Breach rate per agency (top 6 by volume) |
| `response_variability` | 5 | Avg, stddev, min, max resolution hours per borough |
| `complaint_types` | 8 | Breach rate per complaint type (top 8 by volume) |
| `monthly_trend` | 61 | Monthly compliance rate across full 2021–2026 scope |

Re-run `mysql_setup.py` any time the DuckDB layer is rebuilt to keep MySQL in sync.

---

## 7. API Layer

`src/api.py` is a Flask application that serves aggregated SLA data to the dashboard.

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Serves `dashboard.html` |
| `/api/dashboard` | GET | Returns full SLA payload as JSON |
| `/api/health` | GET | Backend connectivity check |

The API supports two backends, switchable via `USE_MYSQL` in `.env`:
- **MySQL** (default, `USE_MYSQL=1`) — queries pre-aggregated summary tables, fast for live dashboard use
- **DuckDB** (fallback) — queries `v_sla` directly if MySQL is unavailable

The payload includes: KPI summary, borough breach rates, agency breach rates, response variability, complaint type breakdown, and full monthly compliance trend (all years, no limit).

A `_sanitize_for_json()` utility recursively replaces Python `NaN`/`Infinity` values (which are invalid JSON) with `null` before serialization, preventing silent dashboard failures.

Flask's `static_folder` is explicitly pointed at the repo root `static/` directory so image assets resolve correctly regardless of where `api.py` is invoked from.

---

## 8. Dashboard

`dashboard.html` is a self-contained single-page dashboard served by Flask, built with **Chart.js** and no frontend framework dependencies.

### Pages
| Page | Status | Description |
|------|--------|-------------|
| Dashboard | Live | Main KPI bento grid |
| SLA Reports | Planned | Agency and complaint-type drill-downs |
| Borough Map | Planned | Choropleth breach heat map |
| Response Times | Planned | Percentile distribution and outlier analysis |
| Pipeline | Planned | Build logs, Parquet inventory, data freshness |

### Dashboard KPIs
- **SLA Compliance Rate** — donut chart showing compliant vs breached percentage
- **Breach Rate** — filterable by year (2022–2025); uses exact KPI rate for "All", derives from monthly trend for specific years
- **Avg Resolution Time** — mean resolution hours across all boroughs with sparkline trend
- **Best / Worst Agency** — lowest and highest breach rate agencies from live data
- **SLA Breach by Borough** — bar chart, highest breach borough highlighted in accent colour
- **5-Borough Coverage** — visual coverage indicator

### Behaviour
- Auto-refreshes every 5 minutes
- Falls back to mock data with "Demo mode" indicator if the API is unreachable
- Export CSV of borough breach data
- Year filter on breach card correctly shows `N/A` for years with no trend data rather than silently falling back

---

## 9. Repository Structure

```
LatencyAtlas/
├── src/
│   ├── api.py              # Flask API (MySQL + DuckDB backends)
│   ├── build.py            # DuckDB semantic layer builder
│   ├── data_extract.py     # Socrata API ingestion
│   └── mysql_setup.py      # MySQL table creation and population
├── sql/
│   ├── 01_raw_views.sql
│   ├── 02_norm_views.sql
│   ├── 03_sla_base_views.sql
│   └── 04_sla_compliance_views.sql
├── data/
│   └── NYC311.parquet      # Immutable raw data
├── static/
│   └── img/                # Dashboard image assets
├── docs/
│   ├── images/             # README and report assets
│   └── PROJECT_REPORT.md   # This file
├── logs/                   # build.log, data_fetch.log, mysql_setup.log
├── dashboard.html          # Single-page BI dashboard
├── analysis.pbix           # Power BI report
├── nyc_311.duckdb          # DuckDB database
├── requirements.txt
├── .env                    # Credentials and paths (not committed)
└── README.md
```

---

## 10. Running the Project

### First-time setup
```
pip install -r requirements.txt

python src/data_extract.py    # ingest raw data from Socrata API
python src/build.py           # build DuckDB semantic layer
python src/mysql_setup.py     # create and populate MySQL summary tables
python src/api.py             # start Flask API + dashboard
```

Open **http://localhost:5050**

### Day-to-day (data unchanged)
```
python src/api.py
```

### After re-ingesting data
```
python src/data_extract.py
python src/build.py
python src/mysql_setup.py
python src/api.py
```

### Environment variables (`.env`)
| Variable | Description |
|----------|-------------|
| `DATA_ROOT` | Absolute path to the repo root |
| `SOCRATA_APP_TOKEN` | NYC Open Data API token |
| `USE_MYSQL` | Set to `1` to use MySQL backend |
| `MYSQL_HOST` | MySQL host (default: `localhost`) |
| `MYSQL_USER` | MySQL user (default: `root`) |
| `MYSQL_PASSWORD` | MySQL password |
| `MYSQL_DATABASE` | MySQL database name (default: `latencyatlas_db`) |

---

## 11. Design Decisions

**Why DuckDB?**
DuckDB is an embedded OLAP engine that queries Parquet directly without a server process. For a single-analyst project with 20M rows, it provides near-instant aggregation without the overhead of Spark or a cloud warehouse.

**Why Parquet over CSV?**
Parquet's columnar layout means DuckDB only reads the columns it needs per query. For a 9-column, 20M-row dataset this is a significant I/O reduction. It also compresses better and preserves data types natively.

**Why MySQL for the live API?**
DuckDB aggregation over 20M rows takes several seconds per request. Pre-aggregating into MySQL summary tables reduces API response time to milliseconds. DuckDB remains the analytical source of truth; MySQL is purely a serving layer.

**Why push logic into SQL views rather than Python?**
SQL views are declarative, version-controlled, and auditable. Any analyst can read `04_sla_compliance_views.sql` and understand exactly how a "breach" is defined without reading application code. Power BI and the Flask API both consume the same `v_sla` view, ensuring a single source of truth for SLA logic.

**Why a configurable SLA threshold CTE?**
The `sla_config` CTE in `04_sla_compliance_views.sql` means the SLA thresholds (3 days / 7 days / 14 days) are defined in exactly one place. Changing the SLA definition requires editing one row, not hunting through application code.

---

## 12. Limitations and Future Work

| Area | Current State | Planned |
|------|--------------|------------|
| SLA thresholds | Uniform across all complaint types | Per-complaint-type thresholds |
| Borough Map | Placeholder page | Leaflet.js choropleth with GeoJSON |
| Response Times page | Placeholder | p50/p90/p99 percentile bands, outlier detection |
| SLA Reports page | Placeholder | Drill-down tables by agency and complaint type |
| Pipeline page | Placeholder | Live build log viewer, Parquet file inventory |
| Authentication | None | Role-based access for multi-user deployment |
| Scheduling | Manual runs | Automated ingestion via cron or Airflow |

---

## 13. Author

**Rehan Abdul Gani Shaikh**  
Data Science & ML Student | Python · Power BI | Building Real-World Data Projects

- LinkedIn: [rehan-shaikh-68153a246](https://www.linkedin.com/in/rehan-shaikh-68153a246)
- Email: rehansk.3107@gmail.com
- GitHub: [RehanShaikh-ai/LatencyAtlas](https://github.com/RehanShaikh-ai/LatencyAtlas)
