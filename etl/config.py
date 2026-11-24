"""
config.py
Pengaturan proyek: lokasi file, koneksi database per peran, logging, audit,
dan helper zona waktu.

Semua kredensial diambil dari environment variable. Saat dijalankan di
container Airflow, nilainya diisi docker-compose dari file .env. Saat
dijalankan manual dari laptop (python etl/run_etl.py), file .env di folder
proyek dibaca otomatis kalau paket python-dotenv terpasang.
"""
import logging
import os
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL

# lokasi folder dan file sumber
BASE_DIR = Path(__file__).resolve().parent.parent
RAW_DIR = BASE_DIR / "data" / "raw"
SQL_DIR = BASE_DIR / "sql"
LOG_DIR = BASE_DIR / "logs"
BACKUP_DIR = Path(os.getenv("BACKUP_DIR", str(BASE_DIR / "backups")))
LOG_DIR.mkdir(exist_ok=True)

# .env hanya dibaca kalau ada dan python-dotenv terpasang (tidak wajib)
try:
    from dotenv import load_dotenv

    load_dotenv(BASE_DIR / ".env", override=False)
except ImportError:
    pass

BOOKING_FILE = RAW_DIR / "Theme Park Mock Data.xlsx"
CALENDAR_FILE = RAW_DIR / "calendar_enriched.csv.xlsx"
RIDESTATS_FILE = RAW_DIR / "ridestats.csv"

# zona waktu operasional Vistaland (Orlando), dipakai untuk jadwal dan
# pengecekan ketepatan waktu data (sebelum 06:00)
TZ_OPERASIONAL = ZoneInfo("America/New_York")

# koneksi database. Default host/port untuk menjalankan dari laptop
# (port 5433 di host -> 5432 di container).
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", "5433"))
DB_NAME = os.getenv("DB_NAME", "vistaland_dwh")

# ETL memakai user engineer (least privilege), backup/restore memakai admin
DB_USER = os.getenv("DB_USER", "vl_engineer")
DB_PASSWORD = os.getenv("DB_PASSWORD") or os.getenv("ENGINEER_PASSWORD")
DB_ADMIN_USER = os.getenv("DB_ADMIN_USER", "vistaland")
DB_ADMIN_PASSWORD = os.getenv("DB_ADMIN_PASSWORD") or os.getenv("POSTGRES_ADMIN_PASSWORD")

# aturan kualitas data dari UTS: baris ditolak > 1% menghentikan load fakta
REJECT_THRESHOLD = float(os.getenv("REJECT_THRESHOLD", "0.01"))

# retensi dari rancangan Storage UTS
RETENSI_STAGING_HARI = 90
RETENSI_AUDIT_BULAN = 24
RETENSI_BACKUP_HARI = 30


class DataQualityError(Exception):
    """Dilempar kalau ambang kualitas data terlampaui. Load fakta harus
    berhenti dan data lama di DWH tetap dipakai (tidak perlu retry)."""


def _url(user, password, database=None):
    if not password:
        raise RuntimeError(
            f"Password untuk user database '{user}' belum diisi. "
            "Salin .env.example menjadi .env lalu isi passwordnya."
        )
    return URL.create(
        "postgresql+psycopg2",
        username=user,
        password=password,
        host=DB_HOST,
        port=DB_PORT,
        database=database or DB_NAME,
    )


def get_engine():
    """Engine untuk ETL (user engineer)."""
    return create_engine(_url(DB_USER, DB_PASSWORD), pool_pre_ping=True)


def get_admin_engine(database=None):
    """Engine untuk tugas DBA (backup, restore, cek RBAC)."""
    return create_engine(_url(DB_ADMIN_USER, DB_ADMIN_PASSWORD, database),
                         pool_pre_ping=True)


def get_logger(name="etl"):
    """Log ditulis ke layar dan ke logs/etl.log."""
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger
    logger.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")

    file_handler = logging.FileHandler(LOG_DIR / "etl.log", encoding="utf-8")
    file_handler.setFormatter(fmt)
    console = logging.StreamHandler()
    console.setFormatter(fmt)

    logger.addHandler(file_handler)
    logger.addHandler(console)
    return logger


def now_operasional():
    """Waktu sekarang di zona waktu operasional (America/New_York)."""
    return datetime.now(TZ_OPERASIONAL)


def write_audit(engine, run_id, step, source_name, rows_in, rows_out,
                rows_rejected, status, message, started_at):
    """Catat satu langkah ETL ke tabel audit.etl_log."""
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO audit.etl_log
                    (run_id, step, source_name, rows_in, rows_out,
                     rows_rejected, status, message, started_at, finished_at)
                VALUES
                    (:run_id, :step, :source_name, :rows_in, :rows_out,
                     :rows_rejected, :status, :message, :started_at, :finished_at)
                """
            ),
            {
                "run_id": run_id,
                "step": step,
                "source_name": source_name,
                "rows_in": rows_in,
                "rows_out": rows_out,
                "rows_rejected": rows_rejected,
                "status": status,
                "message": message,
                "started_at": started_at,
                "finished_at": datetime.now(),
            },
        )


def write_dq(conn, run_id, check_name, table_name, checked, failed, detail,
             status=None):
    """Catat hasil satu pengecekan kualitas ke audit.data_quality_log."""
    if status is None:
        status = "PASS" if not failed else "WARN"
    conn.execute(
        text(
            """
            INSERT INTO audit.data_quality_log
                (run_id, check_name, table_name, rows_checked, rows_failed,
                 status, detail)
            VALUES (:run_id, :check_name, :table_name, :checked, :failed,
                    :status, :detail)
            """
        ),
        {"run_id": run_id, "check_name": check_name, "table_name": table_name,
         "checked": checked, "failed": failed, "status": status,
         "detail": detail},
    )


def last_success(engine, step, within_hours=None):
    """Waktu SUCCESS terakhir sebuah step di audit.etl_log (atau None).
    Dipakai sensor Airflow untuk memastikan tahap sebelumnya sudah selesai."""
    sql = ("SELECT MAX(finished_at) FROM audit.etl_log "
           "WHERE step = :step AND status = 'SUCCESS'")
    params = {"step": step}
    if within_hours is not None:
        sql += " AND finished_at >= :batas"
        params["batas"] = datetime.now() - timedelta(hours=within_hours)
    with engine.connect() as conn:
        return conn.execute(text(sql), params).scalar()
