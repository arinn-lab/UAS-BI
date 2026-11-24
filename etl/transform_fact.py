"""
transform_fact.py
Load fakta operasional park (jadwal UTS 05:15, setelah load dimensi):
  dw.fact_crowd_daily  (1 baris = 1 park per hari)
  dw.fact_wait_time    (1 baris = 1 wahana per park per tahun)

Hanya baris yang lolos tahap transform_validasi yang dimuat. Baris valid yang
gagal lookup foreign key ditahan di stg.stg_rejected (aturan T21).
Load bersifat idempoten (upsert per kunci fakta), dalam satu transaksi per tabel.
"""
from datetime import datetime

from sqlalchemy import text

import config
from transform_validate import CALENDAR_CHK_CTE, RIDESTATS_CHK_CTE

logger = config.get_logger()

# ---------- fact_crowd_daily ----------
# T13: operating_minutes kosong diisi median park yang sama, pada hari dalam
# minggu yang sama, tahun yang sama; ditandai is_minutes_imputed = 1
CROWD_LOAD = CALENDAR_CHK_CTE + """
, cal AS (
    SELECT chk.*, CAST(chk."date" AS date) AS dt
    FROM chk WHERE chk.reason IS NULL
),
med AS (
    SELECT park_id, "year", day_of_week,
           percentile_cont(0.5) WITHIN GROUP (ORDER BY operating_minutes) AS med_min
    FROM cal
    WHERE operating_minutes IS NOT NULL
    GROUP BY park_id, "year", day_of_week
)
INSERT INTO dw.fact_crowd_daily
    (date_key, park_key, day_condition_key, crowd_level_pct, crowd_rel_to_year,
     operating_minutes, is_minutes_imputed, source_file)
SELECT
    d.date_key,
    p.park_key,
    dc.day_condition_key,
    cal.crowd_level_pct,
    cal.crowd_rel_to_year,
    COALESCE(cal.operating_minutes, m.med_min),
    CASE WHEN cal.operating_minutes IS NULL THEN 1 ELSE 0 END,
    cal.source_file
FROM cal
JOIN dw.dim_date d ON d.full_date = cal.dt
JOIN dw.dim_park p ON p.source_park_id = cal.park_id
JOIN dw.dim_day_condition dc
  ON dc.is_rainy = (CAST(cal.is_rainy AS numeric) = 1)
 AND dc.has_special_event = (CAST(cal.has_special_event AS numeric) = 1)
 AND dc.has_early_entry = (CAST(cal.has_early_entry AS numeric) = 1)
 AND dc.has_extended_evening = (CAST(cal.has_extended_evening AS numeric) = 1)
LEFT JOIN med m
  ON m.park_id = cal.park_id AND m."year" = cal."year"
 AND m.day_of_week = cal.day_of_week
ON CONFLICT (date_key, park_key) DO UPDATE SET
    day_condition_key = EXCLUDED.day_condition_key,
    crowd_level_pct = EXCLUDED.crowd_level_pct,
    crowd_rel_to_year = EXCLUDED.crowd_rel_to_year,
    operating_minutes = EXCLUDED.operating_minutes,
    is_minutes_imputed = EXCLUDED.is_minutes_imputed,
    source_file = EXCLUDED.source_file,
    load_ts = now()
"""

# baris valid yang tidak masuk fakta karena lookup dimensi gagal (T21)
CROWD_FK_REJECT = CALENDAR_CHK_CTE + """
INSERT INTO stg.stg_rejected (run_id, source_name, record_key, reason)
SELECT :run_id, 'calendar',
       CAST(chk.park_id AS text) || '|' || CAST(chk."date" AS text),
       'lookup foreign key gagal (dim_date/dim_park/dim_day_condition)'
FROM chk
WHERE chk.reason IS NULL
  AND NOT EXISTS (
      SELECT 1 FROM dw.fact_crowd_daily f
      JOIN dw.dim_date d ON d.date_key = f.date_key
      JOIN dw.dim_park p ON p.park_key = f.park_key
      WHERE d.full_date = CAST(chk."date" AS date)
        AND p.source_park_id = chk.park_id)
"""

