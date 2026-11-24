# Vistaland Data Warehouse & Dashboard BI

Proyek UAS Kecerdasan Bisnis (Bidang MTI) — implementasi rancangan UTS *Data Warehouse Vistaland Theme Park*.
Vistaland adalah studi kasus fiktif; data booking bersifat simulasi, data crowd dan waktu tunggu berasal dari
dataset eksternal (Queue-Times via Kaggle).

```
Sumber (xlsx/csv) ─► Extract ─► stg (staging) ─► Transform & validasi ─► dw (9 dimensi + 3 fakta)
      │                                                                     │
      └─► MinIO (arsip file sumber)                                         ▼
                                              mart (3 view) ─► Dashboard Streamlit
Airflow: jadwal, retry, callback, email (Mailpit) · audit: etl_log, data_quality_log
Backup 23:00: pg_dump terenkripsi ─► folder backups/ + MinIO (retensi 30 hari)
```

## Komponen

| Komponen | Versi | Fungsi | Alamat |
|---|---|---|---|
| PostgreSQL | 17 | schema `stg`, `dw`, `mart`, `audit` + RBAC | `localhost:5433` |
| Apache Airflow | 3.3.0 (standalone) | orkestrasi ETL, backup, notifikasi | http://localhost:8081 |
| MinIO | latest | object storage: arsip file sumber & backup | http://localhost:9001 |
| Mailpit | latest | penangkap email notifikasi (lokal) | http://localhost:8025 |
| Streamlit | — | dashboard BI (membaca schema `mart` sebagai `vl_viewer`) | http://localhost:8501 |

## Struktur folder

```
airflow/Dockerfile            image Airflow + pg_dump 17 + library ETL
airflow/dags/vistaland_etl.py 9 DAG (jadwal UTS + 1 DAG manual)
etl/                          extract, transform_validate, transform_dim, transform_fact,
                              transform_booking, pipeline, backup, retensi, notify, storage, config
sql/01_schema.sql             schema + 9 dimensi + 3 fakta + indeks + audit
sql/02_mart_dan_validasi.sql  view data mart + query validasi source vs mart
sql/03_rbac.sh                peran viewer / analyst / engineer / admin
sql/04_explain_analyze.sql    uji performa query (EXPLAIN ANALYZE)
sql/05_uji_rbac.sql           bukti least privilege per user
dashboard/app.py              dashboard Streamlit
docs/kamus_data.md            kamus data, definisi KPI, aturan kualitas
data/raw/                     3 file sumber
```

## Menjalankan dari nol (Windows PowerShell)

```powershell
cd C:\Users\USER\Downloads\vistaland-dwh

# 1. konfigurasi rahasia
copy .env.example .env
notepad .env                     # isi semua nilai GANTI_...
pip install cryptography         # sekali saja, untuk membuat kunci backup
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
#    tempel hasilnya ke BACKUP_ENCRYPTION_KEY di .env

# 2. jalankan semua container
docker compose up -d --build
docker compose ps                # vistaland_db harus "healthy"

# 3. password login Airflow (user admin)
docker compose exec airflow cat /opt/airflow/simple_auth_manager_passwords.json.generated
```

Buka Airflow → DAG **`vistaland_etl`** (manual) → **Trigger**. DAG ini menjalankan seluruh pipeline
sekali jalan; DAG lain berjalan sendiri sesuai jadwal.

### Dashboard

```powershell
python -m venv .venv-dashboard
.\.venv-dashboard\Scripts\Activate.ps1          # kalau diblokir: Set-ExecutionPolicy -Scope Process Bypass
pip install -r dashboard\requirements-dashboard.txt
streamlit run dashboard\app.py                  # http://localhost:8501
```

### ETL manual tanpa Airflow (opsional)

```powershell
pip install -r requirements.txt
python etl\run_etl.py
```

## Jadwal (America/New_York, sesuai tabel Scheduling UTS)

| DAG | Jadwal | Isi | Menunggu |
|---|---|---|---|
| `vistaland_extract_booking` | harian 02:00 | extract booking (full load awal, lalu incremental per BookingID) | — |
| `vistaland_extract_calendar` | harian 03:00 | extract calendar (upsert per park_id, date) | — |
| `vistaland_extract_ridestats` | tgl 1 tiap bulan 04:00 | extract ridestats (upsert) | — |
| `vistaland_transform_validasi` | harian 04:30 | aturan kualitas, `stg_rejected`, ambang 1% | semua extract |
| `vistaland_load_dimensi` | harian 05:00 | 9 dimensi | transform_validasi |
| `vistaland_load_fakta` | harian 05:15 | 3 fakta | load_dimensi |
| `vistaland_refresh_mart` | harian 05:30 | view mart → validasi → cek siap < 06:00 → ringkasan Data Steward | load_fakta |
| `vistaland_backup` | harian 23:00 | backup terenkripsi + retensi | — |
| `vistaland_etl` | manual | seluruh pipeline berurutan | — |

Dependensi dijaga sensor yang membaca `audit.etl_log`: kalau satu tahap gagal, tahap berikutnya tidak
jalan dan data lama di DWH tetap dipakai.

## Error handling, logging, notifikasi

