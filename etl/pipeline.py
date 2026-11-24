"""
pipeline.py
Tahap-tahap pipeline setelah load fakta, plus pengecekan dependensi antar
tahap. Dipakai oleh DAG Airflow dan run manual (run_etl.py).

  refresh_mart            -> bangun ulang view data mart (05:30)
  validate_source_mart    -> rekonsiliasi staging vs DWH vs data mart
  check_timeliness        -> data harian harus siap sebelum 06:00 (Orlando)
  send_steward_summary    -> ringkasan harian baris ditolak ke Data Steward
  stage_ready             -> apakah tahap sebelumnya sudah SUCCESS (untuk sensor)
"""
from datetime import datetime
from decimal import Decimal

from sqlalchemy import text

import config
import notify
from transform_validate import BOOKING_CHK_CTE, CALENDAR_CHK_CTE, RIDESTATS_CHK_CTE

logger = config.get_logger()

# dependensi antar tahap sesuai tabel Scheduling UTS.
# (step, batas jam). None = cukup pernah sukses (ridestats diperbarui bulanan).
DEPENDENCIES = {
    "transform_validasi": [("extract_booking", 20), ("extract_calendar", 20),
                           ("extract_ridestats", None)],
    "load_dimensi": [("transform_validasi", 20)],
    "load_fakta": [("load_dimensi", 20)],
    "refresh_mart": [("load_fakta", 20)],
}


def stage_ready(engine, stage):
    """True kalau semua tahap yang dibutuhkan `stage` sudah SUCCESS."""
    for step, hours in DEPENDENCIES[stage]:
        if config.last_success(engine, step, within_hours=hours) is None:
            logger.info("menunggu %s: %s belum SUCCESS", stage, step)
            return False
    return True


def refresh_mart(engine, run_id):
    """Bangun ulang view data mart dari sql/02_mart_dan_validasi.sql."""
    started = datetime.now()
    sql = (config.SQL_DIR / "02_mart_dan_validasi.sql").read_text(encoding="utf-8")
    raw = engine.raw_connection()
    try:
        cur = raw.cursor()
        cur.execute(sql)
        raw.commit()
    except Exception as exc:
        raw.rollback()
        config.write_audit(engine, run_id, "refresh_mart", "sql/02_mart_dan_validasi.sql",
                           None, None, None, "FAILED", str(exc)[:1500], started)
        raise
    finally:
        raw.close()

    config.write_audit(engine, run_id, "refresh_mart", "sql/02_mart_dan_validasi.sql",
                       None, None, 0, "SUCCESS", "view schema mart dibuat ulang", started)


def _one(conn, sql):
    return conn.execute(text(sql)).scalar()


