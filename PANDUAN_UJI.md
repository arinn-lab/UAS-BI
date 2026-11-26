# Panduan Uji dan Dokumentasi Bukti, Vistaland DWH

Ikuti dari atas ke bawah di PowerShell. Setiap tanda **Bukti-xx** berarti ambil screenshot lalu
simpan dengan nama itu (misalnya `Bukti-03.png`). Nomornya sama dengan kotak `[Tempel Bukti-xx]`
di laporan.

Semua perintah dijalankan dari folder proyek:
```powershell
cd C:\Users\USER\Downloads\vistaland-dwh
```
Pakai dua jendela PowerShell: satu untuk dashboard (dibiarkan terbuka), satu untuk perintah lain.

---

## 0. Pasang paket baru (sekali saja)

1. Ekstrak zip ke folder sementara, lalu salin isinya menimpa folder proyek. File `.env`, `.git`,
   dan `.venv-dashboard` milikmu tidak ikut tertimpa karena tidak ada di zip.
   ```powershell
   Expand-Archive $HOME\Downloads\vistaland-dwh-final.zip -DestinationPath $HOME\Downloads\final_tmp -Force
   Copy-Item -Recurse -Force $HOME\Downloads\final_tmp\vistaland-dwh\* .
   Copy-Item -Recurse -Force $HOME\Downloads\final_tmp\vistaland-dwh\.streamlit .
   Copy-Item -Force $HOME\Downloads\final_tmp\vistaland-dwh\.gitignore .
   Remove-Item dashboard\requirements-dashboard.txt -ErrorAction SilentlyContinue
   Remove-Item -Recurse -Force dashboard\__pycache__ -ErrorAction SilentlyContinue
   Remove-Item -Recurse -Force $HOME\Downloads\final_tmp
   ```
2. Cek `.env` masih ada dan terisi (`notepad .env`). Untuk uji kegagalan nanti, ubah
   `RETRY_DELAY_MINUTES=1` sekarang supaya tidak perlu menunggu 30 menit.

## 1. Bangun ulang dari nol

```powershell
docker compose down -v
docker compose up -d --build
docker compose ps
```
`down -v` sengaja dipakai di sini supaya database, audit, dan riwayat Airflow bersih dan semua bukti
berasal dari satu kali jalan. Tunggu sampai 4 container `Up` dan `vistaland_db` `(healthy)`.

**Bukti-01**: hasil `docker compose ps` (4 container berjalan).

## 2. Login Airflow

```powershell
docker compose exec airflow cat /opt/airflow/simple_auth_manager_passwords.json.generated
```
Buka http://localhost:8081, login `admin` dengan password di atas. Kalau file belum ada, tunggu 1 menit.

**Bukti-02**: halaman Dags berisi 9 DAG `vistaland_*` beserta jadwalnya.

> Saat Airflow pertama menyala, DAG terjadwal ikut jalan sekali untuk interval terakhir. Itu normal.
> Bukti utama diambil dari DAG manual `vistaland_etl` di langkah 3.

## 3. Jalankan pipeline ETL

Buka DAG `vistaland_etl`, klik Trigger, lalu Trigger lagi. Tunggu sampai semua task hijau (sekitar
30 detik), buka tampilan Graph, lalu klik tombol fit view.

**Bukti-03**: Graph `vistaland_etl` semua success, termasuk task baru `ekspor_snapshot`.

## 4. Validasi hasil load

```powershell
docker exec vistaland_db psql -U vistaland -d vistaland_dwh -c "SELECT 'fact_booking' tabel, count(*) FROM dw.fact_booking UNION ALL SELECT 'fact_crowd_daily', count(*) FROM dw.fact_crowd_daily UNION ALL SELECT 'fact_wait_time', count(*) FROM dw.fact_wait_time UNION ALL SELECT 'dim_date', count(*) FROM dw.dim_date UNION ALL SELECT 'dim_park', count(*) FROM dw.dim_park UNION ALL SELECT 'dim_ride', count(*) FROM dw.dim_ride UNION ALL SELECT 'dim_customer', count(*) FROM dw.dim_customer UNION ALL SELECT 'dim_package', count(*) FROM dw.dim_package UNION ALL SELECT 'dim_channel_promo', count(*) FROM dw.dim_channel_promo UNION ALL SELECT 'dim_event', count(*) FROM dw.dim_event UNION ALL SELECT 'dim_day_condition', count(*) FROM dw.dim_day_condition UNION ALL SELECT 'dim_year', count(*) FROM dw.dim_year;"
```
Harus: 5000, 2552, 174, 730, 4, 97, 80, 144, 12, 4, 9, 2.

