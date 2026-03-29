import logging
import os
from pathlib import Path

import duckdb
from dotenv import load_dotenv

from data_extract import FILE_NAME

load_dotenv()

# <------------logging setup------------>

Path("logs").mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[logging.FileHandler("logs/build.log"), logging.StreamHandler()],
    force=True,
)

logger = logging.getLogger(__name__)

# <------------loading environment-defined parameters and constants------------>

# validate FIRST before using
_DATA_ROOT_RAW = os.getenv("DATA_ROOT")
if not _DATA_ROOT_RAW:
    raise RuntimeError("DATA_ROOT not defined in environment")

DATA_ROOT = Path(_DATA_ROOT_RAW)
DB_PATH = "nyc_311.duckdb"
SQL_DIR = Path("sql")

# consistent pathlib — no string concatenation
DATA_FILE = FILE_NAME
data_path = DATA_ROOT / "data" / DATA_FILE

SCRIPTS = [
    "02_norm_views.sql",
    "03_sla_base_views.sql",
    "04_sla_compliance_views.sql",
]

# <------------build logic------------>

def main():
    logger.info("======================================================")
    logger.info("Starting build")
    logger.info(f"Data path resolved to: {data_path}")

    # <------------raw data view setup for pure source of truth------------>
    raw_file = Path("sql/01_raw_views.sql").read_text()
    raw_file = raw_file.replace("{{DATA_PATH}}", str(data_path))

    # use context manager — auto closes connection even on crash
    try:
        with duckdb.connect(DB_PATH) as con:
            logger.info("Running build...Creating the raw data view")
            con.execute(raw_file)

            # <------------executing SQL layers------------>
            for n, script in enumerate(SCRIPTS, start=1):
                path = SQL_DIR / script
                logger.info(f"Running build...Executing script {n}/{len(SCRIPTS)}: {script}")
                sql = path.read_text()
                con.execute(sql)

        logger.info("Build completed successfully!")

    except Exception as e:
        logger.error("Build failed", exc_info=True)
        raise e


if __name__ == "__main__":
    main()