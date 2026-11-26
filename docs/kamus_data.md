# Kamus Data dan Definisi KPI, Vistaland DWH

Dokumen ini adalah kamus data terpusat yang dirancang di UTS dan dipelihara oleh Data Steward.
Mata uang diasumsikan **USD** pada seluruh KPI. Data booking bersifat **simulasi**. Data calendar
dan ridestats adalah dataset eksternal (Queue-Times via Kaggle).

## 1. Lapisan dan schema

| Schema | Isi | Retensi | Akses (RBAC) |
|---|---|---|---|
| `stg` | `stg_booking`, `stg_calendar`, `stg_ridestats`, `stg_rejected` (data mentah + `source_file`, `extracted_at`) | 90 hari; arsip file sumber permanen di MinIO (`vistaland-raw`) | engineer, admin |
| `dw` | 9 dimensi + 3 fakta (galaxy schema) | permanen | engineer (tulis), analyst (baca), admin |
| `mart` | 3 view untuk dashboard | dibangun ulang tiap refresh | viewer, analyst (baca), engineer (buat), admin |
| `audit` | `etl_log`, `data_quality_log` | 24 bulan | engineer, admin |

## 2. Tabel fakta

| Fakta | Grain | Kunci | Measure |
|---|---|---|---|
| `fact_booking` | 1 baris = 1 booking | PK `booking_id` (degenerate dimension) | `adult_guests`, `child_guests`, `total_guests`, `trip_length`, `lead_time_days`, `ticket_revenue`, `hotel_revenue`, `addon_revenue`, `total_revenue`, `promo_valid_flag` |
| `fact_crowd_daily` | 1 baris = 1 park per hari | PK (`date_key`, `park_key`) | `crowd_level_pct`, `crowd_rel_to_year`, `operating_minutes`, `is_minutes_imputed` |
| `fact_wait_time` | 1 baris = 1 wahana per park per tahun | PK (`year_key`, `park_key`, `ride_key`) | `avg_wait_minutes`, `max_wait_minutes` (CHECK max ≥ avg) |

Setiap fakta menyimpan `source_file` dan `load_ts` untuk data lineage.

## 3. Tabel dimensi

| Dimensi | Kolom utama | Perlakuan | Baris |
|---|---|---|---|
| `dim_date` | `date_key` (yyyymmdd), `full_date`, `day`, `month`, `month_name`, `quarter`, `year`, `day_of_week`, `is_weekend`, `is_holiday`, `season` | SCD Type 0; role-playing (tanggal datang & beli); conformed | 730 |
| `dim_year` | `year_key`, `year_number` | rollup dari `dim_date` | 2 |
| `dim_park` | `park_key`, `source_park_id`, `park_name` (alias Vistaland), `source_park_name` | SCD Type 1; conformed | 4 |
| `dim_ride` | `ride_key`, `ride_id`, `ride_name`, `is_archived` | SCD Type 1 (snapshot sumber) | 97 |
| `dim_customer` | `customer_key`, `customer_state`, `customer_segment`, `first_time_guest` | SCD Type 1 | 80 |
| `dim_package` | `package_key`, `resort_category`, `ticket_days`, `park_hopper`, `lightning_lane`, `dining_plan` | dimensi gabungan, SCD Type 1 | 144 |
| `dim_channel_promo` | `channel_promo_key`, `sales_channel`, `promotion` | junk dimension | 12 |
| `dim_event` | `event_key`, `event_name` | SCD Type 1 | 4 |
| `dim_day_condition` | `day_condition_key`, `is_rainy`, `has_special_event`, `has_early_entry`, `has_extended_evening` | junk dimension | kombinasi unik di calendar |

Alias park: Magic Kingdom → Vista Kingdom, Epcot → Vista Discovery, Hollywood Studios → Vista Studios,
Animal Kingdom → Vista Wildlands. Season: Des–Feb Winter, Mar–Mei Spring, Jun–Agu Summer, Sep–Nov Fall.

## 4. View data mart

| View | Area | Sumber | Catatan |
|---|---|---|---|
| `mart.v_sales_revenue` | Sales & Revenue | `fact_booking` + 5 dimensi | `revenue_per_guest` dan `revenue_per_ticket_day` dihitung di view |
| `mart.v_park_operations` | Park Operations | `fact_crowd_daily` + 3 dimensi | `operating_minutes_observed` = jam operasional tanpa imputasi |
| `mart.v_wait_time` | Park Operations | `fact_wait_time` + 3 dimensi | `ride_status` = Active/Archived dari `is_archived` |
| `mart.v_status_data` | Status data | ringkasan `audit.etl_log` | waktu terakhir mart diperbarui dan hasil validasi terakhir, supaya viewer tidak perlu akses ke schema audit |

## 5. Definisi KPI

| KPI | Rumus | Sumber | Dimensi analisis |
|---|---|---|---|
| Total Revenue | `SUM(total_revenue)` | `v_sales_revenue` | tanggal, channel, promo, segmen, paket |
| Average Revenue per Booking | `SUM(total_revenue) / COUNT(booking_id)` | `v_sales_revenue` | segmen, resort category, bulan |
| Revenue Mix | `SUM(ticket_revenue) / SUM(total_revenue)`, begitu juga hotel dan add-on | `v_sales_revenue` | paket, channel, musim |
| Promo Validity Rate | booking berpromo dengan `promo_valid_flag = 1` / seluruh booking berpromo | `v_sales_revenue` | promo, state pelanggan |
| Average Crowd Level | `AVG(crowd_level_pct)` (indeks 0–100, bukan jumlah pengunjung) | `v_park_operations` | park, bulan, hari, kondisi hari |
| Operating Minutes | `AVG(operating_minutes_observed)` (tanpa data imputasi) | `v_park_operations` | park, bulan |
| Average & Max Wait Time | `AVG(avg_wait_minutes)`, `MAX(max_wait_minutes)` | `v_wait_time` | park, wahana, tahun |
| Rainy-Day Crowd Difference | `AVG(crowd)` hari hujan − `AVG(crowd)` hari tidak hujan | `v_park_operations` | park, kondisi hari |

## 6. Aturan kualitas data

| Dimensi | Aturan | Ambang | Tindakan |
|---|---|---|---|
| Kelengkapan | BookingID, tanggal, park_id tidak kosong | 100% | tolak ke `stg_rejected` |
| Keunikan | BookingID unik; (park_id, date) unik | 0 duplikat | pakai versi terbaru, catat |
| Validitas | crowd 0–100; max_wait ≥ avg_wait; ArrivalDate ≥ PurchaseDate | 0 pelanggaran | tolak baris |
| Konsistensi | TotalRevenue = Ticket + Hotel + Addon; semua FK ada | 0 selisih | tolak / lookup FK gagal → `stg_rejected` |
| Ambang penolakan | baris ditolak per sumber | maks 1% | load fakta dihentikan, email darurat |
| Ketepatan | promo Florida Resident hanya untuk pelanggan FL | dipantau | `promo_valid_flag = 0`, laporan ke Marketing |
| Ketepatan waktu | data mart siap sebelum 06:00 (Orlando) | setiap hari | email ke Data Engineer |
