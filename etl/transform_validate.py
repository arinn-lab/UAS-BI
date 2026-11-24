"""
transform_validate.py
Tahap "Transform dan validasi" (jadwal UTS 04:30, setelah seluruh extract).

Menjalankan aturan kualitas data UTS pada staging SEBELUM data dimuat ke DWH:
  - baris yang melanggar aturan ditahan di stg.stg_rejected beserta alasannya
    (T01, T02, T05, T12, T19, T21 dan aturan kelengkapan kunci)
  - hasil tiap pengecekan dicatat di audit.data_quality_log
  - kalau baris ditolak > 1% dari total pada salah satu sumber, tahap ini
    gagal dengan DataQualityError: load fakta tidak dijalankan dan data lama
    di DWH tetap dipakai (tabel Error Handling UTS)

Aturan CTE di bawah juga dipakai tahap load, supaya baris yang dimuat persis
baris yang lolos validasi.
"""
from datetime import datetime

from sqlalchemy import text

import config

logger = config.get_logger()

# ---------------- booking ----------------
# Rentang tanggal sama dengan Dim_Date (1 Jan 2025 - 31 Des 2026)
BOOKING_CHK_CTE = """
WITH b AS (
    SELECT s.*,
           CAST(s."PurchaseDate" AS date) AS pdate,
           CAST(s."ArrivalDate" AS date) AS adate,
           ROW_NUMBER() OVER (PARTITION BY TRIM(s."BookingID")
                              ORDER BY s.extracted_at DESC) AS rn
    FROM stg.stg_booking s
),
chk AS (
    SELECT b.*,
           CASE
               WHEN b."BookingID" IS NULL OR TRIM(b."BookingID") = ''
                    OR b.pdate IS NULL OR b.adate IS NULL
                   THEN 'BookingID atau tanggal kosong'
               WHEN b.rn > 1
                   THEN 'BookingID duplikat (dipakai versi terbaru)'
               WHEN b.adate < b.pdate
                   THEN 'ArrivalDate lebih awal dari PurchaseDate'
               WHEN ABS(b."TotalRevenue" - (b."TicketRevenue" + b."HotelRevenue"
                        + b."AddonRevenue")) > 0.01
                   THEN 'TotalRevenue tidak sama dengan jumlah komponen'
               WHEN b.pdate NOT BETWEEN DATE '2025-01-01' AND DATE '2026-12-31'
                    OR b.adate NOT BETWEEN DATE '2025-01-01' AND DATE '2026-12-31'
                   THEN 'tanggal di luar rentang Dim_Date'
           END AS reason
    FROM b
)
"""

# ---------------- calendar (dipakai 2025-2026, aturan T11) ----------------
CALENDAR_CHK_CTE = """
WITH chk AS (
    SELECT c.*,
           CASE
               WHEN c.park_id IS NULL OR c."date" IS NULL
                   THEN 'park_id atau tanggal kosong'
               WHEN c.crowd_level_pct IS NULL
                    OR c.crowd_level_pct NOT BETWEEN 0 AND 100
                   THEN 'crowd_level_pct kosong atau di luar 0-100'
           END AS reason
    FROM stg.stg_calendar c
    WHERE c."year" IN (2025, 2026)
)
"""

# ---------------- ridestats (aturan T16-T19) ----------------
# all_time bukan tahun, jadi tidak ikut (tetap tersimpan di staging)
RIDESTATS_CHK_CTE = """
WITH piv AS (
    SELECT CAST(s."year" AS text) AS yr, s.park_id, s.ride_id,
           MAX(CASE WHEN s.metric = 'ride_avg_wait' THEN s.minutes END) AS avg_min,
           MAX(CASE WHEN s.metric = 'ride_max_wait' THEN s.minutes END) AS max_min,
           MAX(s.source_file) AS source_file
    FROM stg.stg_ridestats s
    WHERE CAST(s."year" AS text) IN ('2025', '2026')
    GROUP BY 1, 2, 3
),
chk AS (
    SELECT piv.*,
           CASE
               WHEN piv.park_id IS NULL OR piv.ride_id IS NULL
                   THEN 'park_id atau ride_id kosong'
               WHEN piv.avg_min IS NULL OR piv.max_min IS NULL
                   THEN 'avg/max waktu tunggu kosong'
               WHEN piv.max_min < piv.avg_min
                   THEN 'max_wait lebih kecil dari avg_wait'
           END AS reason
    FROM piv
)
"""

