"""
export_snapshot.py
Menyalin isi data mart ke folder dashboard/data supaya dashboard bisa
di-deploy ke Streamlit Community Cloud (server Streamlit tidak bisa
menjangkau PostgreSQL yang berjalan di Docker laptop).

Pembacaan dilakukan dengan akun vl_viewer, jadi isi salinan sama persis
dengan yang boleh dilihat dashboard. File yang dihasilkan:
    dashboard/data/sales_revenue.csv.gz
    dashboard/data/park_operations.csv.gz
    dashboard/data/wait_time.csv.gz
    dashboard/data/status.json

Dijalankan otomatis oleh Airflow (task ekspor_snapshot setelah validasi
mart), atau manual dari folder proyek:
    python etl/export_snapshot.py
"""
import gzip
import json
import os
import sys
from datetime import datetime

import pandas as pd
from sqlalchemy import create_engine
from sqlalchemy.engine import URL

import config

logger = config.get_logger()

OUT_DIR = config.BASE_DIR / "dashboard" / "data"

VIEWS = {
    "sales_revenue": "mart.v_sales_revenue",
    "park_operations": "mart.v_park_operations",
    "wait_time": "mart.v_wait_time",
}


def viewer_engine():
    password = os.getenv("DASHBOARD_DB_PASSWORD") or os.getenv("VIEWER_PASSWORD")
    if not password:
        raise RuntimeError("VIEWER_PASSWORD belum diisi di file .env")
    url = URL.create(
        "postgresql+psycopg2",
        username=os.getenv("DASHBOARD_DB_USER", "vl_viewer"),
        password=password,
        host=os.getenv("DASHBOARD_DB_HOST", config.DB_HOST),
        port=int(os.getenv("DASHBOARD_DB_PORT", str(config.DB_PORT))),
        database=config.DB_NAME,
    )
    return create_engine(url)


def _tulis_csv_gz(df, path):
    # ditulis biasa (tanpa menyalin metadata file) supaya aman di folder
    # bind mount Windows
    data = df.to_csv(index=False).encode("utf-8")
    with open(path, "wb") as f:
        f.write(gzip.compress(data, mtime=0))


def export_snapshot(run_id=None):
    started = datetime.now()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    eng = viewer_engine()
    jumlah = {}
    for nama, view in VIEWS.items():
        df = pd.read_sql(f"SELECT * FROM {view}", eng)
        _tulis_csv_gz(df, OUT_DIR / f"{nama}.csv.gz")
        jumlah[nama] = len(df)

    status = pd.read_sql("SELECT * FROM mart.v_status_data", eng).iloc[0]

    def iso(v):
        return None if pd.isna(v) else pd.Timestamp(v).isoformat(timespec="minutes")

    meta = {
        "diekspor_pada": started.isoformat(timespec="minutes"),
        "mart_diperbarui": iso(status["mart_diperbarui"]),
        "status_validasi": status["status_validasi"],
        "waktu_validasi": iso(status["waktu_validasi"]),
        "jumlah_baris": jumlah,
    }
    (OUT_DIR / "status.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    pesan = ", ".join(f"{k}={v}" for k, v in jumlah.items())
    logger.info("ekspor_snapshot | %s | folder %s", pesan, OUT_DIR)

    # audit ditulis dengan akun engineer (viewer tidak boleh menulis audit)
    if run_id:
        config.write_audit(config.get_engine(), run_id, "ekspor_snapshot",
                           "schema mart", sum(jumlah.values()), sum(jumlah.values()),
                           0, "SUCCESS", f"salinan data mart untuk dashboard: {pesan}",
                           started)
    return meta


if __name__ == "__main__":
    try:
        info = export_snapshot()
        print(json.dumps(info, indent=2))
    except Exception as exc:
        logger.error("ekspor_snapshot gagal: %s", exc)
        sys.exit(1)