def validate_source_mart(engine, run_id):
    """Validasi Source -> DWH -> Data Mart untuk ketiga fakta."""
    started = datetime.now()
    gagal = []

    with engine.begin() as conn:
        # ---------- booking ----------
        stg_baris = _one(conn, 'SELECT COUNT(*) FROM stg.stg_booking')
        ditolak = _one(conn, "SELECT COUNT(*) FROM stg.stg_rejected "
                             "WHERE source_name = 'booking'")
        rev_stg = _one(conn, 'SELECT COALESCE(SUM(CAST("TotalRevenue" AS numeric)), 0) '
                             'FROM stg.stg_booking')
        mart_baris = _one(conn, "SELECT COUNT(*) FROM mart.v_sales_revenue")
        rev_mart = _one(conn, "SELECT COALESCE(SUM(total_revenue), 0) FROM mart.v_sales_revenue")
        fakta_baris = _one(conn, "SELECT COUNT(*) FROM dw.fact_booking")
        # setiap booking valid di staging harus ada di mart dengan revenue yang sama
        hilang = _one(conn, BOOKING_CHK_CTE + """
            SELECT COUNT(*) FROM chk c
            WHERE c.reason IS NULL AND NOT EXISTS (
                SELECT 1 FROM mart.v_sales_revenue m
                WHERE m.booking_id = TRIM(c."BookingID")
                  AND ABS(m.total_revenue - CAST(c."TotalRevenue" AS numeric)) <= 0.01)""")

        if hilang or mart_baris != fakta_baris:
            gagal.append(f"booking: {hilang} baris valid tidak cocok di mart")
        config.write_dq(conn, run_id, "validasi booking staging vs mart",
                        "mart.v_sales_revenue", stg_baris, hilang,
                        f"stg={stg_baris}, ditolak={ditolak}, dw={fakta_baris}, "
                        f"mart={mart_baris}, revenue stg={rev_stg} mart={rev_mart}")

        # ---------- crowd harian ----------
        crowd_stg = _one(conn, CALENDAR_CHK_CTE + "SELECT COUNT(*) FROM chk WHERE reason IS NULL")
        crowd_avg_stg = _one(conn, CALENDAR_CHK_CTE +
                             "SELECT ROUND(AVG(crowd_level_pct)::numeric, 4) FROM chk "
                             "WHERE reason IS NULL")
        crowd_mart = _one(conn, "SELECT COUNT(*) FROM mart.v_park_operations")
        crowd_avg_mart = _one(conn, "SELECT ROUND(AVG(crowd_level_pct)::numeric, 4) "
                                    "FROM mart.v_park_operations")
        crowd_beda = (crowd_stg != crowd_mart
                      or Decimal(crowd_avg_stg or 0) != Decimal(crowd_avg_mart or 0))
        if crowd_beda:
            gagal.append("crowd: jumlah baris atau rata-rata berbeda")
        config.write_dq(conn, run_id, "validasi crowd staging vs mart",
                        "mart.v_park_operations", crowd_stg, 1 if crowd_beda else 0,
                        f"stg valid={crowd_stg}, mart={crowd_mart}, avg crowd "
                        f"stg={crowd_avg_stg} mart={crowd_avg_mart}")

        # ---------- waktu tunggu ----------
        wait_stg = _one(conn, RIDESTATS_CHK_CTE + "SELECT COUNT(*) FROM chk WHERE reason IS NULL")
        wait_mart = _one(conn, "SELECT COUNT(*) FROM mart.v_wait_time")
        if wait_stg != wait_mart:
            gagal.append("waktu tunggu: jumlah baris berbeda")
        config.write_dq(conn, run_id, "validasi waktu tunggu staging vs mart",
                        "mart.v_wait_time", wait_stg, abs(wait_stg - wait_mart),
                        f"stg valid={wait_stg}, mart={wait_mart}")

    status = "FAILED" if gagal else "SUCCESS"
    pesan = (f"baris stg={stg_baris} ditolak={ditolak} mart={mart_baris} | "
             f"revenue stg={rev_stg} mart={rev_mart} | crowd stg={crowd_stg} "
             f"mart={crowd_mart} | wait stg={wait_stg} mart={wait_mart}")
    config.write_audit(engine, run_id, "validasi_source_mart", "mart",
                       stg_baris, mart_baris, ditolak, status, pesan, started)
    logger.info("validasi_source_mart | %s | %s", status, pesan)
    if gagal:
        raise ValueError("Validasi source vs mart gagal: " + "; ".join(gagal))
    return pesan


