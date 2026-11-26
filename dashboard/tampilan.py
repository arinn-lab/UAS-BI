"""
tampilan.py
Gaya tampilan dashboard Vistaland, versi 1.

Mockup awal dibuat dengan bantuan Google Stitch, lalu disesuaikan. Komponen
HTML buatan sendiri (kepala halaman, kartu KPI, daftar tindak lanjut, daftar
batang) memakai kelas Tailwind CSS. File CSS-nya sudah dikompilasi ke
static/tailwind.css (lihat folder tailwind/ untuk konfigurasi dan cara
kompilasi ulang), jadi dashboard tidak butuh Node.js saat dijalankan.

Tema warna pastel tetap mengikuti referensi:
- warna taman memakai skema "light" dari Tol (2021), yang dirancang untuk
  batang atau sel berlabel dan tetap cukup terbedakan oleh pembaca buta warna,
- karena warna pastel kontrasnya rendah, setiap batang diberi label nilai
  atau disertai tabel angka. Menurut WCAG 2.2 (SC 1.4.11), grafik yang nilainya
  juga tampil sebagai teks tidak wajib memenuhi kontras 3:1,
- semua teks memakai warna gelap dengan kontras minimal 4,5:1 (SC 1.4.3),
- peta panas (heatmap) memakai skema berurutan YlOrBr dari Tol (2021).
Huruf: Bricolage Grotesque untuk judul dan angka, Figtree untuk teks biasa
(keduanya lisensi SIL OFL), disimpan di folder static.
"""
from contextlib import contextmanager
from pathlib import Path

import pandas as pd
import streamlit as st

FOLDER = Path(__file__).resolve().parent

UNGU = "#6A4FC0"       # warna utama antarmuka dan garis grafik (kontras 5,8:1 di putih)
LAVENDER = "#F7F4FE"   # sidebar
UTAMA = "#7B61C9"      # batang yang disorot
KONTEKS = "#DCD6EC"    # batang pembanding
SOROT = "#B0204F"      # teks "perlu perhatian" (kontras 6,6:1 di putih)
SOROT_ISI = "#F58FAE"  # isi batang "perlu ditinjau"
TEKS = "#2B2340"
TEKS_LEMAH = "#4A4360"   # teks sekunder, kontras 9:1 di putih
GARIS = "#E6E1F0"

# warna tetap tiap taman: skema "light" Tol (2021)
WARNA_TAMAN = {
    "Vista Kingdom": "#77AADD",
    "Vista Discovery": "#EE8866",
    "Vista Studios": "#44BB99",
    "Vista Wildlands": "#FFAABB",
}
WARNA_KOMPONEN = {"Tiket": "#9C86E0", "Hotel": "#77AADD", "Add-on": "#EEDD88"}
# skema berurutan YlOrBr (Tol, 2021): kuning muda berarti sepi, cokelat berarti padat
SKALA = [[0, "#FFFFE5"], [0.125, "#FFF7BC"], [0.25, "#FEE391"], [0.375, "#FEC44F"],
         [0.5, "#FB9A29"], [0.625, "#EC7014"], [0.75, "#CC4C02"], [0.875, "#993404"], [1, "#662506"]]

# titik warna di label KPI, dipakai bergantian dari kiri ke kanan
PASTEL = ["#9C86E0", "#44BB99", "#77AADD", "#EE8866", "#D9A6E8"]
PINK = "#F2A3BA"   # KPI yang perlu perhatian

BULAN = ["Jan", "Feb", "Mar", "Apr", "Mei", "Jun", "Jul", "Agu", "Sep", "Okt", "Nov", "Des"]
HARI = {"Monday": "Senin", "Tuesday": "Selasa", "Wednesday": "Rabu", "Thursday": "Kamis",
        "Friday": "Jumat", "Saturday": "Sabtu", "Sunday": "Minggu"}

JUDUL = "'Bricolage Grotesque', 'Segoe UI', sans-serif"
BADAN = "'Figtree', 'Segoe UI', sans-serif"

