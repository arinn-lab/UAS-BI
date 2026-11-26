"""
sumber_data.py
Mengambil data mart untuk dashboard dari salah satu dari dua sumber:

1. PostgreSQL (mode "langsung"): dashboard login sebagai vl_viewer yang
   hanya boleh membaca schema mart. Dipakai saat dijalankan di laptop
   bersama Docker.
2. Salinan data mart (mode "salinan"): file di dashboard/data hasil
   etl/export_snapshot.py. Dipakai saat dashboard di-deploy ke Streamlit
   Community Cloud, karena server Streamlit tidak bisa menjangkau database
   di laptop.

Pemilihan mode:
- DASHBOARD_MODE=db atau DASHBOARD_MODE=snapshot memaksa salah satu mode.
- Kalau tidak diisi: coba PostgreSQL dulu bila password viewer tersedia,
  kalau gagal atau tidak ada password, pakai salinan.
"""
import json
import os
from pathlib import Path

import pandas as pd
import streamlit as st

DASH_DIR = Path(__file__).resolve().parent
DATA_DIR = DASH_DIR / "data"

try:
    from dotenv import load_dotenv

    load_dotenv(DASH_DIR.parent / ".env", override=False)
except ImportError:
    pass

VIEWS = {
    "sales": "mart.v_sales_revenue",
    "ops": "mart.v_park_operations",
    "wait": "mart.v_wait_time",
}
FILES = {
    "sales": "sales_revenue.csv.gz",
    "ops": "park_operations.csv.gz",
    "wait": "wait_time.csv.gz",
}


def _engine():
    from sqlalchemy import create_engine
    from sqlalchemy.engine import URL

    password = os.getenv("DASHBOARD_DB_PASSWORD") or os.getenv("VIEWER_PASSWORD")
    url = URL.create(
        "postgresql+psycopg2",
        username=os.getenv("DASHBOARD_DB_USER", "vl_viewer"),
        password=password,
        host=os.getenv("DASHBOARD_DB_HOST", "localhost"),
        port=int(os.getenv("DASHBOARD_DB_PORT", "5433")),
        database=os.getenv("DB_NAME", "vistaland_dwh"),
        query={"connect_timeout": "5"},
    )
    return create_engine(url)


def _rapikan(d):
    d["sales"]["arrival_date"] = pd.to_datetime(d["sales"]["arrival_date"])
    d["sales"]["purchase_date"] = pd.to_datetime(d["sales"]["purchase_date"])
    d["ops"]["full_date"] = pd.to_datetime(d["ops"]["full_date"])
    for col in ["arrival_is_weekend", "arrival_is_holiday", "first_time_guest",
                "park_hopper", "lightning_lane", "dining_plan"]:
        d["sales"][col] = d["sales"][col].astype(bool)
    for col in ["is_weekend", "is_holiday", "is_rainy", "has_special_event",
                "has_early_entry", "has_extended_evening", "operating_minutes_missing"]:
        d["ops"][col] = d["ops"][col].astype(bool)
    return d


def _dari_db():
    eng = _engine()
    d = {k: pd.read_sql(f"SELECT * FROM {v}", eng) for k, v in VIEWS.items()}
    st_row = pd.read_sql("SELECT * FROM mart.v_status_data", eng).iloc[0]
    info = {
        "mode": "langsung",
        "keterangan": "PostgreSQL (schema mart, akun vl_viewer)",
        "mart_diperbarui": st_row["mart_diperbarui"],
        "status_validasi": st_row["status_validasi"],
    }
    return _rapikan(d), info


def _dari_salinan():
    d = {k: pd.read_csv(DATA_DIR / f) for k, f in FILES.items()}
    meta = json.loads((DATA_DIR / "status.json").read_text(encoding="utf-8"))
    info = {
        "mode": "salinan",
        "keterangan": "salinan data mart (hasil ekspor pipeline)",
        "mart_diperbarui": meta.get("mart_diperbarui"),
        "status_validasi": meta.get("status_validasi"),
        "diekspor_pada": meta.get("diekspor_pada"),
    }
    return _rapikan(d), info


@st.cache_data(ttl=600, show_spinner="Memuat data mart...")
def muat_data():
    mode = os.getenv("DASHBOARD_MODE", "").lower()
    ada_password = bool(os.getenv("DASHBOARD_DB_PASSWORD") or os.getenv("VIEWER_PASSWORD"))
    if mode == "snapshot":
        return _dari_salinan()
    if mode == "db":
        return _dari_db()
    if ada_password:
        try:
            return _dari_db()
        except Exception as exc:  # database mati -> pakai salinan
            d, info = _dari_salinan()
            info["catatan"] = f"Database tidak bisa dihubungi ({type(exc).__name__}), memakai salinan."
            return d, info
    return _dari_salinan()
