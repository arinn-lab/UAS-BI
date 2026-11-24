"""
backup.py
Backup dan Disaster Recovery sesuai rancangan UTS:
  - backup penuh harian 23:00 dengan pg_dump (format custom)      -> RPO 24 jam
  - file backup dienkripsi (Fernet/AES) sebelum disimpan
  - disimpan terpisah dari database utama: folder backups/ di host dan
    object storage MinIO (bucket vistaland-backup)
  - retensi 30 hari
  - uji restore ke database terpisah, waktu pemulihan diukur   -> RTO 4 jam

Butuh pg_dump/pg_restore versi 17 (sudah dipasang di image Airflow) dan
environment variable BACKUP_ENCRYPTION_KEY.

Uji restore manual (dari folder proyek):
    docker compose exec airflow python /opt/airflow/project/etl/backup.py restore
"""
import os
import subprocess
import sys
import tempfile
import time
import uuid
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy import text

import config
import storage

logger = config.get_logger()

RTO_TARGET_JAM = 4
RPO_TARGET_JAM = 24


def _fernet():
    from cryptography.fernet import Fernet

    key = os.getenv("BACKUP_ENCRYPTION_KEY")
    if not key:
        raise RuntimeError("BACKUP_ENCRYPTION_KEY belum diisi di .env")
    return Fernet(key.encode())


def _pg_env():
    env = os.environ.copy()
    env["PGPASSWORD"] = config.DB_ADMIN_PASSWORD or ""
    return env


def _pg_args():
    return ["-h", config.DB_HOST, "-p", str(config.DB_PORT), "-U", config.DB_ADMIN_USER]


def run_backup(run_id):
    """Buat backup terenkripsi, simpan lokal + MinIO, hapus backup > 30 hari."""
    started = datetime.now()
    engine = config.get_admin_engine()
    config.BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = started.strftime("%Y%m%d_%H%M%S")
    out = config.BACKUP_DIR / f"{config.DB_NAME}_{stamp}.dump.enc"

    try:
        with tempfile.TemporaryDirectory() as tmp:
            dump = Path(tmp) / "db.dump"
            subprocess.run(["pg_dump", *_pg_args(), "-d", config.DB_NAME,
                            "-Fc", "-f", str(dump)],
                           check=True, env=_pg_env(), capture_output=True, text=True)
            out.write_bytes(_fernet().encrypt(dump.read_bytes()))

        size_mb = out.stat().st_size / 1_048_576
        lokasi = [str(out)]
        try:
            obj = storage.upload_backup(out)
            if obj:
                lokasi.append(f"minio://{obj}")
        except Exception as exc:          # noqa: BLE001
            logger.error("backup | upload ke MinIO gagal: %s", exc)
            lokasi.append(f"MinIO GAGAL: {exc}")

        # retensi 30 hari (lokal dan MinIO)
        batas = datetime.now() - timedelta(days=config.RETENSI_BACKUP_HARI)
        hapus_lokal = 0
        for f in config.BACKUP_DIR.glob("*.dump.enc"):
            if datetime.fromtimestamp(f.stat().st_mtime) < batas:
                f.unlink()
                hapus_lokal += 1
        try:
            hapus_minio = storage.delete_old_backups(config.RETENSI_BACKUP_HARI)
        except Exception as exc:          # noqa: BLE001
            hapus_minio = f"gagal ({exc})"

        pesan = (f"backup terenkripsi {size_mb:.2f} MB -> {' ; '.join(lokasi)} | "
                 f"dihapus (>30 hari): lokal={hapus_lokal}, minio={hapus_minio} | "
                 f"RPO {RPO_TARGET_JAM} jam")
        logger.info("backup_database | %s | OK", pesan)
        config.write_audit(engine, run_id, "backup_database", config.DB_NAME, None, None,
                           None, "SUCCESS", pesan, started)
        return out

    except subprocess.CalledProcessError as exc:
        pesan = f"pg_dump gagal: {exc.stderr.strip()[:1000]}"
        logger.error("backup_database | %s", pesan)
        config.write_audit(engine, run_id, "backup_database", config.DB_NAME, None, None,
                           None, "FAILED", pesan, started)
        raise RuntimeError(pesan) from exc
    except Exception as exc:
        logger.error("backup_database | GAGAL | %s", exc)
        config.write_audit(engine, run_id, "backup_database", config.DB_NAME, None, None,
                           None, "FAILED", str(exc)[:1500], started)
        raise