# kelas grid ditulis lengkap supaya terbaca oleh Tailwind saat kompilasi
GRID_KOLOM = {
    2: "tw-grid-cols-1 sm:tw-grid-cols-2",
    3: "tw-grid-cols-1 md:tw-grid-cols-3",
    4: "tw-grid-cols-2 lg:tw-grid-cols-4",
    5: "tw-grid-cols-2 lg:tw-grid-cols-5",
}

# CSS untuk elemen bawaan Streamlit (tidak bisa diberi kelas Tailwind langsung)
CSS = f"""
@font-face {{ font-family: 'Bricolage Grotesque'; src: url('app/static/bricolage.woff2') format('woff2');
              font-weight: 200 800; font-stretch: 75% 100%; font-display: swap; }}
@font-face {{ font-family: 'Figtree'; src: url('app/static/figtree.woff2') format('woff2');
              font-weight: 300 900; font-display: swap; }}
html, body, .stApp, .stApp p, .stApp li, .stApp input, .stApp button, .stApp label {{ font-family: {BADAN}; }}
.stApp {{ background: #FFFFFF; color: {TEKS}; }}
header[data-testid="stHeader"] {{ background: transparent; }}
.block-container {{ padding-top: 2.4rem; padding-bottom: 4rem; max-width: 1240px; }}
div[data-testid="stMainBlockContainer"] > div > div[data-testid="stVerticalBlock"] {{ gap: 1.25rem; }}
.stApp h4 {{ font-family: {JUDUL}; font-weight: 600; font-size: 1.2rem; margin: 1rem 0 0 0;
             padding: 0; color: {TEKS}; }}
.stApp a:hover {{ text-decoration: none; }}

/* Streamlit memberi margin bawah negatif pada markdown (untuk paragraf biasa).
   Komponen HTML buatan sendiri tidak memakai paragraf, jadi margin itu dinolkan
   supaya elemen tidak saling tumpuk. */
div[data-testid="stMarkdownContainer"]:has(> .komponen) {{ margin-bottom: 0; }}

/* sidebar */
section[data-testid="stSidebar"] {{ background: {LAVENDER}; border-right: 1px solid #EEE9FA; }}


/* panel putih: semua st.container yang dibuat lewat panel() */
div[class*="st-key-panel"] {{ background: #FFFFFF; border: 1px solid {GARIS}; border-radius: 20px;
      padding: 20px 22px 14px 22px; height: 100%; gap: .5rem; }}
/* panel yang bersebelahan dibuat sama tinggi */
div[data-testid="stHorizontalBlock"]:has(div[class*="st-key-panel"]) {{ align-items: stretch; }}
div[data-testid="stHorizontalBlock"]:has(div[class*="st-key-panel"]) > div[data-testid="stColumn"] > div[data-testid="stVerticalBlock"],
div[data-testid="stHorizontalBlock"]:has(div[class*="st-key-panel"]) > div[data-testid="stColumn"] > div[data-testid="stVerticalBlock"] > div[data-testid="stLayoutWrapper"] {{
      height: 100%; }}

/* tabel bawaan Streamlit: garis antarbaris dan antarkolom dibuat jelas */
div[data-testid="stDataFrame"] {{ border: 1px solid {GARIS}; border-radius: 12px; overflow: hidden; }}
div[data-testid="stTable"] table {{ font-size: .88rem; }}
div[data-testid="stTable"] th, div[data-testid="stTable"] td {{ border: 1px solid {GARIS} !important;
      vertical-align: top; color: {TEKS}; }}
div[data-testid="stTable"] thead th {{ background: #F7F4FE; font-weight: 600; }}
div[data-testid="stExpander"] details {{ border-color: {GARIS}; border-radius: 12px; }}
"""

