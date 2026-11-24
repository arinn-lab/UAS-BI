# Langkah pindah ke versi revisi (sekali saja)

Versi ini mengubah struktur tabel (nama kolom, primary key) dan menambah RBAC,
jadi database lama harus dibangun ulang dari nol. Data sumber tidak berubah,
hasil akhirnya tetap harus 5.000 / 2.552 / 174 dan revenue 21.633.888,40.

1. (opsional) simpan bukti lama: screenshot Airflow dan isi audit.etl_log.
2. Ganti isi folder proyek dengan versi ini (folder data\raw tetap sama).
3. `copy .env.example .env`, isi semua password dan BACKUP_ENCRYPTION_KEY.
4. Hapus container DAN volume database lama, lalu bangun ulang:
   ```powershell
   docker compose down -v
   docker compose up -d --build
   docker compose ps
   ```
   `-v` di sini memang disengaja: supaya sql/01_schema.sql dan sql/03_rbac.sh
   dijalankan ulang. Setelah ini JANGAN pakai `-v` lagi.
5. Login Airflow (http://localhost:8081), trigger DAG `vistaland_etl`.
6. Cek validasi (README bagian Pengujian), lalu buka dashboard.

Kalau `docker compose up` gagal di db dengan pesan `03_rbac.sh: ... \r`,
file itu tersimpan dengan akhir baris Windows (CRLF). Buka di VS Code, ubah
"CRLF" menjadi "LF" di pojok kanan bawah, simpan, lalu ulangi langkah 4.
