-- 02_mart_dan_validasi.sql
-- Data mart (view) untuk dashboard, lalu query validasi sumber vs mart.
-- Dijalankan otomatis oleh tahap refresh_mart (user vl_engineer).
-- Kalau dijalankan manual, pakai user vl_engineer atau admin.
--
-- Dua area data mart sesuai rancangan UTS:
--   Sales & Revenue   -> mart.v_sales_revenue          (Fact_Booking)
--   Park Operations   -> mart.v_park_operations         (Fact_Crowd_Daily)
--                        mart.v_wait_time               (Fact_Wait_Time)
-- Schema mart sudah dibuat oleh 01_schema.sql.

-- ================= MART SALES & REVENUE (1 baris = 1 booking) =================
CREATE OR REPLACE VIEW mart.v_sales_revenue AS
SELECT
    f.booking_id,
    da.full_date      AS arrival_date,
    da.year           AS arrival_year,
    da.month          AS arrival_month,
    da.month_name     AS arrival_month_name,
    da.quarter        AS arrival_quarter,
    da.season         AS arrival_season,
    da.day_of_week    AS arrival_day_of_week,
    da.is_weekend     AS arrival_is_weekend,
    da.is_holiday     AS arrival_is_holiday,
    dp.full_date      AS purchase_date,
    c.customer_state,
    c.customer_segment,
    c.first_time_guest,
    p.resort_category,
    p.ticket_days,
    p.park_hopper,
    p.lightning_lane,
    p.dining_plan,
    cp.sales_channel,
    cp.promotion,
    e.event_name,
    f.adult_guests,
    f.child_guests,
    f.total_guests,
    f.trip_length,
    f.lead_time_days,
    f.ticket_revenue,
    f.hotel_revenue,
    f.addon_revenue,
    f.total_revenue,
    -- measure turunan dihitung di mart, bukan disimpan di fakta
    ROUND(f.total_revenue / NULLIF(f.total_guests, 0), 2)  AS revenue_per_guest,
    ROUND(f.total_revenue / NULLIF(p.ticket_days, 0), 2)   AS revenue_per_ticket_day,
    f.promo_valid_flag
FROM dw.fact_booking f
JOIN dw.dim_date da ON da.date_key = f.arrival_date_key
JOIN dw.dim_date dp ON dp.date_key = f.purchase_date_key
JOIN dw.dim_customer c ON c.customer_key = f.customer_key
JOIN dw.dim_package p ON p.package_key = f.package_key
JOIN dw.dim_channel_promo cp ON cp.channel_promo_key = f.channel_promo_key
JOIN dw.dim_event e ON e.event_key = f.event_key;

-- ================= MART PARK OPERATIONS: crowd harian (1 baris = 1 park per hari) =================
-- operating_minutes_observed hanya berisi data asli (tanpa imputasi),
-- sesuai definisi KPI Operating Minutes di UTS.
CREATE OR REPLACE VIEW mart.v_park_operations AS
SELECT
    d.full_date,
    d.year,
    d.month,
    d.month_name,
    d.season,
    d.day_of_week,
    d.is_weekend,
    d.is_holiday,
    pk.park_name,
    pk.source_park_name,
    dc.is_rainy,
    dc.has_special_event,
    dc.has_early_entry,
    dc.has_extended_evening,
    f.crowd_level_pct,
    f.crowd_rel_to_year,
    f.operating_minutes,
    (f.is_minutes_imputed = 1) AS operating_minutes_missing,
    CASE WHEN f.is_minutes_imputed = 1 THEN NULL
         ELSE f.operating_minutes END AS operating_minutes_observed
FROM dw.fact_crowd_daily f
JOIN dw.dim_date d ON d.date_key = f.date_key
JOIN dw.dim_park pk ON pk.park_key = f.park_key
JOIN dw.dim_day_condition dc ON dc.day_condition_key = f.day_condition_key;

-- ================= MART PARK OPERATIONS: waktu tunggu (1 baris = 1 wahana per park per tahun) =================
CREATE OR REPLACE VIEW mart.v_wait_time AS
SELECT
    y.year_number AS year,
    pk.park_name,
    pk.source_park_name,
    r.ride_id,
    r.ride_name,
    CASE WHEN r.is_archived THEN 'Archived' ELSE 'Active' END AS ride_status,
    f.avg_wait_minutes,
    f.max_wait_minutes
FROM dw.fact_wait_time f
JOIN dw.dim_year y ON y.year_key = f.year_key
JOIN dw.dim_park pk ON pk.park_key = f.park_key
JOIN dw.dim_ride r ON r.ride_key = f.ride_key;

