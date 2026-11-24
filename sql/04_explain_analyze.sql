-- 04_explain_analyze.sql
-- Uji performa query dashboard (rancangan Storage UTS: "Validasi manfaat
-- indeks dengan EXPLAIN ANALYZE pada query yang mewakili dashboard").
--
-- Jalankan (sebagai analyst atau admin):
--   PowerShell: Get-Content sql\04_explain_analyze.sql | docker exec -i vistaland_db psql -U vistaland -d vistaland_dwh
--
-- Setiap query dijalankan dua kali: (A) indeks dimatikan sementara untuk sesi
-- ini saja, (B) indeks dipakai normal. Bandingkan "Execution Time".
-- Catatan: dengan volume prototipe (< 10 ribu baris fakta) planner bisa saja
-- tetap memilih Seq Scan karena lebih murah; itu hasil yang wajar dan justru
-- menjadi dasar keputusan UTS bahwa partisi belum diperlukan.

\echo '===== Q1: revenue per bulan & channel tahun 2025 (tab Penjualan) ====='
SET enable_indexscan = off; SET enable_bitmapscan = off;
\echo '--- (A) tanpa indeks'
EXPLAIN (ANALYZE, BUFFERS)
SELECT d.year, d.month, cp.sales_channel, SUM(f.total_revenue)
FROM dw.fact_booking f
JOIN dw.dim_date d ON d.date_key = f.arrival_date_key
JOIN dw.dim_channel_promo cp ON cp.channel_promo_key = f.channel_promo_key
WHERE d.year = 2025
GROUP BY 1, 2, 3;
RESET enable_indexscan; RESET enable_bitmapscan;
\echo '--- (B) dengan indeks'
EXPLAIN (ANALYZE, BUFFERS)
SELECT d.year, d.month, cp.sales_channel, SUM(f.total_revenue)
FROM dw.fact_booking f
JOIN dw.dim_date d ON d.date_key = f.arrival_date_key
JOIN dw.dim_channel_promo cp ON cp.channel_promo_key = f.channel_promo_key
WHERE d.year = 2025
GROUP BY 1, 2, 3;

\echo '===== Q2: rata-rata crowd satu park per bulan (tab Crowd) ====='
SET enable_indexscan = off; SET enable_bitmapscan = off;
\echo '--- (A) tanpa indeks'
EXPLAIN (ANALYZE, BUFFERS)
SELECT d.month, AVG(f.crowd_level_pct)
FROM dw.fact_crowd_daily f
JOIN dw.dim_date d ON d.date_key = f.date_key
WHERE f.park_key = 1
GROUP BY 1;
RESET enable_indexscan; RESET enable_bitmapscan;
\echo '--- (B) dengan indeks'
EXPLAIN (ANALYZE, BUFFERS)
SELECT d.month, AVG(f.crowd_level_pct)
FROM dw.fact_crowd_daily f
JOIN dw.dim_date d ON d.date_key = f.date_key
WHERE f.park_key = 1
GROUP BY 1;

\echo '===== Q3: query view mart yang dibaca dashboard ====='
EXPLAIN (ANALYZE, BUFFERS) SELECT * FROM mart.v_sales_revenue;
EXPLAIN (ANALYZE, BUFFERS) SELECT * FROM mart.v_park_operations;
EXPLAIN (ANALYZE, BUFFERS) SELECT * FROM mart.v_wait_time;

\echo '===== daftar indeks di schema dw ====='
SELECT tablename, indexname FROM pg_indexes WHERE schemaname = 'dw' ORDER BY 1, 2;
