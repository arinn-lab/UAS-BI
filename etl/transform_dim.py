"""
transform_dim.py
Load dimensi (jadwal UTS 05:00, setelah transform dan validasi sukses).
Isi 9 tabel dimensi di schema dw dari staging, sesuai urutan Load Process UTS:
  1. Dim_Date            generate kalender 2025-2026; is_holiday dari calendar
  2. Dim_Year, Dim_Park  seed (2 tahun, 4 park dengan alias Vistaland)
  3. Dim_Customer, Dim_Package, Dim_Channel_Promo, Dim_Event
                         kombinasi unik dari booking (SCD Type 1)
  4. Dim_Day_Condition   kombinasi unik penanda hari dari calendar
  5. Dim_Ride            SCD Type 1, satu baris per ride_id
Aman dijalankan berulang karena memakai ON CONFLICT.
"""
from datetime import datetime

from sqlalchemy import text

import config

logger = config.get_logger()

# alias nama park Vistaland (tabel alias pada rancangan UTS).
# park_name = label presentasi; source_park_name dan source_park_id tetap
# disimpan supaya data bisa ditelusuri ke sumber.
PARK_ALIAS = {
    "Magic Kingdom": "Vista Kingdom",
    "Epcot": "Vista Discovery",
    "Hollywood Studios": "Vista Studios",
    "Animal Kingdom": "Vista Wildlands",
}
_alias_case = " ".join(f"WHEN '{src}' THEN '{alias}'" for src, alias in PARK_ALIAS.items())

