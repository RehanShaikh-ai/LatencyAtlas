import logging
import os
from pathlib import Path

import duckdb
from dotenv import load_dotenv

load_dotenv()

# <------------logging setup------------>
Path("logs").mkdir(exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[logging.FileHandler("logs/build.log"), logging.StreamHandler()],
)
logger = logging.getLogger(__name__)


DATA_ROOT = os.getenv("DATA_ROOT")
if not DATA_ROOT:
    raise RuntimeError("DATA_ROOT not defined")
DB_PATH = "nyc_311.duckdb"
SQL_DIR = Path("sql")


# <------------build logic------------>
def main():

    logger.info("======================================================")
    logger.info("Starting build")

    try:
        con = duckdb.connect(DB_PATH)
        con.execute(f"SET VARIABLE data_root = '{DATA_ROOT}/data'")

        SCRIPTS = [
            "01_raw_views.sql",
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
