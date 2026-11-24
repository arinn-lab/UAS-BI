"""
Dashboard Vistaland (Streamlit) - membaca data mart di PostgreSQL.
Jalankan dari folder proyek:  streamlit run dashboard/app.py
"""
import os
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st
from sqlalchemy import create_engine
from sqlalchemy.engine import URL

st.set_page_config(page_title="Vistaland Dashboard", page_icon="🎢", layout="wide",
                   initial_sidebar_state="collapsed")

PALETTE = ["#8b7cf6", "#f472b6", "#fb923c", "#60a5fa", "#34d399", "#fbbf24"]

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
html, body, [class*="css"], .stApp { font-family: 'Inter', sans-serif; }
.stApp { background: #f4f5f9; }
header[data-testid="stHeader"] { background: transparent; }
.block-container { padding-top: 1.4rem; padding-bottom: 2rem; max-width: 1400px; }

/* kartu putih membulat */
div[class*="st-key-card_"] {
  background: #ffffff; border-radius: 24px; padding: 20px 24px;
  box-shadow: 0 6px 24px rgba(30, 30, 60, 0.06); margin-bottom: 6px;
}
/* kartu hero bergradasi (seperti kartu Visa di contoh) */
div[class*="st-key-hero_"] {
  background: linear-gradient(135deg, #7c6cf0 0%, #c77dff 45%, #ff9a8b 100%);
  border-radius: 24px; padding: 22px 26px; color: #fff;
  box-shadow: 0 10px 28px rgba(124, 108, 240, 0.35);
}
div[class*="st-key-hero_"] * { color: #fff !important; }

.brand { font-weight: 700; letter-spacing: .5px; font-size: 1.05rem; }
.page-title { font-size: 2rem; font-weight: 700; margin: 0; line-height: 1.1; }
.page-sub { color: #8a8aa3; font-size: .9rem; margin-top: 2px; }
.card-title { font-weight: 600; font-size: 1rem; margin-bottom: 4px; }
.kpi-label { color: #8a8aa3; font-size: .8rem; }
.kpi-value { font-size: 1.7rem; font-weight: 700; line-height: 1.2; }
.kpi-sub { color: #8a8aa3; font-size: .78rem; }
.hero-label { opacity: .85; font-size: .85rem; }
.hero-value { font-size: 2.2rem; font-weight: 700; line-height: 1.2; }
.hero-sub { opacity: .9; font-size: .85rem; margin-top: 4px; }

.bar-wrap { margin: 10px 0 14px 0; }
.bar-head { display: flex; justify-content: space-between; font-size: .85rem; margin-bottom: 5px; }
.bar-bg { background: #eceef4; border-radius: 99px; height: 9px; overflow: hidden; }
.bar-fill { height: 9px; border-radius: 99px; background: linear-gradient(90deg, #8b7cf6, #f472b6); }

.row-item { display: flex; align-items: center; justify-content: space-between;
            padding: 9px 0; border-bottom: 1px solid #f0f1f6; }
.row-item:last-child { border-bottom: none; }
.row-left { display: flex; align-items: center; gap: 12px; }
.dot { width: 36px; height: 36px; border-radius: 50%; background: #1b1b2f; color: #fff;
       display: flex; align-items: center; justify-content: center; font-weight: 600; font-size: .8rem; }
.row-title { font-weight: 600; font-size: .9rem; }
.row-sub { color: #8a8aa3; font-size: .75rem; }
.row-amt { font-weight: 600; font-size: .9rem; }

.park-card { border-radius: 20px; padding: 16px 18px; color: #1b1b2f; }
.park-name { font-weight: 600; font-size: .9rem; }
.park-val { font-size: 1.8rem; font-weight: 700; }
.park-sub { font-size: .75rem; opacity: .75; }

/* tab berbentuk pil */
.stTabs [data-baseweb="tab-list"] { gap: 8px; border-bottom: none; }
.stTabs [data-baseweb="tab"] { background: #fff; border-radius: 999px; padding: 8px 20px; height: auto;
                               box-shadow: 0 2px 8px rgba(30,30,60,.06); }
.stTabs [aria-selected="true"] { background: #111; }
.stTabs [aria-selected="true"] p { color: #fff !important; }
.stTabs [data-baseweb="tab-highlight"], .stTabs [data-baseweb="tab-border"] { display: none; }
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)


# ---------- koneksi dan pengambilan data ----------
# Dashboard login sebagai vl_viewer (peran viewer: hanya boleh membaca schema
# mart). Password dibaca dari file .env di folder proyek.
try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parent.parent / ".env", override=False)
except ImportError:
    pass


@st.cache_resource
def get_engine():
    password = os.getenv("DASHBOARD_DB_PASSWORD") or os.getenv("VIEWER_PASSWORD")
    if not password:
        raise RuntimeError("VIEWER_PASSWORD belum diisi di file .env")
    url = URL.create(
        "postgresql+psycopg2",
        username=os.getenv("DASHBOARD_DB_USER", "vl_viewer"),
        password=password,
        host=os.getenv("DASHBOARD_DB_HOST", "localhost"),
        port=int(os.getenv("DASHBOARD_DB_PORT", "5433")),
        database=os.getenv("DB_NAME", "vistaland_dwh"),
    )
    return create_engine(url)


@st.cache_data(ttl=300)
def load_data():
    eng = get_engine()
    sales = pd.read_sql("SELECT * FROM mart.v_sales_revenue", eng)
    ops = pd.read_sql("SELECT * FROM mart.v_park_operations", eng)
    wait = pd.read_sql("SELECT * FROM mart.v_wait_time", eng)
    sales["arrival_date"] = pd.to_datetime(sales["arrival_date"])
    sales["purchase_date"] = pd.to_datetime(sales["purchase_date"])
    ops["full_date"] = pd.to_datetime(ops["full_date"])
    return sales, ops, wait


# ---------- helper tampilan ----------
def kpi(label, value, sub=""):
    st.markdown(f'<div class="kpi-label">{label}</div><div class="kpi-value">{value}</div>'
                f'<div class="kpi-sub">{sub}</div>', unsafe_allow_html=True)


def title(text):
    st.markdown(f'<div class="card-title">{text}</div>', unsafe_allow_html=True)


def style(fig, h=320, legend=True):
    fig.update_layout(height=h, margin=dict(l=0, r=0, t=10, b=0),
                      paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                      font=dict(family="Inter, sans-serif", size=12, color="#1b1b2f"),
                      showlegend=legend,
                      legend=dict(orientation="h", y=-0.2, x=0, title_text=""),
                      colorway=PALETTE)
    fig.update_xaxes(showgrid=False, title_text="")
    fig.update_yaxes(gridcolor="#eceef4", title_text="")
    return fig


def money(x):
    return f"${x:,.0f}"


try:
    sales, ops, wait = load_data()
except Exception as e:
    st.error("Tidak bisa terhubung ke database. Pastikan container vistaland_db "
             "berjalan (docker compose ps), port 5433 benar, dan VIEWER_PASSWORD "
             "di file .env sudah diisi.")
    st.exception(e)
    st.stop()

# ---------- header dan filter ----------
h1, h2 = st.columns([1, 2])
with h1:
    st.markdown('<div class="brand">🎢 VISTALAND</div>', unsafe_allow_html=True)
    st.markdown('<div class="page-title">Dashboard</div>'
                '<div class="page-sub">Data warehouse · dimuat oleh pipeline Airflow</div>',
                unsafe_allow_html=True)
with h2:
    years = sorted(sales["arrival_year"].unique())
    channels = sorted(sales["sales_channel"].dropna().unique())
    parks = sorted(ops["park_name"].unique())
    f1, f2, f3 = st.columns(3)
    sel_years = f1.multiselect("Tahun kedatangan", years, default=years)
    sel_channels = f2.multiselect("Sales channel", channels, default=channels)
    sel_parks = f3.multiselect("Taman", parks, default=parks)

s = sales[sales["arrival_year"].isin(sel_years) & sales["sales_channel"].isin(sel_channels)]
o = ops[ops["year"].isin(sel_years) & ops["park_name"].isin(sel_parks)]
w = wait[wait["park_name"].isin(sel_parks)]

tab1, tab2, tab3 = st.tabs(["Penjualan & Revenue", "Crowd Taman", "Waktu Tunggu Wahana"])

# ================= TAB 1: PENJUALAN =================
with tab1:
    if s.empty:
        st.warning("Tidak ada data untuk filter yang dipilih.")
    else:
        total = s["total_revenue"].sum()
        k0, k1, k2, k3 = st.columns([1.4, 1, 1, 1])
        with k0:
            with st.container(key="hero_total"):
                st.markdown(f'<div class="hero-label">Total revenue</div>'
                            f'<div class="hero-value">{money(total)}</div>'
                            f'<div class="hero-sub">{len(s):,} booking · rata-rata '
                            f'{money(s["total_revenue"].mean())}/booking</div>',
                            unsafe_allow_html=True)
        with k1:
            with st.container(key="card_k1"):
                kpi("Revenue per tamu", money(s["revenue_per_guest"].mean()), "rata-rata")
        with k2:
            with st.container(key="card_k2"):
                kpi("Lama kunjungan", f"{s['trip_length'].mean():.1f} hari", "rata-rata per booking")
        with k3:
            with st.container(key="card_k3"):
                kpi("Lead time", f"{s['lead_time_days'].mean():.0f} hari", "beli sampai datang")

        left, mid, right = st.columns([1.5, 1.1, 1])

        with left:
            with st.container(key="card_trend"):
                title("Revenue per periode")
                per = st.segmented_control("Periode", ["Bulan", "Kuartal", "Tahun"], default="Bulan",
                                           label_visibility="collapsed", key="per") or "Bulan"
                d = s["arrival_date"]
                if per == "Bulan":
                    p = d.dt.to_period("M")
                elif per == "Kuartal":
                    p = d.dt.to_period("Q")
                else:
                    p = d.dt.to_period("Y")
                g = (s.assign(periode=p)
                       .groupby("periode")[["ticket_revenue", "hotel_revenue", "addon_revenue"]]
                       .sum().sort_index())
                g.index = g.index.astype(str)
                g = g.rename(columns={"ticket_revenue": "Tiket", "hotel_revenue": "Hotel",
                                      "addon_revenue": "Add-on"})
                fig = px.bar(g, x=g.index, y=["Tiket", "Hotel", "Add-on"], barmode="stack")
                fig.update_traces(marker_cornerradius=6)
                st.plotly_chart(style(fig, 340), width="stretch")

        with mid:
            with st.container(key="card_donut"):
                title("Komposisi revenue")
                dim_map = {"Kategori paket": "resort_category", "Sales channel": "sales_channel",
                           "Segmen customer": "customer_segment"}
                dim_label = st.segmented_control("Dimensi", list(dim_map), default="Kategori paket",
                                                 label_visibility="collapsed", key="dim") or "Kategori paket"
                dg = s.groupby(dim_map[dim_label], as_index=False)["total_revenue"].sum()
                fig = px.pie(dg, names=dim_map[dim_label], values="total_revenue", hole=0.68)
                fig.update_traces(textinfo="none", marker=dict(line=dict(color="#fff", width=3)))
                fig.add_annotation(text=f"Total<br><b>{money(total)}</b>", showarrow=False,
                                   font=dict(size=15))
                st.plotly_chart(style(fig, 340), width="stretch")

        with right:
            with st.container(key="card_share"):
                title("Komponen revenue")
                comps = [("Tiket", s["ticket_revenue"].sum()), ("Hotel", s["hotel_revenue"].sum()),
                         ("Add-on", s["addon_revenue"].sum())]
                for name, val in comps:
                    pct = val / total * 100 if total else 0
                    st.markdown(
                        f'<div class="bar-wrap"><div class="bar-head"><span>{name}</span>'
                        f'<span><b>{money(val)}</b> · {pct:.0f}%</span></div>'
                        f'<div class="bar-bg"><div class="bar-fill" style="width:{pct:.1f}%"></div></div></div>',
                        unsafe_allow_html=True)

        b1, b2 = st.columns([1, 1])
        with b1:
            with st.container(key="card_state"):
                title("10 asal customer dengan revenue tertinggi")
                bs = (s.groupby("customer_state", as_index=False)["total_revenue"].sum()
                        .nlargest(10, "total_revenue").sort_values("total_revenue"))
                fig = px.bar(bs, x="total_revenue", y="customer_state", orientation="h")
                fig.update_traces(marker_color="#8b7cf6", marker_cornerradius=6)
                st.plotly_chart(style(fig, 360, legend=False), width="stretch")
        with b2:
            with st.container(key="card_last"):
                title("Booking terbaru")
                last = s.sort_values("purchase_date", ascending=False).head(7)
                rows = ""
                for _, r in last.iterrows():
                    rows += (f'<div class="row-item"><div class="row-left">'
                             f'<div class="dot">{str(r["customer_state"])[:2].upper()}</div>'
                             f'<div><div class="row-title">{r["resort_category"]} · {r["sales_channel"]}</div>'
                             f'<div class="row-sub">dibeli {r["purchase_date"]:%d %b %Y} · '
                             f'{int(r["total_guests"])} tamu</div></div></div>'
                             f'<div class="row-amt">{money(r["total_revenue"])}</div></div>')
                st.markdown(rows, unsafe_allow_html=True)

# ================= TAB 2: CROWD =================
with tab2:
    if o.empty:
        st.warning("Tidak ada data untuk filter yang dipilih.")
    else:
        avg_hours = o["operating_minutes_observed"].mean() / 60
        k0, k1, k2 = st.columns([1.4, 1, 1])
        with k0:
            with st.container(key="hero_crowd"):
                st.markdown(f'<div class="hero-label">Rata-rata crowd level</div>'
                            f'<div class="hero-value">{o["crowd_level_pct"].mean():.1f}%</div>'
                            f'<div class="hero-sub">{len(o):,} hari-taman diamati</div>',
                            unsafe_allow_html=True)
        with k1:
            with st.container(key="card_c1"):
                kpi("Hari hujan", f"{int(o['is_rainy'].sum()):,}", "jumlah hari-taman")
        with k2:
            with st.container(key="card_c2"):
                hrs = f"{avg_hours:.1f} jam" if pd.notna(avg_hours) else "-"
                kpi("Jam operasional", hrs, "rata-rata, hanya data asli")

        cols = st.columns(len(sel_parks))
        grads = ["#e9e4ff", "#ffe4ee", "#ffeedd", "#dff0ff", "#dcf7ea", "#fff3cd"]
        for i, pk in enumerate(sel_parks):
            sub = o[o["park_name"] == pk]
            if sub.empty:
                continue
            with cols[i]:
                st.markdown(f'<div class="park-card" style="background:{grads[i % 6]}">'
                            f'<div class="park-name">{pk}</div>'
                            f'<div class="park-val">{sub["crowd_level_pct"].mean():.1f}%</div>'
                            f'<div class="park-sub">rata-rata crowd · {int(sub["is_rainy"].sum())} hari hujan</div>'
                            f'</div>', unsafe_allow_html=True)

        t1, t2 = st.columns([1.6, 1])
        with t1:
            with st.container(key="card_crowdtrend"):
                title("Tren crowd level bulanan")
                mc = (o.assign(bulan=o["full_date"].dt.to_period("M").dt.to_timestamp())
                        .groupby(["bulan", "park_name"], as_index=False)["crowd_level_pct"].mean())
                fig = px.line(mc, x="bulan", y="crowd_level_pct", color="park_name", markers=True)
                fig.update_traces(line_shape="spline")
                st.plotly_chart(style(fig, 340), width="stretch")
        with t2:
            with st.container(key="card_crowdcmp"):
                title("Pembanding rata-rata crowd")
                rows = []
                for lab, ser in [("Hari kerja", o[~o["is_weekend"]]), ("Akhir pekan", o[o["is_weekend"]]),
                                 ("Tidak hujan", o[~o["is_rainy"]]), ("Hujan", o[o["is_rainy"]])]:
                    if not ser.empty:
                        rows.append({"kondisi": lab, "crowd": ser["crowd_level_pct"].mean()})
                cmp = pd.DataFrame(rows)
                fig = px.bar(cmp, x="crowd", y="kondisi", orientation="h", color="kondisi")
                fig.update_traces(marker_cornerradius=6)
                st.plotly_chart(style(fig, 340, legend=False), width="stretch")
        st.caption("Jam operasional hanya menghitung data asli. Baris hasil imputasi dikecualikan "
                   "(kolom operating_minutes_observed).")

# ================= TAB 3: WAKTU TUNGGU =================
with tab3:
    if w.empty:
        st.warning("Tidak ada data untuk filter yang dipilih.")
    else:
        with st.container(key="card_waitfilter"):
            years_w = sorted(w["year"].unique())
            sel_y = st.segmented_control("Tahun", years_w, default=years_w[-1], key="wy") or years_w[-1]
        wy = w[w["year"] == sel_y]
        longest = wy.loc[wy["avg_wait_minutes"].idxmax()]
        k0, k1, k2 = st.columns([1.4, 1, 1])
        with k0:
            with st.container(key="hero_wait"):
                st.markdown(f'<div class="hero-label">Wahana tunggu terlama ({sel_y})</div>'
                            f'<div class="hero-value">{longest["avg_wait_minutes"]:.0f} menit</div>'
                            f'<div class="hero-sub">{longest["ride_name"]} · {longest["park_name"]}</div>',
                            unsafe_allow_html=True)
        with k1:
            with st.container(key="card_w1"):
                kpi("Rata-rata tunggu", f"{wy['avg_wait_minutes'].mean():.0f} menit", "semua wahana")
        with k2:
            with st.container(key="card_w2"):
                kpi("Jumlah wahana", f"{len(wy):,}", "tercatat")

        l, r = st.columns([1.3, 1])
        with l:
            with st.container(key="card_waitbar"):
                title("10 wahana dengan tunggu terlama")
                top = wy.nlargest(10, "avg_wait_minutes").sort_values("avg_wait_minutes")
                fig = px.bar(top, x="avg_wait_minutes", y="ride_name", orientation="h", color="park_name")
                fig.update_traces(marker_cornerradius=6)
                st.plotly_chart(style(fig, 400), width="stretch")
        with r:
            with st.container(key="card_waittbl"):
                title("Semua wahana")
                st.dataframe(wy.sort_values("avg_wait_minutes", ascending=False)
                               [["park_name", "ride_name", "ride_status", "avg_wait_minutes",
                                 "max_wait_minutes"]],
                             width="stretch", hide_index=True, height=400)