CHECKS = {
    "booking": {
        "cte": BOOKING_CHK_CTE,
        "key": "COALESCE(TRIM(c.\"BookingID\"), '(kosong)')",
        "table": "stg.stg_booking",
    },
    "calendar": {
        "cte": CALENDAR_CHK_CTE,
        "key": "CAST(c.park_id AS text) || '|' || CAST(c.\"date\" AS text)",
        "table": "stg.stg_calendar (2025-2026)",
    },
    "ridestats": {
        "cte": RIDESTATS_CHK_CTE,
        "key": "c.yr || '|' || CAST(c.park_id AS text) || '|' || CAST(c.ride_id AS text)",
        "table": "stg.stg_ridestats (pivot 2025-2026)",
    },
}


def validate_staging(engine, run_id):
    """Jalankan semua aturan validasi. Return ringkasan per sumber.
    Lempar config.DataQualityError kalau ambang 1% terlampaui."""
    started = datetime.now()
    step = "transform_validasi"
    summary, melanggar = {}, []

    try:
        with engine.begin() as conn:
            for source, chk in CHECKS.items():
                cte = chk["cte"]
                conn.execute(text("DELETE FROM stg.stg_rejected WHERE source_name = :s"),
                             {"s": source})
                conn.execute(text(
                    cte + f"""
                    INSERT INTO stg.stg_rejected (run_id, source_name, record_key, reason)
                    SELECT :run_id, :s, {chk['key']}, c.reason
                    FROM chk c WHERE c.reason IS NOT NULL
                    """), {"run_id": run_id, "s": source})

                total = conn.execute(text(cte + "SELECT COUNT(*) FROM chk")).scalar()
                rejected = conn.execute(text(
                    "SELECT COUNT(*) FROM stg.stg_rejected WHERE source_name = :s"),
                    {"s": source}).scalar()
                rasio = rejected / total if total else 0.0
                lewat = rasio > config.REJECT_THRESHOLD

                config.write_dq(
                    conn, run_id, "ambang baris ditolak (maks 1%)", chk["table"],
                    total, rejected,
                    f"ditolak={rejected} dari {total} ({rasio:.2%}), "
                    f"ambang={config.REJECT_THRESHOLD:.0%}",
                    status="FAIL" if lewat else ("WARN" if rejected else "PASS"))

                summary[source] = {"total": total, "ditolak": rejected,
                                   "rasio": round(rasio, 4)}
                if lewat:
                    melanggar.append(f"{source} {rejected}/{total} ({rasio:.2%})")

            # pemantauan promo (T06): tidak ditolak, hanya ditandai
            promo_total = conn.execute(text(
                "SELECT COUNT(*) FROM stg.stg_booking "
                "WHERE TRIM(\"Promotion\") = 'Florida Resident'")).scalar()
            promo_bad = conn.execute(text(
                "SELECT COUNT(*) FROM stg.stg_booking "
                "WHERE TRIM(\"Promotion\") = 'Florida Resident' "
                "AND TRIM(\"CustomerState\") <> 'FL'")).scalar()
            config.write_dq(
                conn, run_id, "promo Florida Resident bukan dari FL",
                "stg.stg_booking", promo_total, promo_bad,
                f"{promo_bad} dari {promo_total} booking Florida Resident akan "
                "ditandai promo_valid_flag = 0 (dilaporkan ke Marketing)")

        total_rej = sum(v["ditolak"] for v in summary.values())
        total_in = sum(v["total"] for v in summary.values())
        pesan = " | ".join(f"{k}: {v['ditolak']}/{v['total']}" for k, v in summary.items())

        if melanggar:
            pesan = "AMBANG 1% TERLAMPAUI, load fakta dihentikan: " + "; ".join(melanggar)
            logger.error("%s | %s", step, pesan)
            config.write_audit(engine, run_id, step, "stg", total_in, None,
                               total_rej, "FAILED", pesan, started)
            raise config.DataQualityError(pesan)

        logger.info("%s | ditolak per sumber %s | OK", step, pesan)
        config.write_audit(engine, run_id, step, "stg", total_in,
                           total_in - total_rej, total_rej, "SUCCESS", pesan, started)
        return summary

    except config.DataQualityError:
        raise
    except Exception as exc:
        logger.error("%s | GAGAL | %s", step, exc)
        config.write_audit(engine, run_id, step, "stg", None, None, None,
                           "FAILED", str(exc)[:1500], started)
        raise