# Gambar di kepala halaman. Untuk mengganti, cukup timpa file dashboard/static/ilustrasi_header.png
# (sebaiknya PNG berlatar transparan, kira-kira 700 x 500 piksel).
ILUSTRASI = "app/static/ilustrasi_header.png"


def pasang_css():
    tailwind = (FOLDER / "static" / "tailwind.css").read_text(encoding="utf-8")
    st.markdown(f"<style>{CSS}\n{tailwind}</style>", unsafe_allow_html=True)


def html(isi):
    st.markdown(f'<div class="komponen">{isi}</div>', unsafe_allow_html=True)


# ---------------- format angka ----------------
def angka(x, des=0):
    if x is None or pd.isna(x):
        return "-"
    s = f"{x:,.{des}f}"
    return s.replace(",", "#").replace(".", ",").replace("#", ".")


def uang(x, des=0):
    return "-" if x is None or pd.isna(x) else f"${angka(x, des)}"


def uang_ringkas(x):
    """Nilai besar untuk kartu KPI: $21,63 jt atau $812 rb."""
    if x is None or pd.isna(x):
        return "-"
    if abs(x) >= 1e6:
        return f"${angka(x / 1e6, 2)} jt"
    if abs(x) >= 1e4:
        return f"${angka(x / 1e3, 0)} rb"
    return uang(x)


def persen(x, des=1):
    return "-" if x is None or pd.isna(x) else f"{angka(x, des)}%"


def poin(x, des=1):
    if x is None or pd.isna(x):
        return "-"
    tanda = "+" if x > 0 else ""
    return f"{tanda}{angka(x, des)} poin"


def label_bulan(ts):
    ts = pd.Timestamp(ts)
    return f"{BULAN[ts.month - 1]} {ts.year}"


# ---------------- tata letak ----------------
_urut = {"kpi": 0, "panel": 0}


def atur_aksen(halaman):
    """Dipanggil di awal tiap halaman: mengulang urutan warna KPI dan nomor panel."""
    _urut["kpi"] = 0
    _urut["panel"] = 0


def panel():
    """Kotak putih bertepi tipis untuk grafik. Panel yang bersebelahan otomatis sama tinggi."""
    _urut["panel"] += 1
    return st.container(key=f"panel_{_urut['panel']}")


def spanduk(judul, untuk, menjawab):
    """Kepala halaman: judul, untuk siapa halaman ini, pertanyaan yang dijawab,
    dan ilustrasi taman hiburan (file gambar di folder static). Ilustrasi hanya
    ada di kepala halaman, tidak di dalam grafik."""
    html(
        '<div class="tw-flex tw-items-end tw-justify-between tw-gap-6 tw-overflow-hidden '
        'tw-rounded-3xl tw-bg-lavender-100 tw-min-h-[184px]">'
        '<div class="tw-self-center tw-max-w-xl tw-py-8 tw-pl-9 tw-pr-4">'
        f'<div class="tw-font-judul tw-text-[2.35rem] tw-font-semibold tw-leading-tight tw-tracking-tight tw-text-tinta">{judul}</div>'
        f'<div class="tw-mt-3 tw-text-[0.97rem] tw-leading-relaxed tw-text-tinta-lemah">Untuk '
        f'<span class="tw-font-semibold tw-text-tinta">{untuk}</span>. Menjawab {menjawab}.</div></div>'
        f'<img src="{ILUSTRASI}" alt="" class="tw-hidden lg:tw-block tw-h-[176px] tw-w-auto '
        f'tw-shrink-0 tw-self-center tw-mr-8 tw-my-3"></div>')


def subjudul(teks):
    """Judul bagian di halaman (misalnya "Perlu ditindaklanjuti")."""
    html(f'<div class="tw-mt-4 tw-mb-1 tw-font-judul tw-text-[1.25rem] tw-font-semibold tw-text-tinta">{teks}</div>')


def judul_filter(teks="Filter halaman ini"):
    st.sidebar.markdown(
        f'<div class="tw-font-judul tw-text-base tw-font-semibold tw-text-tinta tw-mt-1">{teks}</div>',
        unsafe_allow_html=True)


