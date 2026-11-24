-- 01_schema.sql
-- Membuat schema dan semua tabel data warehouse sesuai rancangan UTS
-- (galaxy schema: 3 fakta, 9 dimensi; schema logis stg, dw, mart, audit).
--
-- File ini dijalankan otomatis oleh container PostgreSQL HANYA saat volume
-- database pertama kali dibuat (docker-entrypoint-initdb.d), sebagai superuser
-- (admin). Kalau dijalankan ulang manual, schema dw, mart, dan audit dibuat
-- ulang dari nol (isinya hilang), jadi ETL harus dijalankan lagi.
--
-- Tabel staging (stg_booking, stg_calendar, stg_ridestats) dibuat oleh tahap
-- extract saat full load pertama, karena strukturnya mengikuti file sumber.

DROP SCHEMA IF EXISTS mart CASCADE;
DROP SCHEMA IF EXISTS dw CASCADE;
DROP SCHEMA IF EXISTS audit CASCADE;
CREATE SCHEMA IF NOT EXISTS stg;
CREATE SCHEMA dw;
CREATE SCHEMA audit;
CREATE SCHEMA mart;

-- baris sumber yang ditolak saat transform/validasi (aturan T21)
CREATE TABLE IF NOT EXISTS stg.stg_rejected (
    reject_id    BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    run_id       VARCHAR(36),
    source_name  VARCHAR(100),
    record_key   VARCHAR(100),
    reason       TEXT NOT NULL,
    raw_data     TEXT,
    rejected_at  TIMESTAMP NOT NULL DEFAULT now()
);

-- ================= DIMENSI =================

-- Dim_Date: SCD Type 0 (statis), dipakai Fact_Booking dan Fact_Crowd_Daily
CREATE TABLE dw.dim_date (
    date_key     INTEGER PRIMARY KEY,          -- yyyymmdd
    full_date    DATE NOT NULL UNIQUE,
    day          SMALLINT NOT NULL,
    month        SMALLINT NOT NULL,
    month_name   VARCHAR(10) NOT NULL,
    quarter      SMALLINT NOT NULL,
    year         SMALLINT NOT NULL,
    day_of_week  VARCHAR(10) NOT NULL,
    is_weekend   BOOLEAN NOT NULL,
    is_holiday   BOOLEAN NOT NULL,
    season       VARCHAR(10) NOT NULL          -- Winter / Spring / Summer / Fall
);

-- Dim_Year: rollup (shrunken) dimension dari Dim_Date
CREATE TABLE dw.dim_year (
    year_key     INTEGER PRIMARY KEY,
    year_number  SMALLINT NOT NULL UNIQUE
);

-- Dim_Park: SCD Type 1; park_name = alias Vistaland, nama dan ID sumber tetap disimpan
CREATE TABLE dw.dim_park (
    park_key          INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source_park_id    INTEGER NOT NULL UNIQUE,
    park_name         VARCHAR(60) NOT NULL,
    source_park_name  VARCHAR(60) NOT NULL
);

-- Dim_Ride: SCD Type 1, satu baris per ride_id (status arsip = snapshot sumber)
CREATE TABLE dw.dim_ride (
    ride_key     INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    ride_id      INTEGER NOT NULL UNIQUE,
    ride_name    VARCHAR(200) NOT NULL,
    is_archived  BOOLEAN NOT NULL
);

-- Dim_Customer: SCD Type 1 (tanpa identitas pribadi)
CREATE TABLE dw.dim_customer (
    customer_key      INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_state    VARCHAR(2) NOT NULL,
    customer_segment  VARCHAR(20) NOT NULL,
    first_time_guest  BOOLEAN NOT NULL,
    UNIQUE (customer_state, customer_segment, first_time_guest)
);

-- Dim_Package: dimensi paket gabungan (SCD Type 1)
CREATE TABLE dw.dim_package (
    package_key      INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    resort_category  VARCHAR(20) NOT NULL,
    ticket_days      SMALLINT NOT NULL,
    park_hopper      BOOLEAN NOT NULL,
    lightning_lane   BOOLEAN NOT NULL,
    dining_plan      BOOLEAN NOT NULL,
    UNIQUE (resort_category, ticket_days, park_hopper, lightning_lane, dining_plan)
);

-- Dim_Channel_Promo: junk dimension
CREATE TABLE dw.dim_channel_promo (
    channel_promo_key  INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    sales_channel      VARCHAR(30) NOT NULL,
    promotion          VARCHAR(30) NOT NULL,       -- termasuk 'Tanpa Promo'
    UNIQUE (sales_channel, promotion)
);

-- Dim_Event: SCD Type 1
CREATE TABLE dw.dim_event (
    event_key   INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    event_name  VARCHAR(40) NOT NULL UNIQUE      -- termasuk 'Tanpa Event'
);

-- Dim_Day_Condition: junk dimension penanda kondisi hari
CREATE TABLE dw.dim_day_condition (
    day_condition_key     INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    is_rainy              BOOLEAN NOT NULL,
    has_special_event     BOOLEAN NOT NULL,
    has_early_entry       BOOLEAN NOT NULL,
    has_extended_evening  BOOLEAN NOT NULL,
    UNIQUE (is_rainy, has_special_event, has_early_entry, has_extended_evening)
);

-- ================= FAKTA =================