**Bukti-04**: jumlah baris 3 fakta dan 9 dimensi.

```powershell
docker exec vistaland_db psql -U vistaland -d vistaland_dwh -c "SELECT status, message FROM audit.etl_log WHERE step='validasi_source_mart' ORDER BY finished_at DESC LIMIT 1;"
docker exec vistaland_db psql -U vistaland -d vistaland_dwh -c "SELECT step, status, rows_in, rows_out, rows_rejected FROM audit.etl_log ORDER BY log_id DESC LIMIT 25;"
```
**Bukti-05**: hasil validasi source vs mart (SUCCESS, revenue 21633888.40 sama).
**Bukti-06**: isi `audit.etl_log`.

```powershell
Get-Content sql\02_mart_dan_validasi.sql | docker exec -i vistaland_db psql -U vl_engineer -d vistaland_dwh
```
**Bukti-07**: tabel validasi per channel, per taman (alias dan nama sumber), dan Promo Validity Rate.

```powershell
Get-ChildItem dashboard\data
Get-Content dashboard\data\status.json
```
**Bukti-20**: isi folder `dashboard\data` (3 file `.csv.gz` dan `status.json`) dan isi `status.json`
(jumlah baris 5000, 2552, 174).

## 5. Notifikasi dan object storage

- http://localhost:8025, buka email "Ringkasan kualitas data harian". **Bukti-08**
- http://localhost:9001, login `MINIO_ROOT_USER` / `MINIO_ROOT_PASSWORD` dari `.env`, buka
  Buckets, `vistaland-raw`, folder `booking`. **Bukti-09**

> Mailpit tidak menyimpan email setelah container restart. Ambil screenshot email sebelum langkah 9.

## 6. Keamanan (RBAC)

```powershell
Get-Content sql\05_uji_rbac.sql | docker exec -i vistaland_db psql -U vl_viewer -d vistaland_dwh
Get-Content sql\05_uji_rbac.sql | docker exec -i vistaland_db psql -U vl_analyst -d vistaland_dwh
Get-Content sql\05_uji_rbac.sql | docker exec -i vistaland_db psql -U vl_engineer -d vistaland_dwh
```
**Bukti-10**: ketiga hasil (viewer ditolak di dw/stg, analyst ditolak di stg, engineer boleh).

## 7. Backup dan disaster recovery

```powershell
docker compose exec airflow python /opt/airflow/project/etl/backup.py backup
docker compose exec airflow python /opt/airflow/project/etl/backup.py restore
```
**Bukti-11**: hasil kedua perintah (durasi restore, "RTO TERPENUHI", "COCOK").
**Bukti-12**: Silo, bucket `vistaland-backup` berisi file `.dump.enc`.

## 8. Performa query

```powershell
Get-Content sql\04_explain_analyze.sql | docker exec -i vistaland_db psql -U vistaland -d vistaland_dwh > docs\hasil_explain.txt
notepad docs\hasil_explain.txt
```
**Bukti-13**: bagian "Execution Time" Q1 dan Q2 (A tanpa indeks, B dengan indeks). Kalau angkanya
beda dengan tabel EXPLAIN di laporan subbab 3.7, ganti angka di laporan dengan angka barumu.

## 9. Uji kegagalan: file sumber hilang (retry dan callback)

```powershell
Rename-Item data\raw\ridestats.csv ridestats_hilang.csv
```
Trigger `vistaland_etl`. Task `extract_ridestats` dicoba 4 kali (1 kali awal dan 3 retry) lalu merah,
task setelahnya berstatus upstream_failed.
```powershell
Get-Content logs\notifikasi_gagal.log -Tail 2
Rename-Item data\raw\ridestats_hilang.csv ridestats.csv
```
**Bukti-14**: Graph dengan `extract_ridestats` merah dan task turunan oranye.
**Bukti-15**: email "Task gagal: extract_ridestats" di Mailpit dan isi `notifikasi_gagal.log`.

## 10. Uji ambang kualitas 1%

```powershell
docker compose exec airflow python /opt/airflow/project/etl/uji_ambang.py buat
```
Trigger `vistaland_etl`. Task `transform_validasi` langsung merah tanpa retry.

**Bukti-16**: Graph dengan `transform_validasi` merah.
**Bukti-17**: email "DARURAT: ambang kualitas data terlampaui" (60/5060 = 1,19%).