def check_timeliness(engine, run_id, batas_jam=6):
    """Aturan kualitas 'Ketepatan waktu': data harian tersedia sebelum 06:00
    waktu Orlando. Kalau terlambat: dicatat WARN dan email ke Data Engineer."""
    started = datetime.now()
    sekarang = config.now_operasional()
    tepat = sekarang.hour < batas_jam
    pesan = (f"data mart siap pukul {sekarang:%H:%M} {sekarang.tzname()} "
             f"(batas {batas_jam:02d}:00)")
    with engine.begin() as conn:
        config.write_dq(conn, run_id, "ketepatan waktu data harian", "mart",
                        1, 0 if tepat else 1, pesan)
    config.write_audit(engine, run_id, "cek_ketepatan_waktu", "mart", None, None, None,
                       "SUCCESS" if tepat else "WARN", pesan, started)
    if not tepat:
        try:
            notify.send_email("Data harian terlambat",
                              f"{pesan}\nrun_id={run_id}\nPeriksa DAG Vistaland di Airflow.",
                              ["engineer"])
        except Exception as exc:          # noqa: BLE001
            logger.error("email ketepatan waktu gagal dikirim: %s", exc)
    return tepat


def send_steward_summary(engine, run_id):
    """Ringkasan harian untuk Data Steward: baris ditolak per sumber dan
    alasan, pengecekan kualitas yang WARN/FAIL dalam 24 jam, dan promo yang
    perlu ditinjau Marketing."""
    started = datetime.now()
    with engine.connect() as conn:
        ditolak = conn.execute(text(
            "SELECT source_name, reason, COUNT(*) FROM stg.stg_rejected "
            "GROUP BY 1, 2 ORDER BY 1, 3 DESC")).fetchall()
        # hasil TERBARU tiap pengecekan dalam 24 jam (tidak diulang per run)
        dq = conn.execute(text(
            "SELECT check_name, table_name, status, detail FROM ("
            "  SELECT DISTINCT ON (check_name, table_name) check_name, table_name,"
            "         status, detail, checked_at"
            "  FROM audit.data_quality_log"
            "  WHERE checked_at >= now() - interval '24 hours'"
            "  ORDER BY check_name, table_name, checked_at DESC) t "
            "WHERE status <> 'PASS' ORDER BY checked_at DESC")).fetchall()
        promo = conn.execute(text(
            "SELECT COUNT(*) FILTER (WHERE promo_valid_flag = 0), "
            "COUNT(*) FILTER (WHERE promotion <> 'Tanpa Promo') "
            "FROM mart.v_sales_revenue")).fetchone()

    baris = ["Ringkasan kualitas data harian Vistaland DWH", f"run_id: {run_id}", ""]
    baris.append("1. Baris ditolak (stg.stg_rejected):")
    baris += [f"   - {s}: {n} baris | {r}" for s, r, n in ditolak] or ["   - tidak ada"]
    baris.append("")
    baris.append("2. Pengecekan WARN/FAIL dalam 24 jam terakhir:")
    baris += [f"   - [{st}] {c} ({t}): {d}" for c, t, st, d in dq] or ["   - tidak ada"]
    baris.append("")
    baris.append(f"3. Booking promo perlu ditinjau Marketing: {promo[0]} "
                 f"dari {promo[1]} booking berpromo (promo_valid_flag = 0)")
    body = "\n".join(baris)

    try:
        notify.send_email("Ringkasan kualitas data harian", body, ["steward"])
        status, pesan = "SUCCESS", f"email ringkasan terkirim ({len(ditolak)} jenis penolakan)"
    except Exception as exc:              # noqa: BLE001
        status, pesan = "WARN", f"email ringkasan gagal dikirim: {exc}"
        logger.error(pesan)
    config.write_audit(engine, run_id, "ringkasan_data_steward", "audit", None, None,
                       None, status, pesan, started)
    return body


def load_all_facts(engine, run_id):
    """Load ketiga fakta (jadwal 05:15) lalu tandai tahap 'load_fakta' selesai."""
    import transform_booking
    import transform_fact

    started = datetime.now()
    hasil = transform_fact.load_facts(engine, run_id)
    hasil.update(transform_booking.load_booking(engine, run_id))
    config.write_audit(engine, run_id, "load_fakta", "stg", None, sum(hasil.values()),
                       None, "SUCCESS", f"3 fakta dimuat: {hasil}", started)
    return hasil