DIM_STEPS = [
    # SCD Type 0: kalender statis; season mengikuti pembagian musim pada sumber
    ("dim_date", """
        INSERT INTO dw.dim_date
            (date_key, full_date, day, month, month_name, quarter,
             year, day_of_week, is_weekend, is_holiday, season)
        SELECT
            CAST(to_char(g.d, 'YYYYMMDD') AS INTEGER),
            CAST(g.d AS date),
            EXTRACT(day FROM g.d),
            EXTRACT(month FROM g.d),
            TRIM(to_char(g.d, 'Month')),
            EXTRACT(quarter FROM g.d),
            EXTRACT(year FROM g.d),
            TRIM(to_char(g.d, 'Day')),
            EXTRACT(isodow FROM g.d) IN (6, 7),
            COALESCE(h.is_holiday, false),
            CASE
                WHEN EXTRACT(month FROM g.d) IN (12, 1, 2) THEN 'Winter'
                WHEN EXTRACT(month FROM g.d) IN (3, 4, 5)  THEN 'Spring'
                WHEN EXTRACT(month FROM g.d) IN (6, 7, 8)  THEN 'Summer'
                ELSE 'Fall'
            END
        FROM generate_series(DATE '2025-01-01', DATE '2026-12-31',
                             INTERVAL '1 day') AS g(d)
        LEFT JOIN (
            SELECT CAST("date" AS date) AS dt,
                   BOOL_OR(CAST(is_holiday AS numeric) = 1) AS is_holiday
            FROM stg.stg_calendar
            WHERE "year" IN (2025, 2026)
            GROUP BY 1
        ) h ON h.dt = CAST(g.d AS date)
        ON CONFLICT (date_key) DO UPDATE SET is_holiday = EXCLUDED.is_holiday
    """),

    ("dim_year", """
        INSERT INTO dw.dim_year (year_key, year_number)
        SELECT y, y FROM (VALUES (2025), (2026)) AS v(y)
        ON CONFLICT (year_key) DO NOTHING
    """),

    # seed 4 park + pemetaan alias; SCD Type 1 (nama ditimpa kalau berubah)
    ("dim_park", f"""
        INSERT INTO dw.dim_park (source_park_id, park_name, source_park_name)
        SELECT park_id,
               CASE MIN(park_name) {_alias_case} ELSE MIN(park_name) END,
               MIN(park_name)
        FROM (
            SELECT park_id, park_name FROM stg.stg_calendar
            WHERE "year" IN (2025, 2026)
            UNION
            SELECT park_id, park_name FROM stg.stg_ridestats
            WHERE CAST("year" AS text) IN ('2025', '2026')
        ) t
        GROUP BY park_id
        ON CONFLICT (source_park_id) DO UPDATE SET
            park_name = EXCLUDED.park_name,
            source_park_name = EXCLUDED.source_park_name
    """),

    ("dim_customer", """
        INSERT INTO dw.dim_customer
            (customer_state, customer_segment, first_time_guest)
        SELECT DISTINCT
            TRIM("CustomerState"),
            TRIM("CustomerSegment"),
            TRIM("FirstTimeGuest") = 'Yes'
        FROM stg.stg_booking
        WHERE "CustomerState" IS NOT NULL AND "CustomerSegment" IS NOT NULL
        ON CONFLICT DO NOTHING
    """),

    ("dim_package", """
        INSERT INTO dw.dim_package
            (resort_category, ticket_days, park_hopper, lightning_lane, dining_plan)
        SELECT DISTINCT
            TRIM("ResortCategory"),
            "TicketDays",
            TRIM("ParkHopper") = 'Yes',
            TRIM("LightningLane") = 'Yes',
            TRIM("DiningPlan") = 'Yes'
        FROM stg.stg_booking
        WHERE "ResortCategory" IS NOT NULL AND "TicketDays" IS NOT NULL
        ON CONFLICT DO NOTHING
    """),

    # T03: Promotion kosong -> 'Tanpa Promo'
    ("dim_channel_promo", """
        INSERT INTO dw.dim_channel_promo (sales_channel, promotion)
        SELECT DISTINCT
            TRIM("SalesChannel"),
            COALESCE(NULLIF(NULLIF(TRIM("Promotion"), ''), 'None'), 'Tanpa Promo')
        FROM stg.stg_booking
        WHERE "SalesChannel" IS NOT NULL
        ON CONFLICT DO NOTHING
    """),

    # T04: SpecialEvent kosong -> 'Tanpa Event'
    ("dim_event", """
        INSERT INTO dw.dim_event (event_name)
        SELECT DISTINCT
            COALESCE(NULLIF(NULLIF(TRIM("SpecialEvent"), ''), 'None'), 'Tanpa Event')
        FROM stg.stg_booking
        ON CONFLICT (event_name) DO NOTHING
    """),

    # T15: junk dimension dari kombinasi unik penanda hari di stg_calendar
    ("dim_day_condition", """
        INSERT INTO dw.dim_day_condition
            (is_rainy, has_special_event, has_early_entry, has_extended_evening)
        SELECT DISTINCT
            CAST(is_rainy AS numeric) = 1,
            CAST(has_special_event AS numeric) = 1,
            CAST(has_early_entry AS numeric) = 1,
            CAST(has_extended_evening AS numeric) = 1
        FROM stg.stg_calendar
        WHERE is_rainy IS NOT NULL AND has_special_event IS NOT NULL
          AND has_early_entry IS NOT NULL AND has_extended_evening IS NOT NULL
        ON CONFLICT DO NOTHING
    """),

    # T20: SCD Type 1, satu baris per ride_id; status arsip = snapshot sumber
    ("dim_ride", """
        INSERT INTO dw.dim_ride (ride_id, ride_name, is_archived)
        SELECT ride_id,
               MIN(ride_name),
               MAX(CAST(is_archived AS numeric)) = 1
        FROM stg.stg_ridestats
        WHERE CAST("year" AS text) IN ('2025', '2026')
        GROUP BY ride_id
        ON CONFLICT (ride_id) DO UPDATE SET
            ride_name = EXCLUDED.ride_name,
            is_archived = EXCLUDED.is_archived
    """),
]


def load_dimensions(engine, run_id):
    summary = {}

    for table, sql in DIM_STEPS:
        started = datetime.now()
        step = f"load_{table}"
        try:
            with engine.begin() as conn:
                conn.execute(text(sql))
                total = conn.execute(
                    text(f"SELECT COUNT(*) FROM dw.{table}")
                ).scalar()

            logger.info("%s | baris di dw.%s = %d | OK", step, table, total)
            config.write_audit(
                engine, run_id, step, "stg", None, total, 0,
                "SUCCESS", f"stg -> dw.{table}", started,
            )
            summary[table] = total

        except Exception as exc:
            logger.error("%s | GAGAL | %s", step, exc)
            config.write_audit(
                engine, run_id, step, "stg", None, None, None,
                "FAILED", str(exc)[:1500], started,
            )
            raise

    config.write_audit(engine, run_id, "load_dimensi", "stg", None,
                       sum(summary.values()), 0, "SUCCESS",
                       f"9 dimensi dimuat: {summary}", datetime.now())
    return summary
