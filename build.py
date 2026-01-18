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
    force=True
)
logger = logging.getLogger(__name__)


DATA_ROOT = os.getenv("DATA_ROOT")
if not DATA_ROOT:
    raise RuntimeError("DATA_ROOT not defined")
DB_PATH = "nyc_311.duckdb"
SQL_DIR = Path("sql")
DATA_FILE = FILE_NAME

# <------------build logic------------>
def main():

    logger.info("======================================================")
    logger.info("Starting build")

    data_path = DATA_ROOT + "/data" + DATA_FILE
    raw_file = Path("sql/01_raw_views.sql").read_text()
    raw_file = raw_file.replace('{{DATA_PATH}}', data_path)

    try:
        con = duckdb.connect(DB_PATH)

        logger.info("Running build...Creating the raw data view")
        con.execute(raw_file)

        SCRIPTS = [
            "02_norm_views.sql",
            "03_sla_base_views.sql",
            "04_sla_compliance_views.sql",
        ]

        for n, script in zip(range(1, len(SCRIPTS) + 1), SCRIPTS):
            path = SQL_DIR / script
            logger.info(f"Running build...Executing script {n}/{len(SCRIPTS)}")

            sql = path.read_text()
            con.execute(sql)

        con.close()
        logger.info("Build completed !")

    except Exception as e:
        logger.error("Build failed", exc_info=True)
        raise e


if __name__ == "__main__":
    main()
