-- 05_uji_rbac.sql
-- Bukti RBAC dan least privilege. Jalankan per user (PowerShell), contoh:
--   Get-Content sql\05_uji_rbac.sql | docker exec -i vistaland_db psql -U vl_viewer -d vistaland_dwh
-- Ganti vl_viewer dengan vl_analyst atau vl_engineer untuk membandingkan.
-- Untuk vl_viewer, query mart harus BERHASIL dan query dw/stg harus
-- DITOLAK ("permission denied").
\set ON_ERROR_STOP off
\echo '== user yang sedang login =='
SELECT current_user, (SELECT string_agg(g.rolname, ', ') FROM pg_auth_members m
       JOIN pg_roles g ON g.oid = m.roleid
       JOIN pg_roles u ON u.oid = m.member WHERE u.rolname = current_user) AS peran;
\echo '== 1. baca data mart (viewer, analyst, engineer: boleh) =='
SELECT COUNT(*) AS mart_sales FROM mart.v_sales_revenue;
\echo '== 2. baca schema dw (viewer: DITOLAK; analyst, engineer: boleh) =='
SELECT COUNT(*) AS dw_fact_booking FROM dw.fact_booking;
\echo '== 3. baca staging (viewer, analyst: DITOLAK; engineer: boleh) =='
SELECT COUNT(*) AS stg_booking FROM stg.stg_booking;
\echo '== 4. menulis ke dw (viewer, analyst: DITOLAK; engineer: boleh, lalu dibatalkan) =='
BEGIN;
UPDATE dw.dim_event SET event_name = event_name WHERE false;
ROLLBACK;
\echo '== 5. membuat tabel di public (semua user non-admin: DITOLAK) =='
CREATE TABLE public.coba_rbac (x int);
