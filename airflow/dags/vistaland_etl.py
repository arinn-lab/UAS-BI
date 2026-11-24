"""
vistaland_etl.py
DAG Airflow Vistaland, mengikuti tabel Scheduling pada rancangan UTS
(zona waktu America/New_York / waktu Orlando):

  DAG                             jadwal              isi
  vistaland_extract_booking       harian 02:00        extract booking (incremental)
  vistaland_extract_calendar      harian 03:00        extract calendar (upsert)
  vistaland_extract_ridestats     bulanan tgl 1 04:00 extract ridestats (upsert)
  vistaland_transform_validasi    harian 04:30        aturan kualitas + ambang 1%
  vistaland_load_dimensi          harian 05:00        9 dimensi
  vistaland_load_fakta            harian 05:15        3 fakta
  vistaland_refresh_mart          harian 05:30        data mart, validasi, cek 06:00,
                                                      ringkasan Data Steward
  vistaland_backup                harian 23:00        backup terenkripsi + retensi
  vistaland_etl                   manual              seluruh pipeline berurutan
                                                      (demo / mengejar data setelah restore)

Dependensi antar DAG dijaga sensor: tiap DAG menunggu tahap sebelumnya
tercatat SUCCESS di audit.etl_log. Kalau tahap sebelumnya gagal, tahap
berikutnya tidak berjalan dan data lama di DWH tetap dipakai.

Semua task: retry 3 kali jeda 10 menit, lalu on_failure_callback
(log + audit.etl_log + email). Kegagalan kualitas data tidak di-retry.
"""
import os
import sys
import uuid
from datetime import datetime, timedelta

import pendulum
from airflow.providers.standard.operators.python import PythonOperator
from airflow.providers.standard.sensors.python import PythonSensor
from airflow.sdk import DAG

try:                                   # Airflow 3
    from airflow.sdk.exceptions import AirflowFailException
except ImportError:                    # cadangan
    from airflow.exceptions import AirflowFailException

# folder skrip ETL (di-mount dari folder etl proyek)
sys.path.insert(0, "/opt/airflow/project/etl")

RETRY_DELAY_MENIT = int(os.getenv("RETRY_DELAY_MINUTES", "10"))
TZ = "America/New_York"
START = pendulum.datetime(2026, 11, 1, tz=TZ)


def run_id_etl(context):
    """run_id Airflow terlalu panjang untuk kolom etl_log (36 karakter),
    jadi diubah jadi UUID yang tetap sama untuk satu DAG run."""
    rid = context.get("run_id") or context["dag_run"].run_id
    dag_id = context["dag"].dag_id if context.get("dag") else ""
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"{dag_id}/{rid}"))


# ---------------------------------------------------------------
# CALLBACK: dipanggil setelah semua retry habis dan task tetap gagal
# ---------------------------------------------------------------
def notifikasi_gagal(context):
    import config
    import notify

    logger = config.get_logger()
    ti = context["task_instance"]
    exc = context.get("exception")
    pesan = (f"DAG {ti.dag_id} | task {ti.task_id} | run {context.get('run_id')} | "
             f"error: {exc}")
    logger.error("CALLBACK KEGAGALAN | %s", pesan)

    # penerima email mengikuti tabel Error Handling UTS
    nama_exc = type(exc).__name__ if exc else ""
    if "DataQuality" in nama_exc or "AMBANG" in str(exc):
        judul, penerima = "DARURAT: ambang kualitas data terlampaui", ["engineer", "steward"]
    elif "OperationalError" in nama_exc or "could not connect" in str(exc):
        judul, penerima = "Kegagalan database", ["dba", "engineer"]
    else:
        judul, penerima = f"Task gagal: {ti.task_id}", ["engineer"]

    try:
        config.write_audit(config.get_engine(), run_id_etl(context),
                           f"callback_{ti.task_id}"[:60], "airflow", None, None, None,
                           "FAILED", pesan[:1500], datetime.now())
    except Exception as e:             # noqa: BLE001 (database bisa saja yang mati)
        logger.error("callback: gagal menulis audit.etl_log: %s", e)

    with open(config.LOG_DIR / "notifikasi_gagal.log", "a", encoding="utf-8") as f:
        f.write(f"{datetime.now():%Y-%m-%d %H:%M:%S} | {judul} | {pesan}\n")

    try:
        notify.send_email(judul, f"{pesan}\n\nWaktu: {datetime.now():%Y-%m-%d %H:%M:%S}\n"
                                 f"Buka Airflow (http://localhost:8081) untuk detail log.",
                          penerima)
    except Exception as e:             # noqa: BLE001
        logger.error("callback: email gagal dikirim: %s", e)


DEFAULT_ARGS = {
    "retries": 3,
    "retry_delay": timedelta(minutes=RETRY_DELAY_MENIT),
    "on_failure_callback": notifikasi_gagal,
}


# ---------------------------------------------------------------
# TASK
# ---------------------------------------------------------------
def t_extract(source, **context):
    import config
    import extract

    extract.extract_source(config.get_engine(), run_id_etl(context), source)


