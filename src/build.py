import logging
import os
from pathlib import Path

import duckdb
from dotenv import load_dotenv

from data_extract import FILE_NAME

_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(dotenv_path=_ROOT / ".env")

# <------------logging setup------------>

(_ROOT / "logs").mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[logging.FileHandler(_ROOT / "logs/build.log"), logging.StreamHandler()],
    force=True,
)

logger = logging.getLogger(__name__)

# <------------loading environment-defined parameters and constants------------>

_DATA_ROOT_RAW = os.getenv("DATA_ROOT")
if not _DATA_ROOT_RAW:
    raise RuntimeError("DATA_ROOT not defined in environment")

DATA_ROOT = Path(_DATA_ROOT_RAW)
DB_PATH = _ROOT / "nyc_311.duckdb"
SQL_DIR = _ROOT / "sql"

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

    raw_file = (SQL_DIR / "01_raw_views.sql").read_text()
    raw_file = raw_file.replace("{{DATA_PATH}}", str(data_path))

    try:
        with duckdb.connect(str(DB_PATH)) as con:
            logger.info("Running build...Creating the raw data view")
            con.execute(raw_file)

            for n, script in enumerate(SCRIPTS, start=1):
                path = SQL_DIR / script
                logger.info(f"Running build...Executing script {n}/{len(SCRIPTS)}: {script}")
                con.execute(path.read_text())

        logger.info("Build completed successfully!")

    except Exception as e:
        logger.error("Build failed", exc_info=True)
        raise e


if __name__ == "__main__":
    main()