# ---------------- kartu KPI ----------------
_papan = {"aktif": False, "isi": []}


@contextmanager
def papan():
    """Mengumpulkan kartu KPI lalu menampilkannya dalam satu grid, jadi semua
    kartu sama tinggi dan sejajar."""
    _papan["aktif"], _papan["isi"] = True, []
    try:
        yield
    finally:
        _papan["aktif"] = False
        isi = _papan["isi"]
        if isi:
            kolom = GRID_KOLOM.get(len(isi), GRID_KOLOM[4])
            html(f'<div class="tw-grid {kolom} tw-gap-4">{"".join(isi)}</div>')


def tiket(label, nilai, konteks="", sorot=False, tautan=None, nama_tautan=""):
    """Satu kartu KPI. Kalau sorot=True, angka berwarna merah tua dan konteks
    diberi tanda teks, jadi informasinya tidak hanya lewat warna. Kalau ada
    tautan, kartu bisa diklik untuk membuka halaman rinciannya."""
    if sorot:
        titik = PINK
        kotak = "tw-border-rose-200 tw-bg-rose-50"
        kelas_nilai = "tw-text-rose-700"
        konteks = f'<span class="tw-font-semibold tw-text-rose-700">Perlu perhatian.</span> {konteks}'
    else:
        titik = PASTEL[_urut["kpi"] % len(PASTEL)]
        _urut["kpi"] += 1
        kotak = "tw-border-garis tw-bg-white"
        kelas_nilai = "tw-text-tinta"
    bawah = ""
    tag, atribut = "div", ""
    if tautan:
        tag = "a"
        atribut = f' href="{tautan}" target="_self" title="Buka halaman {nama_tautan}"'
        bawah = (f'<div class="tw-mt-auto tw-pt-4 tw-text-[0.84rem] tw-font-semibold tw-text-ungu-700 '
                 f'group-hover:tw-underline">Lihat {nama_tautan}</div>')
    kartu = (
        f'<{tag}{atribut} class="tw-group tw-flex tw-flex-col tw-rounded-2xl tw-border tw-border-solid {kotak} tw-p-5 '
        f'tw-no-underline tw-transition tw-duration-150 hover:tw-border-ungu-300 hover:tw-shadow-kartu">'
        f'<div class="tw-flex tw-min-h-[2.6rem] tw-items-start tw-gap-2 tw-text-[0.9rem] tw-font-medium tw-leading-snug tw-text-tinta-lemah">'
        f'<span class="tw-mt-[5px] tw-h-2.5 tw-w-2.5 tw-shrink-0 tw-rounded-full" style="background:{titik}"></span>'
        f'<span>{label}</span></div>'
        f'<div class="tw-mt-3 tw-font-judul tw-text-[1.9rem] tw-font-semibold tw-leading-none tw-tracking-tight '
        f'tw-tabular-nums {kelas_nilai}">{nilai}</div>'
        f'<div class="tw-mt-2 tw-text-[0.86rem] tw-leading-normal tw-text-tinta-lemah">{konteks}</div>'
        f'{bawah}</{tag}>')
    if _papan["aktif"]:
        _papan["isi"].append(kartu)
    else:
        html(kartu)


# ---------------- isi panel ----------------
def judul_grafik(judul, keterangan=""):
    ket = (f'<div class="tw-mt-1 tw-text-[0.88rem] tw-leading-normal tw-text-tinta-lemah">{keterangan}</div>'
           if keterangan else "")
    html(f'<div><div class="tw-font-judul tw-text-[1.06rem] tw-font-semibold tw-leading-snug tw-text-tinta">'
         f'{judul}</div>{ket}</div>')


def catatan(teks):
    html(f'<div class="tw-text-[0.86rem] tw-leading-normal tw-text-tinta-lemah">{teks}</div>')


