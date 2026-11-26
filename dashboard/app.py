"""
Dashboard BI Vistaland (Streamlit), versi 1.

Jalankan dari folder proyek:
    streamlit run dashboard/app.py

Di laptop, dashboard membaca data mart PostgreSQL sebagai vl_viewer
(password dari file .env). Di Streamlit Community Cloud, dashboard
membaca salinan data mart di dashboard/data. Lihat sumber_data.py.
"""
from functools import partial
from pathlib import Path

import pandas as pd
import streamlit as st

import halaman
import tampilan as t
from sumber_data import muat_data

ASET = Path(__file__).resolve().parent / "aset"
st.set_page_config(page_title="Dashboard Vistaland", page_icon=str(ASET / "ikon.png"), layout="wide")
t.pasang_css()
st.logo(str(ASET / "logo.png"), size="large", icon_image=str(ASET / "ikon.png"))

try:
    data, info = muat_data()
except Exception as exc:
    st.error("Data tidak bisa dimuat. Kalau dijalankan di laptop, pastikan container "
             "vistaland_db berjalan (docker compose ps) dan VIEWER_PASSWORD di .env sudah "
             "diisi. Kalau memakai salinan, pastikan folder dashboard/data berisi file hasil "
             "python etl/export_snapshot.py.")
    st.exception(exc)
    st.stop()


def hal(fungsi, judul, ikon, url, default=False):
    return st.Page(partial(fungsi, data, info), title=judul, icon=ikon,
                   url_path=url, default=default)


nav = st.navigation({
    "Ikhtisar": [hal(halaman.ringkasan, "Ringkasan Eksekutif", ":material/dashboard:", "ringkasan", True)],
    "Analisis": [
        hal(halaman.penjualan, "Penjualan & Revenue", ":material/payments:", "penjualan"),
        hal(halaman.promo, "Validitas Promo", ":material/sell:", "promo"),
        hal(halaman.crowd, "Crowd & Operasional", ":material/groups:", "crowd"),
        hal(halaman.waktu_tunggu, "Waktu Tunggu Wahana", ":material/schedule:", "waktu-tunggu"),
    ],
    "Informasi": [hal(halaman.kamus, "Kamus KPI & Data", ":material/menu_book:", "kamus")],
})

nav.run()

# identitas organisasi selalu di bagian bawah sidebar, setelah filter halaman
with st.sidebar:
    st.divider()
    try:
        waktu = pd.Timestamp(info.get("mart_diperbarui"))
        if pd.isna(waktu):
            raise ValueError("waktu kosong")
        diperbarui = f"{waktu.day} {t.BULAN[waktu.month - 1]} {waktu.year}, {waktu:%H:%M}"
    except (TypeError, ValueError):
        diperbarui = "-"
    t.kartu_organisasi(diperbarui, info.get("catatan") or "")