| Kejadian | Penanganan | Email (Mailpit) |
|---|---|---|
| File sumber tidak ada/rusak | retry 3× jeda 10 menit, tahap turunan tertahan | Data Engineer |
| Baris melanggar aturan | ditahan di `stg.stg_rejected`, baris valid tetap dimuat | ringkasan harian ke Data Steward |
| Baris ditolak > 1% | `transform_validasi` gagal tanpa retry, load fakta tidak jalan | darurat: Data Engineer + Data Steward |
| Database putus | transaksi di-rollback, retry otomatis | DBA + Data Engineer |
| Job dijalankan dua kali | load idempoten (upsert), tidak ada duplikat | — |
| Data mart belum siap 06:00 | dicatat WARN | Data Engineer |

Log: `logs/etl.log`, `logs/notifikasi_gagal.log`, tabel `audit.etl_log` dan `audit.data_quality_log`.

## Keamanan (RBAC)

| User | Peran | Hak akses |
|---|---|---|
| `vl_viewer` | viewer | baca `mart` (dipakai dashboard) |
| `vl_analyst` | analyst | baca `dw` dan `mart` |
| `vl_engineer` | engineer | tulis `stg`, `dw`, `audit`; buat view `mart` (dipakai Airflow) |
| `vistaland` | admin (DBA) | superuser: backup, restore, kelola peran |

Semua password ada di `.env` (tidak di-push). Uji: lihat bagian *Pengujian*.

## Backup & disaster recovery

- **RPO 24 jam**: `vistaland_backup` setiap 23:00 — `pg_dump` → dienkripsi (Fernet) → `backups/` dan
  bucket MinIO `vistaland-backup`. Backup > 30 hari dihapus otomatis.
- **RTO 4 jam**: uji restore ke database terpisah dan ukur waktunya:
  ```powershell
  docker compose exec airflow python /opt/airflow/project/etl/backup.py backup    # backup sekarang
  docker compose exec airflow python /opt/airflow/project/etl/backup.py restore   # uji restore
  ```
  Hasilnya (durasi + perbandingan jumlah baris dan revenue) tercatat di `audit.etl_log` step `uji_restore`.
- Pemulihan sungguhan: restore ke database baru, arahkan `DB_NAME` ke database itu, lalu trigger
  `vistaland_etl` untuk mengejar data terakhir. File sumber asli tersimpan permanen di bucket
  `vistaland-raw`, jadi staging bisa dibangun ulang.
- Uji restore direncanakan setiap kuartal.

## Pengujian

```powershell
# jumlah baris (harus 5000 / 2552 / 174 / 5000)
docker exec vistaland_db psql -U vistaland -d vistaland_dwh -c "SELECT (SELECT count(*) FROM dw.fact_booking) booking, (SELECT count(*) FROM dw.fact_crowd_daily) crowd, (SELECT count(*) FROM dw.fact_wait_time) wait, (SELECT count(*) FROM mart.v_sales_revenue) mart_sales;"

# hasil validasi source vs mart
docker exec vistaland_db psql -U vistaland -d vistaland_dwh -c "SELECT status, message FROM audit.etl_log WHERE step='validasi_source_mart' ORDER BY finished_at DESC LIMIT 1;"

# RBAC: ulangi dengan vl_analyst dan vl_engineer
Get-Content sql\05_uji_rbac.sql | docker exec -i vistaland_db psql -U vl_viewer -d vistaland_dwh

# performa query
Get-Content sql\04_explain_analyze.sql | docker exec -i vistaland_db psql -U vistaland -d vistaland_dwh
```

**Uji kegagalan terkontrol (callback + email):** set `RETRY_DELAY_MINUTES=1` di `.env`, jalankan
`docker compose up -d`, ganti nama `data\raw\ridestats.csv` sementara, trigger `vistaland_etl`. Setelah
3 retry, task merah, `logs\notifikasi_gagal.log` terisi, dan email muncul di http://localhost:8025.
Kembalikan nama file lalu trigger ulang.

**Uji ambang 1%:** salin `data\raw\Theme Park Mock Data.xlsx` sebagai cadangan. Karena extract booking
bersifat incremental (hanya BookingID baru), tambahkan **60 baris baru** di akhir file dengan BookingID
`TST001`–`TST060` dan `ArrivalDate` lebih awal dari `PurchaseDate` (60 dari 5.060 = 1,19%). Trigger
`vistaland_etl`: `transform_validasi` harus gagal tanpa retry, email "DARURAT" terkirim, dan isi `dw`
tidak berubah. Setelah itu kembalikan file asli dan hapus baris uji dari staging:
```powershell
'DELETE FROM stg.stg_booking WHERE "BookingID" LIKE ''TST%'';' | docker exec -i vistaland_db psql -U vistaland -d vistaland_dwh
```

## Catatan

- `docker compose down` aman (data tetap di volume). **`docker compose down -v` menghapus semua data**;
  hanya dipakai bila sengaja membangun database dari nol.
- `sql/01_schema.sql` dan `sql/03_rbac.sh` hanya dijalankan saat volume database pertama kali dibuat.
- Sumber dataset: Katy Kramer, *Walt Disney World Mock Data*; Chad Wambles, *Walt Disney World Wait Times
  and Crowd Calendar* (Kaggle). Atribusi dan lisensi diverifikasi di halaman Kaggle masing-masing.