# ---------- fact_wait_time ----------
# T18: pivot metric long -> wide (sudah di RIDESTATS_CHK_CTE); T19: max >= avg
WAIT_LOAD = RIDESTATS_CHK_CTE + """
INSERT INTO dw.fact_wait_time
    (year_key, park_key, ride_key, avg_wait_minutes, max_wait_minutes, source_file)
SELECT y.year_key, p.park_key, r.ride_key,
       chk.avg_min, chk.max_min, chk.source_file
FROM chk
JOIN dw.dim_year y ON CAST(y.year_number AS text) = chk.yr
JOIN dw.dim_park p ON p.source_park_id = chk.park_id
JOIN dw.dim_ride r ON r.ride_id = chk.ride_id
WHERE chk.reason IS NULL
ON CONFLICT (year_key, park_key, ride_key) DO UPDATE SET
    avg_wait_minutes = EXCLUDED.avg_wait_minutes,
    max_wait_minutes = EXCLUDED.max_wait_minutes,
    source_file = EXCLUDED.source_file,
    load_ts = now()
"""

WAIT_FK_REJECT = RIDESTATS_CHK_CTE + """
INSERT INTO stg.stg_rejected (run_id, source_name, record_key, reason)
SELECT :run_id, 'ridestats',
       chk.yr || '|' || CAST(chk.park_id AS text) || '|' || CAST(chk.ride_id AS text),
       'lookup foreign key gagal (dim_year/dim_park/dim_ride)'
FROM chk
WHERE chk.reason IS NULL
  AND NOT EXISTS (
      SELECT 1 FROM dw.fact_wait_time f
      JOIN dw.dim_year y ON y.year_key = f.year_key
      JOIN dw.dim_park p ON p.park_key = f.park_key
      JOIN dw.dim_ride r ON r.ride_key = f.ride_key
      WHERE CAST(y.year_number AS text) = chk.yr
        AND p.source_park_id = chk.park_id
        AND r.ride_id = chk.ride_id)
"""

# (tabel, sumber, sql load, sql reject FK, cte untuk hitung sumber)
FACT_STEPS = [
    ("fact_crowd_daily", "calendar", CROWD_LOAD, CROWD_FK_REJECT, CALENDAR_CHK_CTE),
    ("fact_wait_time", "ridestats", WAIT_LOAD, WAIT_FK_REJECT, RIDESTATS_CHK_CTE),
]


def load_facts(engine, run_id):
    summary = {}

    for table, source, load_sql, fk_reject_sql, cte in FACT_STEPS:
        started = datetime.now()
        step = f"load_{table}"
        try:
            with engine.begin() as conn:
                conn.execute(text(load_sql))
                conn.execute(text(
                    "DELETE FROM stg.stg_rejected WHERE source_name = :s "
                    "AND reason LIKE 'lookup foreign key%'"), {"s": source})
                conn.execute(text(fk_reject_sql), {"run_id": run_id})

                rows_in = conn.execute(text(cte + "SELECT COUNT(*) FROM chk")).scalar()
                rows_out = conn.execute(text(f"SELECT COUNT(*) FROM dw.{table}")).scalar()
                rejected = conn.execute(
                    text("SELECT COUNT(*) FROM stg.stg_rejected WHERE source_name = :s"),
                    {"s": source},
                ).scalar()

                config.write_dq(conn, run_id, "rekonsiliasi baris sumber vs fakta",
                                f"dw.{table}", rows_in, rows_in - rows_out - rejected,
                                f"sumber={rows_in}, dimuat={rows_out}, ditolak={rejected}")

                if table == "fact_crowd_daily":
                    imputed = conn.execute(text(
                        "SELECT COUNT(*) FROM dw.fact_crowd_daily "
                        "WHERE is_minutes_imputed = 1"
                    )).scalar()
                    config.write_dq(conn, run_id, "jam operasional diimputasi (median)",
                                    f"dw.{table}", rows_out, imputed,
                                    f"{imputed} baris ditandai is_minutes_imputed = 1")
                    logger.info("%s | baris imputasi jam operasional = %d", step, imputed)

            logger.info("%s | in=%d out=%d rejected=%d | OK",
                        step, rows_in, rows_out, rejected)
            config.write_audit(
                engine, run_id, step, source, rows_in, rows_out, rejected,
                "SUCCESS", f"stg.stg_{source} -> dw.{table}", started,
            )
            summary[table] = rows_out

        except Exception as exc:
            logger.error("%s | GAGAL | %s", step, exc)
            config.write_audit(
                engine, run_id, step, source, None, None, None,
                "FAILED", str(exc)[:1500], started,
            )
            raise

    return summary
