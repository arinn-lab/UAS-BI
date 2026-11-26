# Vistaland Data Warehouse & Dashboard BI

Proyek UAS Kecerdasan Bisnis (Bidang MTI), implementasi rancangan UTS *Data Warehouse Vistaland Theme Park*.
Vistaland adalah studi kasus fiktif; data booking bersifat simulasi, data crowd dan waktu tunggu berasal dari
dataset eksternal (Queue-Times via Kaggle).

```
Sumber (xlsx/csv) ─► Extract ─► stg (staging) ─► Transform & validasi ─► dw (9 dimensi + 3 fakta)
      │                                                                     │
      └─► MinIO (arsip file sumber)                                         ▼
                                    mart (view) ─► Dashboard Streamlit (laptop, baca PostgreSQL)
                                         └─► dashboard/data (salinan) ─► Streamlit Community Cloud
Airflow: jadwal, retry, callback, email (Mailpit) · audit: etl_log, data_quality_log
Backup 23:00: pg_dump terenkripsi ─► folder backups/ + MinIO (retensi 30 hari)
```

> **Cara menguji dan mendokumentasikan bukti langkah demi langkah: lihat [PANDUAN_UJI.md](PANDUAN_UJI.md).**

## Komponen

| Komponen | Versi | Fungsi | Alamat |
|---|---|---|---|
| PostgreSQL | 17 | schema `stg`, `dw`, `mart`, `audit` + RBAC | `localhost:5433` |
| Apache Airflow | 3.3.0 (standalone) | orkestrasi ETL, backup, notifikasi | http://localhost:8081 |
| MinIO (image `pgsty/silo`) | latest | object storage: arsip file sumber & backup | http://localhost:9001 |
| Mailpit | latest | penangkap email notifikasi (lokal) | http://localhost:8025 |
| Streamlit | 1.50+ | dashboard BI (membaca schema `mart` sebagai `vl_viewer`) | http://localhost:8501 |
| Streamlit Community Cloud | - | dashboard online, membaca salinan `dashboard/data` | [isi tautan] |

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
dashboard/app.py              navigasi dashboard (6 halaman)
dashboard/halaman.py          isi tiap halaman
dashboard/tampilan.py         warna, format angka, kartu KPI, gaya grafik
dashboard/sumber_data.py      baca PostgreSQL (laptop) atau salinan dashboard/data (online)
dashboard/data/               salinan data mart hasil etl/export_snapshot.py
docs/kamus_data.md            kamus data, definisi KPI, aturan kualitas
docs/mti/instrumen_MTI.xlsx   skenario tugas, form Heuristic Evaluation, kuesioner & hitung SUS
docs/hasil_explain.txt        hasil EXPLAIN ANALYZE
PANDUAN_UJI.md                urutan perintah uji + daftar screenshot bukti
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
pip install -r dashboard\requirements.txt
streamlit run dashboard\app.py                  # http://localhost:8501
```

### ETL manual tanpa Airflow (opsional)

```powershell
pip install -r requirements.txt
python etl\run_etl.py
```

## Dashboard

Dashboard dirancang dengan acuan Bach dkk. (2023), Franconeri dkk. (2021), Setlur dkk. (2023),
WCAG 2.2, dan skema warna Tol (2021). Mockup awal dibuat dengan bantuan Google Stitch.
Penjelasan lengkap ada di laporan subbab 2.12.

Tampilan:
- komponen HTML buatan sendiri (kepala halaman, kartu KPI, tindak lanjut) memakai Tailwind CSS.
  Hasil kompilasinya sudah ada di `dashboard/static/tailwind.css`, jadi tidak perlu Node.js untuk
  menjalankan dashboard. Kalau kelas Tailwind di file `.py` diubah, kompilasi ulang dari folder proyek:
  `npx tailwindcss@3 -c dashboard/tailwind/tailwind.config.js -i dashboard/tailwind/input.css -o dashboard/static/tailwind.css --minify`
- huruf Bricolage Grotesque dan Figtree (lisensi SIL OFL) ada di `dashboard/static`.
- ilustrasi kepala halaman digambar sendiri (`dashboard/aset/ilustrasi_taman.svg`).
- fitur interaktif: kartu KPI di Ringkasan bisa diklik untuk membuka halaman rinciannya, grafik tren
  bisa diganti antara revenue dan jumlah booking, baris tabel ringkasan per taman bisa dipilih untuk
  melihat rincian taman itu, semua grafik punya tooltip, dan tabel bisa diurutkan.

| Halaman | Isi |
|---|---|
| Ringkasan Eksekutif | Total Revenue, Revenue Mix, Promo Validity Rate, Average Crowd Level, Average Wait Time, tren revenue atau booking, crowd per taman, 3 tindak lanjut, ringkasan per taman dengan rincian |
| Penjualan & Revenue | revenue per bulan/kuartal per komponen, perbandingan menurut dimensi pilihan, Revenue Mix per kategori resort, revenue per state |
| Validitas Promo | Promo Validity Rate, Florida Resident, daftar booking perlu ditinjau (unduh CSV) |
| Crowd & Operasional | heatmap taman per bulan, Rainy-Day Crowd Difference, kondisi hari, hari dalam minggu, Operating Minutes |
| Waktu Tunggu Wahana | Average dan Max Wait Time, 10 wahana terlama, rata-rata per taman, tabel semua wahana |
| Kamus KPI & Data | definisi KPI, catatan data, status data |

### Dashboard online (Streamlit Community Cloud)

Server Streamlit tidak bisa menjangkau PostgreSQL di laptop. Karena itu task `ekspor_snapshot`
(setelah validasi mart) menyalin isi view mart ke `dashboard/data` memakai akun `vl_viewer`.
Folder ini ikut di-push ke GitHub, lalu dibaca dashboard online. Di laptop, dashboard tetap
membaca PostgreSQL langsung. Mode bisa dipaksa dengan `DASHBOARD_MODE=db` atau `DASHBOARD_MODE=snapshot`.

Deploy: https://share.streamlit.io, masuk dengan GitHub, Create app, pilih repository ini,
branch `main`, main file `dashboard/app.py`. Tidak perlu secrets.

## Jadwal (America/New_York, sesuai tabel Scheduling UTS)

| DAG | Jadwal | Isi | Menunggu |
|---|---|---|---|
| `vistaland_extract_booking` | harian 02:00 | extract booking (full load awal, lalu incremental per BookingID) |, |
| `vistaland_extract_calendar` | harian 03:00 | extract calendar (upsert per park_id, date) |, |
| `vistaland_extract_ridestats` | tgl 1 tiap bulan 04:00 | extract ridestats (upsert) |, |
| `vistaland_transform_validasi` | harian 04:30 | aturan kualitas, `stg_rejected`, ambang 1% | semua extract |
| `vistaland_load_dimensi` | harian 05:00 | 9 dimensi | transform_validasi |
| `vistaland_load_fakta` | harian 05:15 | 3 fakta | load_dimensi |
| `vistaland_refresh_mart` | harian 05:30 | view mart → validasi → cek siap < 06:00 → ringkasan Data Steward; salinan mart untuk dashboard online | load_fakta |
| `vistaland_backup` | harian 23:00 | backup terenkripsi + retensi |, |
| `vistaland_etl` | manual | seluruh pipeline berurutan |, |

Dependensi dijaga sensor yang membaca `audit.etl_log`: kalau satu tahap gagal, tahap berikutnya tidak
jalan dan data lama di DWH tetap dipakai.

## Error handling, logging, notifikasi

| Kejadian | Penanganan | Email (Mailpit) |
|---|---|---|
| File sumber tidak ada/rusak | retry 3× jeda 10 menit, tahap turunan tertahan | Data Engineer |
| Baris melanggar aturan | ditahan di `stg.stg_rejected`, baris valid tetap dimuat | ringkasan harian ke Data Steward |
| Baris ditolak > 1% | `transform_validasi` gagal tanpa retry, load fakta tidak jalan | darurat: Data Engineer + Data Steward |
| Database putus | transaksi di-rollback, retry otomatis | DBA + Data Engineer |
| Job dijalankan dua kali | load idempoten (upsert), tidak ada duplikat |, |
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

- **RPO 24 jam**: `vistaland_backup` setiap 23:00, `pg_dump` → dienkripsi (Fernet) → `backups/` dan
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

**Uji ambang 1%:** skrip `etl/uji_ambang.py` menambahkan 60 booking rusak (TST001-TST060,
ArrivalDate lebih awal dari PurchaseDate; 60 dari 5.060 = 1,19%) lalu memulihkannya:
```powershell
docker compose exec airflow python /opt/airflow/project/etl/uji_ambang.py buat
# trigger vistaland_etl: transform_validasi gagal tanpa retry, email DARURAT, isi dw tidak berubah
docker compose exec airflow python /opt/airflow/project/etl/uji_ambang.py pulihkan
# trigger vistaland_etl lagi sampai semua hijau
```

## Catatan

- `docker compose down` aman (data tetap di volume). **`docker compose down -v` menghapus semua data**;
  hanya dipakai bila sengaja membangun database dari nol.
- `sql/01_schema.sql` dan `sql/03_rbac.sh` hanya dijalankan saat volume database pertama kali dibuat.
- Sumber dataset (Kaggle):
  - Katy Kramer, *Walt Disney World Mock Data* (judul halaman: *Theme Park Resort Ticket Sales Analytics
    Dataset*), https://www.kaggle.com/datasets/katykramer/walt-disney-world-mock-data, data **simulasi**
    booking, dipakai sebagai ekspor sistem reservasi fiktif.
  - Chad Wambles, *Walt Disney World Wait Times and Crowd Calendar* -
    https://www.kaggle.com/datasets/chadwambles/walt-disney-world-wait-times, data nyata waktu tunggu dan
    crowd level empat taman WDW (sumber Queue-Times).
  - Lisensi masing-masing dataset: lihat panel *License* di halaman Kaggle di atas.
- Nama taman ditampilkan sebagai alias Vistaland (Vista Kingdom, Vista Discovery, Vista Studios,
  Vista Wildlands); nama sumber tetap disimpan di `dim_park.source_park_name`.
