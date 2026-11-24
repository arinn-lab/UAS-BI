"""
transform_booking.py
Load fakta booking (jadwal UTS 05:15, setelah load dimensi):
  dw.fact_booking (1 baris = 1 booking; booking_id = PK, degenerate dimension)

Hanya baris yang lolos tahap transform_validasi yang dimuat. Aturan yang
diterapkan saat load:
  T06 promo_valid_flag   = 0 kalau promo Florida Resident tapi CustomerState <> FL
  T07 total_guests       = Adult + Child; lead_time_days = Arrival - Purchase
  T08 CrowdLevel dan CapacityUtilization tidak dimuat (tetap di staging)
  T09 Month dan Season tidak dimuat (diambil dari Dim_Date)
  T10 trim teks dan standardisasi Yes/No
  T21 baris valid yang gagal lookup foreign key ditahan di stg_rejected
Load idempoten: upsert berdasarkan booking_id, dalam satu transaksi.
"""
from datetime import datetime

from sqlalchemy import text

import config
from transform_validate import BOOKING_CHK_CTE

logger = config.get_logger()

PROMO_EXPR = "COALESCE(NULLIF(NULLIF(TRIM(c.\"Promotion\"), ''), 'None'), 'Tanpa Promo')"
EVENT_EXPR = "COALESCE(NULLIF(NULLIF(TRIM(c.\"SpecialEvent\"), ''), 'None'), 'Tanpa Event')"

LOAD_INSERT = BOOKING_CHK_CTE + f"""
INSERT INTO dw.fact_booking
    (booking_id, arrival_date_key, purchase_date_key, customer_key,
     package_key, channel_promo_key, event_key,
     adult_guests, child_guests, total_guests, trip_length, lead_time_days,
     ticket_revenue, hotel_revenue, addon_revenue, total_revenue,
     promo_valid_flag, source_file)
SELECT
    TRIM(c."BookingID"),
    da.date_key,
    dp.date_key,
    cu.customer_key,
    pk.package_key,
    cpr.channel_promo_key,
    ev.event_key,
    c."AdultGuests",
    c."ChildGuests",
    c."AdultGuests" + c."ChildGuests",
    c."TripLength",
    (c.adate - c.pdate),
    c."TicketRevenue",
    c."HotelRevenue",
    c."AddonRevenue",
    c."TotalRevenue",
    CASE WHEN TRIM(c."Promotion") = 'Florida Resident'
              AND TRIM(c."CustomerState") <> 'FL'
         THEN 0 ELSE 1 END,
    c.source_file
FROM chk c
JOIN dw.dim_date da ON da.full_date = c.adate
JOIN dw.dim_date dp ON dp.full_date = c.pdate
JOIN dw.dim_customer cu
  ON cu.customer_state = TRIM(c."CustomerState")
 AND cu.customer_segment = TRIM(c."CustomerSegment")
 AND cu.first_time_guest = (TRIM(c."FirstTimeGuest") = 'Yes')
JOIN dw.dim_package pk
  ON pk.resort_category = TRIM(c."ResortCategory")
 AND pk.ticket_days = c."TicketDays"
 AND pk.park_hopper = (TRIM(c."ParkHopper") = 'Yes')
 AND pk.lightning_lane = (TRIM(c."LightningLane") = 'Yes')
 AND pk.dining_plan = (TRIM(c."DiningPlan") = 'Yes')
JOIN dw.dim_channel_promo cpr
  ON cpr.sales_channel = TRIM(c."SalesChannel")
 AND cpr.promotion = {PROMO_EXPR}
JOIN dw.dim_event ev
  ON ev.event_name = {EVENT_EXPR}
WHERE c.reason IS NULL
ON CONFLICT (booking_id) DO UPDATE SET
    arrival_date_key = EXCLUDED.arrival_date_key,
    purchase_date_key = EXCLUDED.purchase_date_key,
    customer_key = EXCLUDED.customer_key,
    package_key = EXCLUDED.package_key,
    channel_promo_key = EXCLUDED.channel_promo_key,
    event_key = EXCLUDED.event_key,
    adult_guests = EXCLUDED.adult_guests,
    child_guests = EXCLUDED.child_guests,
    total_guests = EXCLUDED.total_guests,
    trip_length = EXCLUDED.trip_length,
    lead_time_days = EXCLUDED.lead_time_days,
    ticket_revenue = EXCLUDED.ticket_revenue,
    hotel_revenue = EXCLUDED.hotel_revenue,
    addon_revenue = EXCLUDED.addon_revenue,
    total_revenue = EXCLUDED.total_revenue,
    promo_valid_flag = EXCLUDED.promo_valid_flag,
    source_file = EXCLUDED.source_file,
    load_ts = now()
"""

