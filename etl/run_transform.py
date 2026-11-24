"""
run_transform.py
Menjalankan tahap setelah extract saja. Staging dipakai dari extract terakhir.

    python etl/run_transform.py            semua tahap
    python etl/run_transform.py validasi   transform dan validasi saja
    python etl/run_transform.py dim        load dimensi saja
    python etl/run_transform.py fakta      load ketiga fakta saja
    python etl/run_transform.py mart       refresh data mart + validasi
"""
import sys
import uuid
from datetime import datetime

from sqlalchemy import inspect

import config
import pipeline
import transform_dim
import transform_validate

logger = config.get_logger()

PILIHAN = ("semua", "validasi", "dim", "fakta", "mart")


def staging_belum_ada(engine):
    perlu = ["stg_booking", "stg_calendar", "stg_ridestats"]
    ada = inspect(engine).get_table_names(schema="stg")
    return [t for t in perlu if t not in ada]


def main():
    tahap = sys.argv[1] if len(sys.argv) > 1 else "semua"
    if tahap not in PILIHAN:
        print("Pilihan tidak dikenal:", tahap)
        print("Pilih salah satu dari:", ", ".join(PILIHAN))
        return 1

    run_id = str(uuid.uuid4())
    started = datetime.now()
    logger.info("=== TRANSFORM DIMULAI (tahap=%s) | run_id=%s ===", tahap, run_id)

    try:
        engine = config.get_engine()
        hilang = staging_belum_ada(engine)
        if hilang:
            raise RuntimeError(
                "Tabel staging belum ada: %s. Jalankan python etl/run_etl.py "
                "dulu supaya extract mengisi staging." % ", ".join(hilang))

        if tahap in ("semua", "validasi"):
            transform_validate.validate_staging(engine, run_id)
        if tahap in ("semua", "dim"):
            transform_dim.load_dimensions(engine, run_id)
        if tahap in ("semua", "fakta"):
            pipeline.load_all_facts(engine, run_id)
        if tahap in ("semua", "mart"):
            pipeline.refresh_mart(engine, run_id)
            pipeline.validate_source_mart(engine, run_id)

        logger.info("=== TRANSFORM SELESAI | durasi %s ===", datetime.now() - started)
        return 0

    except Exception as exc:
        logger.error("=== TRANSFORM BERHENTI KARENA ERROR: %s ===", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
