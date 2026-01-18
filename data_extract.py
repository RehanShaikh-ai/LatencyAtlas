import logging
import os
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from sodapy import Socrata  # API library for data

load_dotenv()  # load .env with env variables

Path("logs").mkdir(exist_ok=True)

# configuring logging format
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[logging.FileHandler("logs/data_fetch.log"), logging.StreamHandler()],
)
logger = logging.getLogger(__name__)


client = Socrata("data.cityofnewyork.us", app_token=os.getenv("SOCRATA_APP_TOKEN"))

# <------------fetch data from 2021-2025------------>
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
LIMIT 20000000 
"""

# Data directory and filename
DATA_ROOT = Path(os.getenv("DATA_ROOT"))  # fetches from .env
DATA_DIR = DATA_ROOT / "data"

if not DATA_ROOT:  # directory check
    raise RuntimeError("DATA_ROOT not defined")

DATA_DIR.mkdir(parents=True, exist_ok=True)  # creates the data directory
FILE_NAME = "NYC311.parquet"
path = DATA_DIR / FILE_NAME  # final location of the file

try:

    logger.info("Extracting data...")
    results = client.get("erm2-nwe9", query=query)

    logger.info("Converting to PARQUET format...")
    df = pd.DataFrame.from_records(results)  # convert to DataFrame
    df.to_parquet(path, index=False)  # Convert to PARQUET format for faster read
    logger.info(f"Data fetch completed ! Data saved at {path}")

except Exception as e:
    logger.error("Data fetch failed", exc_info=True)
    raise e