def temuan(teks, sorot=False):
    garis = "tw-border-l-rose-700" if sorot else "tw-border-l-ungu-500"
    html(f'<div class="tw-rounded-xl tw-border tw-border-solid tw-border-garis tw-border-l-4 {garis} tw-bg-white '
         f'tw-px-4 tw-py-3 tw-text-sm">{teks}</div>')


def daftar_tindak(item):
    """Kartu tindak lanjut dalam satu grid (sama tinggi). item: list dict berisi
    judul, isi, siapa, warna, latar, tautan, nama_tautan."""
    kartu = []
    for it in item:
        link = ""
        if it.get("tautan"):
            link = (f'<a href="{it["tautan"]}" target="_self" class="tw-text-[0.86rem] tw-font-semibold '
                    f'tw-text-ungu-700 tw-no-underline hover:tw-underline">Buka halaman {it["nama_tautan"]}</a>')
        kartu.append(
            f'<div class="tw-flex tw-flex-col tw-rounded-2xl tw-border tw-border-solid tw-border-garis tw-p-6" '
            f'style="background:{it.get("latar", "#FFFFFF")}">'
            f'<div class="tw-flex tw-min-h-[2.7rem] tw-items-start tw-gap-2.5 tw-font-judul tw-text-[1.05rem] '
            f'tw-font-semibold tw-leading-snug tw-text-tinta"><span class="tw-mt-[7px] tw-h-2.5 tw-w-2.5 '
            f'tw-shrink-0 tw-rounded-full" style="background:{it["warna"]}"></span><span>{it["judul"]}</span></div>'
            f'<div class="tw-flex-1 tw-pt-3 tw-pl-5 tw-text-[0.93rem] tw-leading-relaxed tw-text-tinta-lemah">'
            f'{it["isi"]}</div>'
            f'<div class="tw-mt-5 tw-flex tw-flex-col tw-gap-1 tw-border-0 tw-border-t tw-border-solid '
            f'tw-border-garis tw-pt-4 tw-pl-5 tw-min-h-[5.4rem]"><span class="tw-text-[0.82rem] tw-text-tinta-lemah">'
            f'Ditujukan ke <span class="tw-font-semibold tw-text-tinta">{it.get("siapa", "-")}</span></span>'
            f'{link}</div></div>')
    html(f'<div class="tw-grid {GRID_KOLOM.get(len(kartu), GRID_KOLOM[3])} tw-gap-4">{"".join(kartu)}</div>')


def tabel_angka(df, judul="Lihat angka dalam tabel"):
    """Tabel pendamping grafik, supaya angka tetap bisa dibaca tanpa bergantung pada warna."""
    with st.expander(judul):
        st.dataframe(df, width="stretch")


def daftar_batang(seri, format_nilai, skala_maks=100, warna=None):
    """Bar horizontal terurut dalam bentuk HTML. Panjang batang memakai skala
    tetap 0 sampai skala_maks supaya perbandingan antartaman tidak dilebih-lebihkan."""
    seri = seri.sort_values(ascending=False)
    baris = []
    for nama, nilai in seri.items():
        w = max(0, min(100, nilai / skala_maks * 100))
        c = (warna or WARNA_TAMAN).get(nama, UTAMA)
        baris.append(
            f'<div><div class="tw-flex tw-items-baseline tw-justify-between tw-text-[0.92rem]">'
            f'<span class="tw-text-tinta">{nama}</span>'
            f'<span class="tw-font-semibold tw-tabular-nums tw-text-tinta">{format_nilai(nilai)}</span></div>'
            f'<div class="tw-mt-2 tw-h-2.5 tw-rounded-full tw-bg-lavender-100">'
            f'<div class="tw-h-2.5 tw-rounded-full" style="width:{w:.1f}%;background:{c}"></div></div></div>')
    skala = (f'<div class="tw-flex tw-justify-between tw-text-[0.74rem] tw-tabular-nums tw-text-tinta-lemah">'
             f'<span>0</span><span>{angka(skala_maks)}</span></div>')
    html(f'<div class="tw-flex tw-flex-col tw-gap-4 tw-pt-2">{"".join(baris)}{skala}</div>')


