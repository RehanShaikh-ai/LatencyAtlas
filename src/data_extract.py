import logging
import os
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from sodapy import Socrata

_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(dotenv_path=_ROOT / ".env")

(_ROOT / "logs").mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[logging.FileHandler(_ROOT / "logs/data_fetch.log"), logging.StreamHandler()],
)
logger = logging.getLogger(__name__)

client = Socrata("data.cityofnewyork.us", app_token=os.getenv("SOCRATA_APP_TOKEN"))

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

DATA_ROOT = os.getenv("DATA_ROOT")
if not DATA_ROOT:
    raise RuntimeError("DATA_ROOT not defined")
DATA_ROOT = Path(DATA_ROOT)
DATA_DIR = DATA_ROOT / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

FILE_NAME = "NYC311.parquet"
path = DATA_DIR / FILE_NAME


def main():
    try:
        logger.info("Extracting data...")
        results = client.get("erm2-nwe9", query=query)

        logger.info("Converting to PARQUET format...")
        df = pd.DataFrame.from_records(results)
        df.to_parquet(path, index=False)
        logger.info(f"Data fetch completed! Data saved at {path}")

    except Exception as e:
        logger.error("Data fetch failed", exc_info=True)
        raise e


if __name__ == "__main__":
    main()
