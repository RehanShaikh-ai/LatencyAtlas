# NYC 311 SLA Analytics

![Python](https://img.shields.io/badge/Python-3.x-blue)
![DuckDB](https://img.shields.io/badge/DuckDB-Analytics-orange)
![License](https://img.shields.io/badge/License-MIT-green)
![Status](https://img.shields.io/badge/Status-Work%20in%20Progress-yellow)

A decision-oriented BI project analyzing SLA compliance and operational performance using real NYC 311 service request data.  
Built with API-driven ingestion and a modern analytics-first architecture.

## Project Objective

To evaluate operational efficiency and SLA adherence across NYC agencies using real, API-sourced data.  
The project is intentionally framed around analytical rigor, pushing heavy logic upstream and keeping BI tools focused on decision-making visuals.

## Data Source

- Platform: NYC Open Data (Socrata)
- Dataset: 311 Service Requests
- Dataset ID: `erm2-nwe9`
- Access Method: Socrata API via Python (`sodapy`)
- Data Scope: Time-scoped operational slice (explicitly framed, not full historical analysis)

## Architecture

NYC Open Data API  
        ↓  
Python (sodapy)  
        ↓  
Parquet (raw, immutable)  
        ↓  
DuckDB (views + aggregations)  
        ↓  
Power BI (visualization only)

## Storage Strategy

- Raw data stored in Parquet for columnar, compressed analytics
- Raw files treated as immutable
- CSV-based workflows intentionally avoided

## Analytics Layer

- DuckDB used as the analytical SQL engine (OLAP)
- Parquet queried directly without import
- Business logic implemented via SQL views:
  - Base data cleaning and derived metrics
  - SLA classification logic
  - Aggregated, BI-ready summary views

## **👤 Author**

**Rehan Abdul Gani Shaikh**
**Data Science & ML Student | Python • Power BI | Building Real-World Data Projects**

🔗 Connect with me:  [LinkedIn](https://www.linkedin.com/in/rehan-shaikh-68153a246)  

📬 Email: rehansk.3107@gmail.com
