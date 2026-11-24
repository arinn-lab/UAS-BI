#!/bin/bash
# 03_rbac.sh
# Role-Based Access Control (RBAC) sesuai rancangan UTS:
#   viewer   -> dashboard: hanya baca schema mart
#   analyst  -> baca schema dw dan mart
#   engineer -> tulis stg, dw, audit; membuat view mart (dipakai ETL/Airflow)
#   admin    -> superuser database (DBA): backup, restore, kelola role
#
# Dijalankan otomatis oleh container PostgreSQL saat volume pertama kali
# dibuat, setelah 01_schema.sql. Password diambil dari environment variable
# (lihat .env), jadi tidak ada password yang tertulis di kode.
#
# PENTING: file ini harus berakhiran baris LF (bukan CRLF Windows).
set -euo pipefail

: "${ENGINEER_PASSWORD:?ENGINEER_PASSWORD belum diisi di .env}"
: "${ANALYST_PASSWORD:?ANALYST_PASSWORD belum diisi di .env}"
: "${VIEWER_PASSWORD:?VIEWER_PASSWORD belum diisi di .env}"

psql -v ON_ERROR_STOP=1 \
     --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
     -v engineer_pw="$ENGINEER_PASSWORD" \
     -v analyst_pw="$ANALYST_PASSWORD" \
     -v viewer_pw="$VIEWER_PASSWORD" <<'EOSQL'

-- ---------- peran (group role, tidak bisa login) ----------
CREATE ROLE role_viewer   NOLOGIN;
CREATE ROLE role_analyst  NOLOGIN;
CREATE ROLE role_engineer NOLOGIN;
CREATE ROLE role_admin    NOLOGIN;

-- ---------- user login, masing-masing hanya punya satu peran ----------
CREATE ROLE vl_viewer   LOGIN PASSWORD :'viewer_pw'   IN ROLE role_viewer;
CREATE ROLE vl_analyst  LOGIN PASSWORD :'analyst_pw'  IN ROLE role_analyst;
CREATE ROLE vl_engineer LOGIN PASSWORD :'engineer_pw' IN ROLE role_engineer;
-- admin = user superuser bawaan container (POSTGRES_USER)
GRANT role_admin TO CURRENT_USER;

-- ---------- least privilege: cabut akses bawaan ----------
REVOKE ALL ON DATABASE vistaland_dwh FROM PUBLIC;
REVOKE ALL ON SCHEMA public FROM PUBLIC;
GRANT CONNECT ON DATABASE vistaland_dwh
      TO role_viewer, role_analyst, role_engineer, role_admin;

-- ---------- viewer: hanya schema mart (baca) ----------
GRANT USAGE ON SCHEMA mart TO role_viewer;

-- ---------- analyst: baca dw dan mart ----------
GRANT USAGE ON SCHEMA dw, mart TO role_analyst;
GRANT SELECT ON ALL TABLES IN SCHEMA dw TO role_analyst;

-- ---------- engineer: tulis stg, dw, audit; buat view di mart ----------
GRANT USAGE, CREATE ON SCHEMA stg, dw, audit, mart TO role_engineer;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA stg, dw, audit
      TO role_engineer;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA stg, dw, audit TO role_engineer;

-- tabel/view yang nanti dibuat engineer (staging, view mart) otomatis
-- mendapat hak akses yang sesuai
ALTER DEFAULT PRIVILEGES FOR ROLE vl_engineer IN SCHEMA mart
      GRANT SELECT ON TABLES TO role_viewer, role_analyst;
ALTER DEFAULT PRIVILEGES FOR ROLE vl_engineer IN SCHEMA stg
      GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO role_engineer;

-- ---------- admin: semua schema ----------
GRANT ALL ON SCHEMA stg, dw, mart, audit TO role_admin;
GRANT ALL ON ALL TABLES IN SCHEMA stg, dw, audit TO role_admin;

-- ringkasan peran
SELECT r.rolname AS user_login, g.rolname AS peran
FROM pg_roles r
JOIN pg_auth_members m ON m.member = r.oid
JOIN pg_roles g ON g.oid = m.roleid
WHERE r.rolname LIKE 'vl_%'
ORDER BY 1;
EOSQL