-- ================= STATUS DATA (untuk keterangan "data terakhir diperbarui") =================
-- Dashboard login sebagai viewer yang tidak boleh membaca schema audit.
-- View ini hanya membuka ringkasan kecil dari audit.etl_log: kapan data mart
-- terakhir berhasil diperbarui dan hasil validasi source vs mart terakhir.
CREATE OR REPLACE VIEW mart.v_status_data AS
SELECT
    (SELECT MAX(finished_at) FROM audit.etl_log
      WHERE step = 'refresh_mart' AND status = 'SUCCESS')          AS mart_diperbarui,
    (SELECT status FROM audit.etl_log
      WHERE step = 'validasi_source_mart'
      ORDER BY log_id DESC LIMIT 1)                                 AS status_validasi,
    (SELECT finished_at FROM audit.etl_log
      WHERE step = 'validasi_source_mart'
      ORDER BY log_id DESC LIMIT 1)                                 AS waktu_validasi;

-- view dimiliki role_engineer, supaya refresh berikutnya (oleh vl_engineer)
-- tetap boleh mengganti view walaupun pernah dibuat oleh admin
ALTER VIEW mart.v_sales_revenue   OWNER TO role_engineer;
ALTER VIEW mart.v_park_operations OWNER TO role_engineer;
ALTER VIEW mart.v_wait_time       OWNER TO role_engineer;
ALTER VIEW mart.v_status_data     OWNER TO role_engineer;
GRANT SELECT ON ALL TABLES IN SCHEMA mart TO role_viewer, role_analyst;

-- ========== cek jumlah baris (harus 6 baris, tidak error) ==========
SELECT 'fact_booking' AS objek, COUNT(*) AS baris FROM dw.fact_booking
UNION ALL SELECT 'fact_crowd_daily', COUNT(*) FROM dw.fact_crowd_daily
UNION ALL SELECT 'fact_wait_time', COUNT(*) FROM dw.fact_wait_time
UNION ALL SELECT 'mart.v_sales_revenue', COUNT(*) FROM mart.v_sales_revenue
UNION ALL SELECT 'mart.v_park_operations', COUNT(*) FROM mart.v_park_operations
UNION ALL SELECT 'mart.v_wait_time', COUNT(*) FROM mart.v_wait_time;

-- ========== validasi 1: jumlah booking dan total revenue ==========
SELECT 'jumlah booking' AS cek,
       (SELECT COUNT(DISTINCT "BookingID") FROM stg.stg_booking) AS sumber,
       (SELECT COUNT(*) FROM mart.v_sales_revenue)               AS mart,
       (SELECT COUNT(DISTINCT "BookingID") FROM stg.stg_booking)
         - (SELECT COUNT(*) FROM mart.v_sales_revenue)           AS selisih
UNION ALL
SELECT 'total revenue',
       (SELECT ROUND(SUM(CAST("TotalRevenue" AS numeric)), 2) FROM stg.stg_booking),
       (SELECT ROUND(SUM(total_revenue), 2) FROM mart.v_sales_revenue),
       (SELECT ROUND(SUM(CAST("TotalRevenue" AS numeric)), 2) FROM stg.stg_booking)
         - (SELECT ROUND(SUM(total_revenue), 2) FROM mart.v_sales_revenue);

-- ========== validasi 2: revenue per channel ==========
SELECT s.channel,
       s.rev_sumber,
       m.rev_mart,
       ROUND(s.rev_sumber - m.rev_mart, 2) AS selisih
FROM (SELECT TRIM("SalesChannel") AS channel,
             ROUND(SUM(CAST("TotalRevenue" AS numeric)), 2) AS rev_sumber
      FROM stg.stg_booking GROUP BY 1) s
JOIN (SELECT sales_channel AS channel,
             ROUND(SUM(total_revenue), 2) AS rev_mart
      FROM mart.v_sales_revenue GROUP BY 1) m
  ON m.channel = s.channel
ORDER BY s.rev_sumber DESC;

-- ========== validasi 3: rata-rata crowd per park (nama sumber vs alias) ==========
SELECT m.park_name,
       s.park_name AS source_park_name,
       s.crowd_sumber,
       m.crowd_mart,
       ROUND(s.crowd_sumber - m.crowd_mart, 2) AS selisih
FROM (SELECT park_name,
             ROUND(AVG(CAST(crowd_level_pct AS numeric)), 2) AS crowd_sumber
      FROM stg.stg_calendar WHERE "year" IN (2025, 2026) GROUP BY 1) s
JOIN (SELECT park_name, source_park_name,
             ROUND(AVG(crowd_level_pct), 2) AS crowd_mart
      FROM mart.v_park_operations GROUP BY 1, 2) m
  ON m.source_park_name = s.park_name
ORDER BY s.crowd_sumber DESC;

-- ========== validasi 4: Promo Validity Rate (KPI UTS) ==========
SELECT promotion,
       COUNT(*)                                   AS booking,
       SUM(promo_valid_flag)                      AS valid,
       COUNT(*) - SUM(promo_valid_flag)           AS perlu_ditinjau,
       ROUND(100.0 * SUM(promo_valid_flag) / COUNT(*), 1) AS validity_rate_pct
FROM mart.v_sales_revenue
WHERE promotion <> 'Tanpa Promo'
GROUP BY promotion
ORDER BY promotion;
