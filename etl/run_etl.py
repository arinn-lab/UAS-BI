"""
run_etl.py
Menjalankan seluruh pipeline secara berurutan tanpa menunggu jadwal
(dipakai untuk run pertama, demo, atau mengejar data setelah pemulihan):
    python etl/run_etl.py

Urutan sama dengan jadwal Airflow di UTS:
extract booking, calendar, ridestats -> transform dan validasi -> load dimensi
-> load fakta -> refresh data mart -> validasi source vs mart.
"""
import sys
import uuid
from datetime import datetime

import config
import extract
import pipeline
import transform_dim
import transform_validate

logger = config.get_logger()


def main():
    run_id = str(uuid.uuid4())
    started = datetime.now()
    logger.info("=== ETL DIMULAI | run_id=%s ===", run_id)

    try:
        engine = config.get_engine()
        for name in extract.SOURCES:
            extract.extract_source(engine, run_id, name)
        transform_validate.validate_staging(engine, run_id)
        transform_dim.load_dimensions(engine, run_id)
        pipeline.load_all_facts(engine, run_id)
        pipeline.refresh_mart(engine, run_id)
        pipeline.validate_source_mart(engine, run_id)
        logger.info("=== ETL SELESAI | durasi %s ===", datetime.now() - started)
        return 0

    except config.DataQualityError as exc:
        logger.error("=== ETL DIHENTIKAN (kualitas data): %s ===", exc)
        return 2
    except Exception as exc:
        logger.error("=== ETL BERHENTI KARENA ERROR: %s ===", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