# T21: baris lolos validasi tetapi tidak masuk fakta = lookup dimensi gagal
FK_REJECT = BOOKING_CHK_CTE + """
INSERT INTO stg.stg_rejected (run_id, source_name, record_key, reason)
SELECT :run_id, 'booking', TRIM(c."BookingID"),
       'lookup foreign key gagal (dimensi tidak ditemukan)'
FROM chk c
WHERE c.reason IS NULL
  AND NOT EXISTS (SELECT 1 FROM dw.fact_booking f
                  WHERE f.booking_id = TRIM(c."BookingID"))
"""


def one(conn, sql):
    return conn.execute(text(sql)).scalar()


def load_booking(engine, run_id):
    started = datetime.now()
    step = "load_fact_booking"
    try:
        with engine.begin() as conn:
            conn.execute(text(LOAD_INSERT))
            conn.execute(text(
                "DELETE FROM stg.stg_rejected WHERE source_name = 'booking' "
                "AND reason LIKE 'lookup foreign key%'"))
            conn.execute(text(FK_REJECT), {"run_id": run_id})

            rows_in = one(conn, BOOKING_CHK_CTE + "SELECT COUNT(*) FROM chk")
            rows_out = one(conn, "SELECT COUNT(*) FROM dw.fact_booking")
            rejected = one(conn, "SELECT COUNT(*) FROM stg.stg_rejected "
                                 "WHERE source_name = 'booking'")
            unaccounted = rows_in - rows_out - rejected

            # cek 1: semua baris staging harus dimuat atau ditolak
            config.write_dq(conn, run_id, "rekonsiliasi jumlah baris", "dw.fact_booking",
                            rows_in, unaccounted,
                            f"staging={rows_in}, dimuat={rows_out}, ditolak={rejected}, "
                            f"tidak terhitung={unaccounted}")

            # cek 2: total revenue baris valid di staging vs DWH
            rev_stg = one(conn, BOOKING_CHK_CTE +
                          'SELECT COALESCE(SUM(CAST("TotalRevenue" AS numeric)), 0) '
                          "FROM chk WHERE reason IS NULL")
            rev_dw = one(conn, "SELECT COALESCE(SUM(total_revenue), 0) FROM dw.fact_booking")
            selisih = abs(rev_stg - rev_dw)
            config.write_dq(conn, run_id, "total revenue staging vs DWH", "dw.fact_booking",
                            rows_in, 0 if selisih <= 0.01 else 1,
                            f"stg={rev_stg:.2f}, dw={rev_dw:.2f}, selisih={selisih:.2f}")

            promo_bad = one(conn, "SELECT COUNT(*) FROM dw.fact_booking "
                                  "WHERE promo_valid_flag = 0")

        logger.info("%s | in=%d out=%d rejected=%d tidak_terhitung=%d | OK",
                    step, rows_in, rows_out, rejected, unaccounted)
        logger.info("%s | revenue stg=%.2f dw=%.2f | promo tidak valid=%d",
                    step, rev_stg, rev_dw, promo_bad)
        config.write_audit(
            engine, run_id, step, "booking", rows_in, rows_out, rejected, "SUCCESS",
            f"stg.stg_booking -> dw.fact_booking | promo_valid_flag=0: {promo_bad}",
            started,
        )
        return {"fact_booking": rows_out}

    except Exception as exc:
        logger.error("%s | GAGAL | %s", step, exc)
        config.write_audit(
            engine, run_id, step, "booking", None, None, None,
            "FAILED", str(exc)[:1500], started,
        )
        raise