-- Fact_Booking: 1 baris = 1 booking; booking_id = degenerate dimension (PK)
CREATE TABLE dw.fact_booking (
    booking_id         VARCHAR(10) PRIMARY KEY,
    arrival_date_key   INTEGER NOT NULL REFERENCES dw.dim_date(date_key),
    purchase_date_key  INTEGER NOT NULL REFERENCES dw.dim_date(date_key),
    customer_key       INTEGER NOT NULL REFERENCES dw.dim_customer(customer_key),
    package_key        INTEGER NOT NULL REFERENCES dw.dim_package(package_key),
    channel_promo_key  INTEGER NOT NULL REFERENCES dw.dim_channel_promo(channel_promo_key),
    event_key          INTEGER NOT NULL REFERENCES dw.dim_event(event_key),
    adult_guests       SMALLINT NOT NULL,
    child_guests       SMALLINT NOT NULL,
    total_guests       SMALLINT NOT NULL,
    trip_length        SMALLINT NOT NULL,
    lead_time_days     INTEGER NOT NULL,
    ticket_revenue     NUMERIC(12,2) NOT NULL,
    hotel_revenue      NUMERIC(12,2) NOT NULL,
    addon_revenue      NUMERIC(12,2) NOT NULL,
    total_revenue      NUMERIC(12,2) NOT NULL,
    promo_valid_flag   SMALLINT NOT NULL CHECK (promo_valid_flag IN (0, 1)),  -- 1 = valid atau tanpa promo
    source_file        VARCHAR(100) NOT NULL,
    load_ts            TIMESTAMP NOT NULL DEFAULT now()
);

-- Fact_Crowd_Daily: 1 baris = 1 park per hari; PK gabungan
CREATE TABLE dw.fact_crowd_daily (
    date_key            INTEGER NOT NULL REFERENCES dw.dim_date(date_key),
    park_key            INTEGER NOT NULL REFERENCES dw.dim_park(park_key),
    day_condition_key   INTEGER NOT NULL REFERENCES dw.dim_day_condition(day_condition_key),
    crowd_level_pct     SMALLINT NOT NULL CHECK (crowd_level_pct BETWEEN 0 AND 100),
    crowd_rel_to_year   NUMERIC(6,3) NOT NULL,
    operating_minutes   NUMERIC(8,2),
    is_minutes_imputed  SMALLINT NOT NULL CHECK (is_minutes_imputed IN (0, 1)),  -- 1 = hasil imputasi median
    source_file         VARCHAR(100) NOT NULL,
    load_ts             TIMESTAMP NOT NULL DEFAULT now(),
    PRIMARY KEY (date_key, park_key)
);

-- Fact_Wait_Time: 1 baris = 1 wahana per park per tahun; PK gabungan
CREATE TABLE dw.fact_wait_time (
    year_key          INTEGER NOT NULL REFERENCES dw.dim_year(year_key),
    park_key          INTEGER NOT NULL REFERENCES dw.dim_park(park_key),
    ride_key          INTEGER NOT NULL REFERENCES dw.dim_ride(ride_key),
    avg_wait_minutes  INTEGER NOT NULL,
    max_wait_minutes  INTEGER NOT NULL,
    source_file       VARCHAR(100) NOT NULL,
    load_ts           TIMESTAMP NOT NULL DEFAULT now(),
    PRIMARY KEY (year_key, park_key, ride_key),
    CHECK (max_wait_minutes >= avg_wait_minutes)
);

-- ================= INDEKS =================
-- Indeks pada foreign key dan kolom filter dashboard (rancangan Storage UTS).
-- Kolom pertama PK gabungan (date_key, year_key) sudah terindeks oleh PK.
CREATE INDEX ix_fact_booking_arrival_date  ON dw.fact_booking (arrival_date_key);
CREATE INDEX ix_fact_booking_purchase_date ON dw.fact_booking (purchase_date_key);
CREATE INDEX ix_fact_booking_customer      ON dw.fact_booking (customer_key);
CREATE INDEX ix_fact_booking_package       ON dw.fact_booking (package_key);
CREATE INDEX ix_fact_booking_channel_promo ON dw.fact_booking (channel_promo_key);
CREATE INDEX ix_fact_booking_event         ON dw.fact_booking (event_key);
CREATE INDEX ix_fact_crowd_park            ON dw.fact_crowd_daily (park_key);
CREATE INDEX ix_fact_crowd_day_condition   ON dw.fact_crowd_daily (day_condition_key);
CREATE INDEX ix_fact_wait_park             ON dw.fact_wait_time (park_key);
CREATE INDEX ix_fact_wait_ride             ON dw.fact_wait_time (ride_key);
CREATE INDEX ix_dim_date_year              ON dw.dim_date (year);

-- ================= AUDIT =================

CREATE TABLE audit.etl_log (
    log_id         BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    run_id         VARCHAR(36) NOT NULL,
    step           VARCHAR(60) NOT NULL,
    source_name    VARCHAR(100),
    rows_in        INTEGER,
    rows_out       INTEGER,
    rows_rejected  INTEGER,
    status         VARCHAR(10) NOT NULL,     -- SUCCESS / FAILED / WARN
    message        TEXT,
    started_at     TIMESTAMP NOT NULL DEFAULT now(),
    finished_at    TIMESTAMP
);
CREATE INDEX ix_etl_log_step_time ON audit.etl_log (step, finished_at);

CREATE TABLE audit.data_quality_log (
    dq_id         BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    run_id        VARCHAR(36) NOT NULL,
    check_name    VARCHAR(100) NOT NULL,
    table_name    VARCHAR(100) NOT NULL,
    rows_checked  INTEGER,
    rows_failed   INTEGER,
    status        VARCHAR(10) NOT NULL,      -- PASS / WARN / FAIL
    detail        TEXT,
    checked_at    TIMESTAMP NOT NULL DEFAULT now()
);

-- Hak akses per peran (RBAC) diatur di sql/03_rbac.sh.

-- cek: harus ada 9 dimensi, 3 fakta, 2 tabel audit, dan stg_rejected
SELECT table_schema, table_name
FROM information_schema.tables
WHERE table_schema IN ('stg', 'dw', 'audit')
ORDER BY table_schema, table_name;