def _ringkasan(engine):
    with engine.connect() as conn:
        return conn.execute(text("""
            SELECT (SELECT COUNT(*) FROM dw.fact_booking),
                   (SELECT COUNT(*) FROM dw.fact_crowd_daily),
                   (SELECT COUNT(*) FROM dw.fact_wait_time),
                   (SELECT COALESCE(SUM(total_revenue), 0) FROM dw.fact_booking)
        """)).fetchone()


def run_restore_test(run_id=None, target_db="vistaland_restore_test", backup_file=None):
    """Pulihkan backup terbaru ke database terpisah, ukur waktunya (RTO),
    lalu cocokkan jumlah baris fakta dan total revenue dengan database utama."""
    if target_db == config.DB_NAME:
        raise ValueError("Uji restore tidak boleh menimpa database utama.")
    run_id = run_id or str(uuid.uuid4())
    started = datetime.now()
    t0 = time.monotonic()
    admin = config.get_admin_engine()

    try:
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            # 1. ambil file backup: dari argumen, MinIO, atau folder lokal
            if backup_file:
                enc, asal = Path(backup_file), "file"
            else:
                name = None
                try:
                    name = storage.latest_backup_name()
                except Exception as exc:  # noqa: BLE001
                    logger.warning("restore | MinIO tidak bisa dibaca: %s", exc)
                if name:
                    enc = storage.download_backup(name, tmp / name)
                    asal = f"minio://{storage.BACKUP_BUCKET}/{name}"
                else:
                    files = sorted(config.BACKUP_DIR.glob("*.dump.enc"))
                    if not files:
                        raise FileNotFoundError("Belum ada file backup.")
                    enc, asal = files[-1], str(files[-1])

            dump = tmp / "db.dump"
            dump.write_bytes(_fernet().decrypt(Path(enc).read_bytes()))

            # 2. buat database tujuan yang bersih
            with admin.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
                conn.execute(text(f'DROP DATABASE IF EXISTS "{target_db}" WITH (FORCE)'))
                conn.execute(text(f'CREATE DATABASE "{target_db}"'))

            # 3. restore
            subprocess.run(["pg_restore", *_pg_args(), "-d", target_db, "--no-owner",
                            "--exit-on-error", str(dump)],
                           check=True, env=_pg_env(), capture_output=True, text=True)

        durasi = time.monotonic() - t0

        # 4. verifikasi isi hasil restore vs database utama
        utama = _ringkasan(admin)
        pulih = _ringkasan(config.get_admin_engine(target_db))
        cocok = tuple(utama) == tuple(pulih)
        rto_ok = durasi <= RTO_TARGET_JAM * 3600
        pesan = (f"sumber={asal} -> database {target_db} | durasi {durasi:.1f} detik "
                 f"(target RTO {RTO_TARGET_JAM} jam: {'TERPENUHI' if rto_ok else 'TIDAK'}) | "
                 f"utama booking/crowd/wait/revenue={tuple(utama)} | "
                 f"hasil restore={tuple(pulih)} | {'COCOK' if cocok else 'BERBEDA'}")
        status = "SUCCESS" if (cocok and rto_ok) else "FAILED"
        logger.info("uji_restore | %s | %s", status, pesan)
        config.write_audit(admin, run_id, "uji_restore", target_db, None, None, None,
                           status, pesan, started)
        if status != "SUCCESS":
            raise RuntimeError(pesan)
        return pesan

    except subprocess.CalledProcessError as exc:
        pesan = f"pg_restore gagal: {exc.stderr.strip()[:1000]}"
        config.write_audit(admin, run_id, "uji_restore", target_db, None, None, None,
                           "FAILED", pesan, started)
        raise RuntimeError(pesan) from exc


if __name__ == "__main__":
    perintah = sys.argv[1] if len(sys.argv) > 1 else ""
    if perintah == "backup":
        print(run_backup(str(uuid.uuid4())))
    elif perintah == "restore":
        berkas = sys.argv[2] if len(sys.argv) > 2 else None
        print(run_restore_test(backup_file=berkas))
    else:
        print("Pakai: python etl/backup.py backup | restore [file.dump.enc]")
        sys.exit(1)