def chip_taman(daftar):
    isi = "".join(
        f'<span class="tw-inline-flex tw-items-center tw-gap-1.5 tw-text-[0.82rem] tw-text-tinta">'
        f'<span class="tw-h-2.5 tw-w-2.5 tw-rounded-full" style="background:{WARNA_TAMAN.get(x, UTAMA)}"></span>{x}</span>'
        for x in daftar)
    html(f'<div class="tw-flex tw-flex-wrap tw-gap-x-4 tw-gap-y-1">{isi}</div>')


# ---------------- grafik ----------------
def gaya(fig, tinggi=330, x="", y="", legenda=True, sumbu_nilai="y"):
    fig.update_layout(
        bargap=0.3,
        height=tinggi, margin=dict(l=4, r=12, t=8, b=4),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Figtree, Segoe UI, sans-serif", size=13, color=TEKS), separators=",.",
        showlegend=legenda,
        legend=dict(orientation="h", yanchor="bottom", y=1.0, x=0, title_text="", font=dict(color=TEKS, size=13)),
        hoverlabel=dict(bgcolor="#FFFFFF", font_size=13, font_family="Figtree, sans-serif",
                        bordercolor=GARIS),
    )
    sumbu = dict(zeroline=False, linecolor="#CFC7E3", gridcolor="#EFEBF7",
                 tickfont=dict(color=TEKS_LEMAH, size=12.5), title_font=dict(color=TEKS, size=13))
    fig.update_xaxes(title_text=x, showgrid=(sumbu_nilai == "x"), **sumbu)
    fig.update_yaxes(title_text=y, showgrid=(sumbu_nilai == "y"), **sumbu)
    return fig


def tampil(fig, **kwargs):
    return st.plotly_chart(fig, width="stretch", config={"displaylogo": False}, **kwargs)


def kosong():
    st.info("Tidak ada data untuk kombinasi filter ini. Tambah lagi pilihan pada filter di sidebar kiri.")


def kartu_organisasi(diperbarui, catatan=""):
    """Identitas organisasi di bagian bawah sidebar (Vistaland adalah organisasi fiktif)."""
    ekstra = (f'<div class="tw-mt-2 tw-text-[0.8rem] tw-leading-snug tw-text-rose-700">{catatan}</div>'
              if catatan else "")
    st.sidebar.markdown(
        f'<div class="komponen"><div class="tw-rounded-2xl tw-border tw-border-solid tw-border-garis tw-bg-white tw-p-4">'
        f'<div class="tw-flex tw-items-center tw-gap-3"><img src="app/static/ikon.png" alt="" '
        f'class="tw-h-9 tw-w-9 tw-rounded-xl"><div><div class="tw-font-judul tw-text-[0.98rem] '
        f'tw-font-semibold tw-leading-tight tw-text-tinta">Vistaland Theme Park</div>'
        f'<div class="tw-text-[0.8rem] tw-leading-snug tw-text-tinta-lemah">Orlando, Florida</div></div></div>'
        f'<div class="tw-mt-3 tw-text-[0.84rem] tw-leading-normal tw-text-tinta">Divisi Business Intelligence</div>'
        f'<div class="tw-text-[0.8rem] tw-leading-normal tw-text-tinta-lemah">Resort dengan 4 taman hiburan '
        f'dan 3 kategori hotel</div>'
        f'<div class="tw-mt-3 tw-border-0 tw-border-t tw-border-solid tw-border-garis tw-pt-3 '
        f'tw-text-[0.8rem] tw-leading-snug tw-text-tinta-lemah">Data diperbarui<br>'
        f'<span class="tw-font-semibold tw-text-tinta">{diperbarui}</span></div>{ekstra}</div></div>',
        unsafe_allow_html=True)