```powershell
docker compose exec airflow python /opt/airflow/project/etl/uji_ambang.py pulihkan
```
Trigger `vistaland_etl` sekali lagi sampai hijau, lalu ulangi perintah jumlah baris di langkah 4.

**Bukti-18**: Graph hijau lagi dan jumlah baris tetap 5000/2552/174.

Setelah selesai, kembalikan `RETRY_DELAY_MINUTES=10` di `.env` lalu `docker compose up -d`.

## 11. Dashboard di laptop

Di jendela PowerShell kedua:
```powershell
cd C:\Users\USER\Downloads\vistaland-dwh
.\.venv-dashboard\Scripts\Activate.ps1
pip install -r dashboard\requirements.txt
streamlit run dashboard\app.py
```
Buka http://localhost:8501. Coba keenam halaman dan ubah beberapa filter (tahun, channel, taman,
termasuk mengosongkan satu filter). Catat hasilnya untuk baris "Filter dashboard" di tabel
pengujian laporan.

**Bukti-19**: halaman Ringkasan Eksekutif, dengan sidebar yang menunjukkan
"Sumber: PostgreSQL (schema mart, akun vl_viewer)".

Ini adalah dashboard versi 1. Gambar versi 1 sudah ada di laporan subbab 3.5, jadi tidak perlu
screenshot setiap halaman lagi.

## 12. GitHub

```powershell
git add .
git commit -m "Dashboard v1 berbasis acuan desain, salinan data mart untuk deploy, instrumen MTI"
git push
```
Pastikan folder `dashboard/data` ikut ter-push (dibutuhkan dashboard online).

**Bukti-23**: halaman https://github.com/arinn-lab/UAS-BI (README tampil).

## 13. Deploy ke Streamlit Community Cloud

1. Buka https://share.streamlit.io, pilih masuk dengan GitHub, izinkan akses ke repository.
2. Klik **Create app**, pilih deploy dari GitHub.
3. Isi: Repository `arinn-lab/UAS-BI`, Branch `main`, Main file path `dashboard/app.py`.
   App URL boleh diganti, misalnya `vistaland-dashboard`.
4. Klik **Deploy** dan tunggu beberapa menit. Tidak perlu mengisi secrets.
5. Buka tautan yang muncul dari HP atau laptop lain untuk memastikan bisa diakses tanpa login.

**Bukti-21**: dashboard online dengan alamat `.streamlit.app` terlihat di address bar.

Kirim tautannya ke aku supaya bisa dimasukkan ke laporan dan README. Setiap kali pipeline dijalankan
ulang dan kamu ingin versi online ikut berubah, cukup `git add dashboard\data`, commit, lalu push.

---

## 14. Metode MTI (bukan perintah PowerShell)

Instrumen ada di `docs\mti\instrumen_MTI.xlsx`.

**Heuristic Evaluation (dashboard versi 1, oleh kamu sendiri)**
1. Buka dashboard dan kerjakan 7 tugas di sheet **1 Skenario Tugas**.
2. Periksa setiap halaman memakai pertanyaan di sheet **2 Panduan Heuristik**.
3. Tulis setiap masalah di sheet **3 Form Heuristic** (prinsip, lokasi, deskripsi, severity 0 sampai 4,
   rekomendasi). Kolom Evaluator diisi namamu. Kalau ada teman yang ikut menilai, tulis namanya
   di baris temuannya.
4. Sheet **4 Rekap Heuristic** terisi otomatis. Kirim file ini ke aku untuk perbaikan dashboard,
   hasilnya dashboard versi 2.

**Tugas dan SUS (dashboard versi 2, minimal 20 responden)**
1. Buat satu Google Form mengikuti sheet **5 Naskah Google Form** (pembuka, tugas, 10 pernyataan SUS,
   saran). Isi tautan dashboard online di bagian tugas.
2. Sebarkan ke minimal 20 responden. Beri kode responden R01, R02, dan seterusnya.
3. Salin jawaban SUS ke sheet **6 Data SUS** dan data tugas ke sheet **7 Data Tugas** (kolom kuning).
   Skor, rata-rata, grade, kategori, dan persentase keberhasilan tugas terhitung otomatis.
4. Masukkan angkanya ke laporan di bagian bertanda `[ISI ...]`.

**Bukti-22**: tampilan Google Form.
**Bukti-24**: dashboard versi 2 setelah perbaikan hasil Heuristic Evaluation.
