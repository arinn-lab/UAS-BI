"""
retensi.py
Kebijakan retensi dari tabel Storage UTS:
  stg    : data mentah 90 hari (arsip file sumber permanen di object storage)
  audit  : 24 bulan
  dw     : permanen (tidak dihapus)
  mart   : view, dibangun ulang tiap refresh
  backup : 30 hari (diatur di backup.py)
Dijalankan harian setelah backup.
"""
from datetime import datetime

from sqlalchemy import inspect, text

import config

logger = config.get_logger()

STAGING = ["stg_booking", "stg_calendar", "stg_ridestats"]


def apply_retention(engine, run_id):
    started = datetime.now()
    hasil = {}
    ada = set(inspect(engine).get_table_names(schema="stg"))
    with engine.begin() as conn:
        for t in STAGING:
            if t in ada:
                hasil[t] = conn.execute(text(
                    f"DELETE FROM stg.{t} WHERE extracted_at < now() - "
                    f"make_interval(days => :d)"), {"d": config.RETENSI_STAGING_HARI}).rowcount
        hasil["stg_rejected"] = conn.execute(text(
            "DELETE FROM stg.stg_rejected WHERE rejected_at < now() - "
            "make_interval(days => :d)"), {"d": config.RETENSI_STAGING_HARI}).rowcount
        hasil["etl_log"] = conn.execute(text(
            "DELETE FROM audit.etl_log WHERE started_at < now() - "
            "make_interval(months => :m)"), {"m": config.RETENSI_AUDIT_BULAN}).rowcount
        hasil["data_quality_log"] = conn.execute(text(
            "DELETE FROM audit.data_quality_log WHERE checked_at < now() - "
            "make_interval(months => :m)"), {"m": config.RETENSI_AUDIT_BULAN}).rowcount

    pesan = ("baris dihapus: " + ", ".join(f"{k}={v}" for k, v in hasil.items())
             + f" | aturan: stg {config.RETENSI_STAGING_HARI} hari, "
               f"audit {config.RETENSI_AUDIT_BULAN} bulan")
    logger.info("retensi_data | %s | OK", pesan)
    config.write_audit(engine, run_id, "retensi_data", "stg+audit", None, None,
                       sum(hasil.values()), "SUCCESS", pesan, started)
    return hasil