def t_validasi(**context):
    import config
    import transform_validate

    try:
        transform_validate.validate_staging(config.get_engine(), run_id_etl(context))
    except config.DataQualityError as exc:
        # data buruk tidak membaik dengan retry: langsung gagal + callback
        raise AirflowFailException(f"DataQualityError: {exc}") from exc


def t_dimensi(**context):
    import config
    import transform_dim

    transform_dim.load_dimensions(config.get_engine(), run_id_etl(context))


def t_fakta(**context):
    import config
    import pipeline

    pipeline.load_all_facts(config.get_engine(), run_id_etl(context))


def t_mart(**context):
    import config
    import pipeline

    pipeline.refresh_mart(config.get_engine(), run_id_etl(context))


def t_validasi_mart(**context):
    import config
    import pipeline

    pipeline.validate_source_mart(config.get_engine(), run_id_etl(context))


def t_ketepatan(**context):
    import config
    import pipeline

    pipeline.check_timeliness(config.get_engine(), run_id_etl(context))


def t_steward(**context):
    import config
    import pipeline

    pipeline.send_steward_summary(config.get_engine(), run_id_etl(context))


def t_backup(**context):
    import backup

    backup.run_backup(run_id_etl(context))


def t_retensi(**context):
    import config
    import retensi

    retensi.apply_retention(config.get_engine(), run_id_etl(context))


def sensor(stage):
    """Sensor yang menunggu tahap sebelumnya SUCCESS (dicek tiap 5 menit,
    maksimal 2 jam)."""
    def _cek():
        import config
        import pipeline

        return pipeline.stage_ready(config.get_engine(), stage)

    return PythonSensor(task_id=f"tunggu_sebelum_{stage}", python_callable=_cek,
                        poke_interval=300, timeout=7200, mode="reschedule",
                        retries=0)


def py(task_id, fn, **kw):
    return PythonOperator(task_id=task_id, python_callable=fn, **kw)


def dag(dag_id, schedule, description, tags):
    return DAG(dag_id=dag_id, description=description, schedule=schedule,
               start_date=START, catchup=False, max_active_runs=1,
               default_args=DEFAULT_ARGS, tags=["vistaland", *tags])


# ---------------------------------------------------------------
# DAG TERJADWAL (tabel Scheduling UTS)
# ---------------------------------------------------------------
with dag("vistaland_extract_booking", "0 2 * * *",
         "02:00 extract booking (incremental BookingID)", ["extract"]):
    py("extract_booking", t_extract, op_kwargs={"source": "booking"})

with dag("vistaland_extract_calendar", "0 3 * * *",
         "03:00 extract calendar (upsert park_id, date)", ["extract"]):
    py("extract_calendar", t_extract, op_kwargs={"source": "calendar"})

with dag("vistaland_extract_ridestats", "0 4 1 * *",
         "Tgl 1 tiap bulan 04:00 extract ridestats (upsert)", ["extract"]):
    py("extract_ridestats", t_extract, op_kwargs={"source": "ridestats"})

with dag("vistaland_transform_validasi", "30 4 * * *",
         "04:30 transform dan validasi kualitas data (ambang 1%)", ["transform"]):
    sensor("transform_validasi") >> py("transform_validasi", t_validasi, retries=0)

with dag("vistaland_load_dimensi", "0 5 * * *",
         "05:00 load 9 dimensi", ["load"]):
    sensor("load_dimensi") >> py("load_dimensi", t_dimensi)

with dag("vistaland_load_fakta", "15 5 * * *",
         "05:15 load 3 fakta", ["load"]):
    sensor("load_fakta") >> py("load_fakta", t_fakta)

with dag("vistaland_refresh_mart", "30 5 * * *",
         "05:30 refresh data mart, validasi, cek ketepatan 06:00, ringkasan steward",
         ["mart"]):
    (sensor("refresh_mart") >> py("refresh_mart", t_mart)
     >> py("validasi_source_mart", t_validasi_mart)
     >> py("cek_ketepatan_waktu", t_ketepatan)
     >> py("ringkasan_data_steward", t_steward))

with dag("vistaland_backup", "0 23 * * *",
         "23:00 backup database terenkripsi (RPO 24 jam) + retensi data", ["backup"]):
    py("backup_database", t_backup) >> py("retensi_data", t_retensi)

# ---------------------------------------------------------------
# DAG MANUAL: seluruh pipeline tanpa menunggu jam (demo, run pertama,
# atau menjalankan ulang setelah restore untuk mengejar data terakhir)
# ---------------------------------------------------------------
with dag("vistaland_etl", None,
         "Manual: seluruh pipeline Vistaland berurutan", ["manual"]):
    extracts = [py(f"extract_{s}", t_extract, op_kwargs={"source": s})
                for s in ("booking", "calendar", "ridestats")]
    (extracts >> py("transform_validasi", t_validasi, retries=0)
     >> py("load_dimensi", t_dimensi)
     >> py("load_fakta", t_fakta)
     >> py("refresh_mart", t_mart)
     >> py("validasi_source_mart", t_validasi_mart)
     >> py("ringkasan_data_steward", t_steward))
