"""
halaman.py
Isi tiap halaman dashboard. Urutan isi halaman: kartu KPI di atas, grafik
pembanding di tengah, tabel rinci di bawah (pola tata letak dari Bach dkk.,
2023). Judul grafik ditulis sebagai kalimat temuan dan dihitung ulang setiap
filter berubah (heuristik "kesimpulan yang jelas" dari Setlur dkk., 2023).
"""
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

import tampilan as t


# ======================================================================
# helper filter
# ======================================================================
def filter_tahun(key, tahun, boleh_semua=True, default=None):
    pilihan = (["Semua"] if boleh_semua else []) + [str(x) for x in tahun]
    awal = default or pilihan[0]
    nilai = st.sidebar.segmented_control("Tahun", pilihan, default=awal, key=key)
    nilai = nilai or awal
    return None if nilai == "Semua" else int(nilai)


def saring_tahun(df, kolom, th):
    return df if th is None else df[df[kolom] == th]


def bar_urut(df, kat, nilai, sorot_atas=True, teks=None, tinggi=None):
    """Bar horizontal terurut. Batang teratas diberi warna utama, sisanya abu-abu."""
    df = df.sort_values(nilai, ascending=True)
    if set(df[kat]).issubset(t.WARNA_TAMAN):
        # setiap taman selalu memakai warnanya sendiri
        warna = [t.WARNA_TAMAN[k] for k in df[kat]]
    else:
        warna = [t.KONTEKS] * len(df)
        if sorot_atas and len(df):
            warna[-1] = t.UTAMA
    fig = go.Figure(go.Bar(x=df[nilai], y=df[kat], orientation="h", marker_color=warna,
                           text=teks if teks is not None else None, textposition="outside",
                           cliponaxis=False))
    fig.update_traces(hovertemplate="%{y}: %{x:,.0f}<extra></extra>")
    fig = t.gaya(fig, tinggi or max(220, 34 * len(df) + 60), legenda=False, sumbu_nilai="x")
    if len(df) and teks is not None:
        # ruang tambahan di kanan supaya label angka tidak terpotong
        fig.update_xaxes(range=[0, df[nilai].max() * 1.38])
    return fig


def teratas(seri):
    """Nama kategori dengan nilai tertinggi. Kalau ada yang sama besar, semua disebut."""
    puncak = seri.max()
    nama = [str(x) for x in seri[seri == puncak].index]
    return " dan ".join(nama)


# ======================================================================
# 1. RINGKASAN EKSEKUTIF
# ======================================================================
def ringkasan(d, info):
    t.atur_aksen("ringkasan")
    t.spanduk("Ringkasan Eksekutif", "Executive Leadership",
             "gambaran umum revenue, promo, crowd, dan waktu tunggu")
    sales, ops, wait = d["sales"], d["ops"], d["wait"]
    t.judul_filter()
    th = filter_tahun("rk_tahun", sorted(sales["arrival_year"].unique()))
    s = saring_tahun(sales, "arrival_year", th)
    o = saring_tahun(ops, "year", th)
    w = saring_tahun(wait, "year", th)
    if s.empty or o.empty:
        t.kosong()
        return

    total = s["total_revenue"].sum()
    promo = s[s["promotion"] != "Tanpa Promo"]
    pvr = promo["promo_valid_flag"].mean() * 100 if len(promo) else None
    tinjau = int((promo["promo_valid_flag"] == 0).sum())
    crowd_taman = o.groupby("park_name")["crowd_level_pct"].mean()
    mix_tiket = s["ticket_revenue"].sum() / total * 100

    with t.papan():
        t.tiket("Total Revenue", t.uang_ringkas(total), f"dari {t.angka(len(s))} booking",
                tautan="penjualan", nama_tautan="Penjualan")
        t.tiket("Revenue Mix (tiket)", t.persen(mix_tiket, 0),
                f"hotel {t.persen(s['hotel_revenue'].sum() / total * 100, 0)}, "
                f"add-on {t.persen(s['addon_revenue'].sum() / total * 100, 0)}",
                tautan="penjualan", nama_tautan="Penjualan")
        t.tiket("Promo Validity Rate", t.persen(pvr), f"{t.angka(tinjau)} booking ditinjau",
                sorot=pvr is not None and pvr < 90, tautan="promo", nama_tautan="Validitas Promo")
        t.tiket("Average Crowd Level", t.persen(o["crowd_level_pct"].mean()),
                f"terpadat {crowd_taman.idxmax()}", tautan="crowd", nama_tautan="Crowd")
        if w.empty:
            t.tiket("Average Wait Time", "-", "tidak ada data")
        else:
            lama = w.loc[w["avg_wait_minutes"].idxmax()]
            t.tiket("Average Wait Time", f"{t.angka(w['avg_wait_minutes'].mean())} menit",
                    f"wahana terlama {t.angka(lama['avg_wait_minutes'])} menit",
                    tautan="waktu-tunggu", nama_tautan="Waktu Tunggu")

    kiri, kanan = st.columns([1.55, 1], gap="medium")
    with kiri:
        with t.panel():
            judul = st.empty()
            ukuran = st.segmented_control("Tampilkan", ["Revenue", "Jumlah booking"], default="Revenue",
                                          key="rk_ukuran", label_visibility="collapsed") or "Revenue"
            bln = (s.assign(bulan=s["arrival_date"].dt.to_period("M").dt.to_timestamp())
                    .groupby("bulan").agg(revenue=("total_revenue", "sum"), booking=("booking_id", "count"))
                    .reset_index())
            if ukuran == "Revenue":
                bln["nilai"] = bln["revenue"] / 1e6
                tampil_nilai, sumbu, fmt = [t.uang(v) for v in bln["revenue"]], "Revenue (juta USD)", ",.1f"
                label_puncak = lambda r: t.uang_ringkas(r["revenue"])
                kalimat = lambda r: f"Revenue tertinggi pada {t.label_bulan(r['bulan'])} ({t.uang(r['revenue'])})"
                ket = "Total revenue menurut bulan kedatangan tamu"
            else:
                bln["nilai"] = bln["booking"]
                tampil_nilai, sumbu, fmt = [f"{t.angka(v)} booking" for v in bln["booking"]], "Jumlah booking", ",.0f"
                label_puncak = lambda r: t.angka(r["booking"])
                kalimat = lambda r: f"Booking terbanyak pada {t.label_bulan(r['bulan'])} ({t.angka(r['booking'])} booking)"
                ket = "Jumlah booking menurut bulan kedatangan tamu"
            puncak = bln.loc[bln["nilai"].idxmax()]
            with judul.container():
                t.judul_grafik(kalimat(puncak), ket)
            fig = go.Figure(go.Scatter(x=bln["bulan"], y=bln["nilai"], mode="lines+markers",
                                       line=dict(color=t.UNGU, width=2.5), marker=dict(size=6),
                                       customdata=[[t.label_bulan(b), v] for b, v in zip(bln["bulan"], tampil_nilai)],
                                       hovertemplate="%{customdata[0]}: %{customdata[1]}<extra></extra>"))
            fig.add_scatter(x=[puncak["bulan"]], y=[puncak["nilai"]], mode="markers+text",
                            marker=dict(size=12, color=t.UNGU, line=dict(color="#FFFFFF", width=2)),
                            text=[label_puncak(puncak)], textposition="top center",
                            textfont=dict(size=13, color=t.TEKS), showlegend=False, hoverinfo="skip")
            fig = t.gaya(fig, 300, x="Bulan kedatangan", y=sumbu, legenda=False)
            fig.update_yaxes(range=[0, bln["nilai"].max() * 1.18], tickformat=fmt)
            tik = bln["bulan"].iloc[::3]
            fig.update_xaxes(tickvals=tik, ticktext=[t.label_bulan(b) for b in tik])
            t.tampil(fig)
    with kanan:
        with t.panel():
            t.judul_grafik(f"{teratas(crowd_taman.round(1))} paling padat",
                           "Average Crowd Level per taman, skala tetap 0 sampai 100")
            t.daftar_batang(crowd_taman, t.persen)
            t.catatan(f"Rata-rata semua taman {t.persen(o['crowd_level_pct'].mean())}. Crowd level adalah "
                      f"indeks dari sumber, bukan jumlah pengunjung.")

    t.subjudul("Perlu ditindaklanjuti")
    item = []
    fr = s[s["promotion"] == "Florida Resident"]
    fr_bad = fr[fr["promo_valid_flag"] == 0]
    if len(fr):
        item.append(dict(
            judul="Promo Florida Resident dipakai tamu luar Florida", warna="#F58FAE", latar="#FFF6F9",
            isi=f"{t.angka(len(fr_bad))} dari {t.angka(len(fr))} booking promo ini berasal dari tamu di luar "
                f"Florida, dengan revenue {t.uang(fr_bad['total_revenue'].sum())}. Aturan pemakaian promo "
                f"perlu ditinjau.",
            siapa="Revenue Management dan Marketing", tautan="promo", nama_tautan="Validitas Promo"))
    cb = o.groupby(o["full_date"].dt.month)["crowd_level_pct"].mean()
    item.append(dict(
        judul=f"Crowd memuncak di bulan {t.BULAN[cb.idxmax() - 1]}", warna="#44BB99", latar="#F4FBF8",
        isi=f"Rata-rata crowd tertinggi pada bulan {t.BULAN[cb.idxmax() - 1]} ({t.persen(cb.max())}) dan "
            f"terendah pada bulan {t.BULAN[cb.idxmin() - 1]} ({t.persen(cb.min())}). Pola ini bisa dipakai "
            f"untuk menyusun jadwal staf.",
        siapa="Park Operations", tautan="crowd", nama_tautan="Crowd"))
    if not w.empty:
        n60 = int((w["avg_wait_minutes"] >= 60).sum())
        item.append(dict(
            judul=f"{n60} wahana antre 60 menit atau lebih", warna="#EE8866", latar="#FFF8F3",
            isi="Wahana dengan rata-rata tunggu 60 menit atau lebih jadi prioritas pengaturan antrean.",
            siapa="Guest Experience", tautan="waktu-tunggu", nama_tautan="Waktu Tunggu"))
    t.daftar_tindak(item)

    t.subjudul("Ringkasan per taman")
    with t.panel():
        t.judul_grafik("Klik satu baris untuk melihat rincian taman itu",
                       "Urut dari crowd tertinggi. Selisih hujan adalah rata-rata crowd hari hujan dikurangi "
                       "hari tidak hujan, bukan bukti sebab-akibat.")
        tabel = tabel_taman(o, w)
        pilih = st.dataframe(
            tabel.drop(columns=["crowd_angka", "Kepadatan"]), hide_index=True, width="stretch",
            on_select="rerun", selection_mode="single-row", key="rk_tabel_taman",
            column_config={
                "Taman": st.column_config.TextColumn(width=140),
                "Rata-rata crowd": st.column_config.TextColumn("Crowd", width=80),
                "Bulan terpadat": st.column_config.TextColumn("Bulan terpadat", width=120),
                "Selisih saat hujan": st.column_config.TextColumn("Selisih hujan", width=110),
                "Jam buka per hari": st.column_config.TextColumn("Jam buka", width=90),
                "Rata-rata tunggu": st.column_config.TextColumn("Tunggu", width=90),
                "Antrean rata-rata terlama": st.column_config.TextColumn("Wahana antrean terlama"),
            })
        baris = pilih.selection.rows if pilih and pilih.selection else []
        if baris:
            rincian_taman(tabel.iloc[baris[0]]["Taman"], o, w)
        else:
            t.catatan("Belum ada taman yang dipilih.")


def tabel_taman(o, w):
    """Satu baris per taman. Semua angka dihitung dari data mart."""
    crowd = o.groupby("park_name")["crowd_level_pct"].mean().sort_values(ascending=False)
    baris = []
    for taman, nilai in crowd.items():
        ot = o[o["park_name"] == taman]
        per_bln = ot.groupby(ot["full_date"].dt.to_period("M"))["crowd_level_pct"].mean()
        hujan = ot.loc[ot["is_rainy"], "crowd_level_pct"].mean() - ot.loc[~ot["is_rainy"], "crowd_level_pct"].mean()
        wt = w[w["park_name"] == taman]
        lama = "-" if wt.empty else wt.loc[wt["avg_wait_minutes"].idxmax(), "ride_name"]
        baris.append({
            "Taman": taman,
            "Rata-rata crowd": t.persen(nilai),
            "Kepadatan": round(nilai, 1),
            "crowd_angka": nilai,
            "Bulan terpadat": t.label_bulan(per_bln.idxmax().to_timestamp()),
            "Selisih saat hujan": t.poin(hujan),
            "Jam buka per hari": f"{t.angka(ot['operating_minutes_observed'].mean() / 60, 1)} jam",
            "Rata-rata tunggu": "-" if wt.empty else f"{t.angka(wt['avg_wait_minutes'].mean())} menit",
            "Antrean rata-rata terlama": lama,
        })
    return pd.DataFrame(baris)


def rincian_taman(taman, o, w):
    """Rincian satu taman yang dipilih dari tabel: crowd per bulan dan 5 wahana terlama."""
    warna = t.WARNA_TAMAN.get(taman, t.UTAMA)
    ot = o[o["park_name"] == taman]
    wt = w[w["park_name"] == taman]
    t.subjudul(f"Rincian {taman}")
    kiri, kanan = st.columns(2, gap="medium")
    with kiri:
        cb = ot.groupby(ot["full_date"].dt.to_period("M"))["crowd_level_pct"].mean()
        t.judul_grafik(f"Crowd {taman} per bulan", "Rata-rata crowd level (indeks 0 sampai 100)")
        fig = go.Figure(go.Bar(x=[t.label_bulan(p.to_timestamp()) for p in cb.index], y=cb.values,
                               marker_color=warna, hovertemplate="%{x}: %{y:.1f}%<extra></extra>"))
        fig = t.gaya(fig, 240, legenda=False)
        fig.update_yaxes(range=[0, 100], title_text="Crowd (%)")
        fig.update_xaxes(tickangle=-45)
        t.tampil(fig)
    with kanan:
        if wt.empty:
            t.judul_grafik("Tidak ada data waktu tunggu untuk taman ini")
        else:
            top = (wt.groupby("ride_name")["avg_wait_minutes"].mean().nlargest(5).sort_values())
            t.judul_grafik(f"5 wahana dengan antrean rata-rata terlama",
                           "Rata-rata waktu tunggu (menit), semua tahun pada filter")
            fig = go.Figure(go.Bar(x=top.values, y=top.index, orientation="h", marker_color=warna,
                                   text=[f"{t.angka(v)} menit" for v in top.values], textposition="outside",
                                   cliponaxis=False, hovertemplate="%{y}: %{x:.0f} menit<extra></extra>"))
            fig = t.gaya(fig, 240, legenda=False, sumbu_nilai="x")
            fig.update_xaxes(range=[0, top.max() * 1.35])
            t.tampil(fig)


# ======================================================================
# 2. PENJUALAN & REVENUE (Analisis 1 dan 2)
# ======================================================================
DIMENSI = {
    "Sales channel": "sales_channel",
    "Segmen tamu": "customer_segment",
    "Kategori resort": "resort_category",
    "Promosi": "promotion",
    "Event": "event_name",
    "Lama tiket (hari)": "ticket_days",
    "Musim": "arrival_season",
}


def penjualan(d, info):
    t.atur_aksen("penjualan")
    t.spanduk("Penjualan & Revenue", "Revenue Management & Sales, Finance, Resort",
             "Analisis 1 (tren dan komposisi revenue) dan Analisis 2 (channel, segmen, paket)")
    sales = d["sales"]
    t.judul_filter()
    th = filter_tahun("pj_tahun", sorted(sales["arrival_year"].unique()))
    ch_all = sorted(sales["sales_channel"].unique())
    rs_all = sorted(sales["resort_category"].unique())
    ch = st.sidebar.multiselect("Sales channel", ch_all, default=ch_all, key="pj_ch")
    rs = st.sidebar.multiselect("Kategori resort", rs_all, default=rs_all, key="pj_rs")
    s = saring_tahun(sales, "arrival_year", th)
    s = s[s["sales_channel"].isin(ch) & s["resort_category"].isin(rs)]
    if s.empty:
        t.kosong()
        return

    total = s["total_revenue"].sum()
    seg = s.groupby("customer_segment")["total_revenue"].mean()
    with t.papan():
        t.tiket("Total Revenue", t.uang_ringkas(total), f"dari {t.angka(len(s))} booking")
        t.tiket("Average Revenue per Booking", t.uang(total / len(s)),
                f"tertinggi segmen {seg.idxmax()} ({t.uang(seg.max())})")
        t.tiket("Revenue per Tamu", t.uang(total / s["total_guests"].sum()),
                f"rata-rata {t.angka(s['total_guests'].mean(), 1)} tamu per booking")
        t.tiket("Revenue Mix", f"{t.persen(s['ticket_revenue'].sum() / total * 100, 0)} tiket",
                f"hotel {t.persen(s['hotel_revenue'].sum() / total * 100, 0)}, "
                f"add-on {t.persen(s['addon_revenue'].sum() / total * 100, 0)}")

    with t.panel():
        atas_kiri, atas_kanan = st.columns([4, 1], vertical_alignment="top")
        with atas_kanan:
            per = st.segmented_control("Periode", ["Bulan", "Kuartal"], default="Bulan", key="pj_per",
                                       label_visibility="collapsed") or "Bulan"
        kode = "M" if per == "Bulan" else "Q"
        g = (s.assign(periode=s["arrival_date"].dt.to_period(kode))
              .groupby("periode")[["ticket_revenue", "hotel_revenue", "addon_revenue"]].sum())
        g.index = [(t.label_bulan(p.to_timestamp()) if kode == "M" else f"K{p.quarter} {p.year}")
                   for p in g.index]
        g.columns = ["Tiket", "Hotel", "Add-on"]
        jml = g.sum(axis=1)
        with atas_kiri:
            t.judul_grafik(f"Revenue tertinggi pada {jml.idxmax()} ({t.uang(jml.max())})",
                           f"Revenue per {per.lower()} kedatangan, dipecah menjadi tiket, hotel, dan add-on")
        panjang = g.reset_index(names="periode").melt("periode", var_name="komponen", value_name="revenue")
        fig = px.bar(panjang, x="periode", y="revenue", color="komponen",
                     color_discrete_map=t.WARNA_KOMPONEN,
                     category_orders={"komponen": ["Tiket", "Hotel", "Add-on"]})
        fig.update_traces(hovertemplate="%{x}<br>%{fullData.name}: $%{y:,.0f}<extra></extra>")
        t.tampil(t.gaya(fig, 340, x=f"{per} kedatangan", y="Revenue (USD)"))
        tb = g.assign(Total=jml).map(t.uang)
        t.tabel_angka(tb)

    kiri, kanan = st.columns(2, gap="medium")
    with kiri:
        with t.panel():
            tempat_judul = st.empty()
            c1, c2 = st.columns(2)
            dim = c1.selectbox("Bandingkan menurut", list(DIMENSI), key="pj_dim")
            ukuran = c2.selectbox("Ukuran", ["Total revenue", "Rata-rata per booking"], key="pj_uk")
            kol = DIMENSI[dim]
            agg = "sum" if ukuran == "Total revenue" else "mean"
            b = s.groupby(kol)["total_revenue"].agg(agg).reset_index()
            b[kol] = b[kol].astype(str)
            atas = b.loc[b["total_revenue"].idxmax()]
            if agg == "sum":
                judul = (f"{atas[kol]} menyumbang revenue terbesar "
                         f"({t.persen(atas['total_revenue'] / total * 100)} dari total)")
            else:
                judul = f"Rata-rata revenue per booking tertinggi: {atas[kol]} ({t.uang(atas['total_revenue'])})"
            with tempat_judul.container():
                t.judul_grafik(judul, f"{ukuran} menurut {dim.lower()}")
            fig = bar_urut(b, kol, "total_revenue", tinggi=340,
                           teks=[t.uang(v) for v in b.sort_values("total_revenue")["total_revenue"]])
            fig.update_xaxes(title_text=f"{ukuran} (USD)")
            t.tampil(fig)
    with kanan:
        with t.panel():
            m = s.groupby("resort_category")[["ticket_revenue", "hotel_revenue", "addon_revenue"]].sum()
            m = m.div(m.sum(axis=1), axis=0) * 100
            m.columns = ["Tiket", "Hotel", "Add-on"]
            t.judul_grafik(f"Porsi hotel paling besar pada kategori {m['Hotel'].idxmax()} "
                           f"({t.persen(m['Hotel'].max(), 0)})",
                           "Revenue Mix per kategori resort (persen dari revenue kategori itu)")
            mm = m.reset_index().melt("resort_category", var_name="komponen", value_name="persen")
            # label kecil (di bawah 8%) tidak ditulis supaya tidak bertumpuk, angkanya tetap ada di hover
            fig = px.bar(mm, x="persen", y="resort_category", color="komponen", orientation="h",
                         color_discrete_map=t.WARNA_KOMPONEN,
                         text=mm["persen"].map(lambda v: t.persen(v, 0) if v >= 8 else ""),
                         category_orders={"komponen": ["Tiket", "Hotel", "Add-on"]})
            fig.update_traces(textposition="inside", insidetextanchor="middle", textangle=0, textfont_color=t.TEKS,
                              hovertemplate="%{y} %{fullData.name}: %{x:.1f}%<extra></extra>")
            fig = t.gaya(fig, 400, x="Porsi revenue (%)", sumbu_nilai="x")
            fig.update_xaxes(range=[0, 100])
            t.tampil(fig)

    with t.panel():
        per_state = s.groupby("customer_state")["total_revenue"].sum().sort_values(ascending=False)
        t.judul_grafik(f"Tamu asal {teratas(per_state)} menghasilkan revenue terbesar",
                       f"Revenue menurut state asal tamu ({per_state.size} state)")
        warna = [t.UTAMA if v == per_state.max() else t.KONTEKS for v in per_state]
        fig = go.Figure(go.Bar(x=per_state.index, y=per_state.values, marker_color=warna,
                               text=[t.uang(v) for v in per_state.values], textposition="outside",
                               cliponaxis=False, hovertemplate="%{x}: $%{y:,.0f}<extra></extra>"))
        fig = t.gaya(fig, 300, x="State asal tamu", y="Revenue (USD)", legenda=False)
        fig.update_yaxes(range=[0, per_state.max() * 1.18])
        t.tampil(fig)
    t.catatan("Mata uang tidak tercantum di data sumber dan diasumsikan USD. "
               "Tanggal yang dipakai adalah tanggal kedatangan tamu.")


# ======================================================================
# 3. VALIDITAS PROMO (Analisis 3)
# ======================================================================
def promo(d, info):
    t.atur_aksen("promo")
    t.spanduk("Validitas Promo", "Revenue Management, Marketing & CRM",
             "Analisis 3 (berapa booking promo yang valid dan berapa yang perlu ditinjau)")
    sales = d["sales"]
    t.judul_filter()
    th = filter_tahun("pr_tahun", sorted(sales["arrival_year"].unique()))
    ch_all = sorted(sales["sales_channel"].unique())
    ch = st.sidebar.multiselect("Sales channel", ch_all, default=ch_all, key="pr_ch")
    s = saring_tahun(sales, "arrival_year", th)
    s = s[s["sales_channel"].isin(ch)]
    p = s[s["promotion"] != "Tanpa Promo"]
    if p.empty:
        t.kosong()
        return

    bad = p[p["promo_valid_flag"] == 0]
    fr = p[p["promotion"] == "Florida Resident"]
    pvr = p["promo_valid_flag"].mean() * 100
    with t.papan():
        t.tiket("Promo Validity Rate", t.persen(pvr),
                f"{t.angka(len(p) - len(bad))} dari {t.angka(len(p))} booking berpromo valid", sorot=pvr < 90)
        fr_rate = fr["promo_valid_flag"].mean() * 100 if len(fr) else None
        t.tiket("Valid khusus Florida Resident", t.persen(fr_rate),
                f"{t.angka(int(fr['promo_valid_flag'].sum()))} dari {t.angka(len(fr))} booking", sorot=True)
        t.tiket("Booking perlu ditinjau", t.angka(len(bad)), "promo tidak sesuai aturan", sorot=len(bad) > 0)
        t.tiket("Revenue booking perlu ditinjau", t.uang_ringkas(bad["total_revenue"].sum()),
                f"{t.persen(bad['total_revenue'].sum() / s['total_revenue'].sum() * 100)} dari total revenue")

    kiri, kanan = st.columns(2, gap="medium")
    with kiri:
        with t.panel():
            v = (p.assign(status=p["promo_valid_flag"].map({1: "Valid", 0: "Perlu ditinjau"}))
                  .groupby(["promotion", "status"]).size().reset_index(name="booking"))
            bad_promo = v[v["status"] == "Perlu ditinjau"]["promotion"].unique()
            judul = ("Semua booking yang perlu ditinjau berasal dari promo "
                     + ", ".join(bad_promo)) if len(bad_promo) else "Semua booking berpromo valid"
            t.judul_grafik(judul, "Jumlah booking per jenis promosi menurut status validitas")
            fig = px.bar(v, x="booking", y="promotion", color="status", orientation="h",
                         color_discrete_map={"Valid": t.UTAMA, "Perlu ditinjau": t.SOROT_ISI},
                         text=v["booking"].map(lambda x: t.angka(x) if x >= 150 else ""),
                         category_orders={"status": ["Valid", "Perlu ditinjau"]})
            fig.update_traces(hovertemplate="%{y} %{fullData.name}: %{x:,} booking<extra></extra>",
                              textposition="inside", insidetextanchor="middle", textfont_color=t.TEKS, textangle=0)
            t.tampil(t.gaya(fig, 300, x="Jumlah booking", sumbu_nilai="x"))
    with kanan:
        with t.panel():
            if bad.empty:
                t.judul_grafik("Tidak ada booking yang perlu ditinjau")
            else:
                hit = bad.groupby("customer_state").size()
                st_bad = hit.nlargest(10).reset_index(name="booking")
                t.judul_grafik(f"Pemakaian terbanyak dari luar Florida berasal dari {teratas(hit)}",
                               "Jumlah booking yang perlu ditinjau menurut state asal tamu")
                fig = bar_urut(st_bad, "customer_state", "booking",
                               teks=[t.angka(x) for x in st_bad.sort_values("booking")["booking"]], tinggi=300)
                fig.update_traces(marker_color=t.SOROT_ISI)
                fig.update_xaxes(title_text="Jumlah booking")
                t.tampil(fig)

    with t.panel():
        t.judul_grafik("Daftar booking yang perlu ditinjau",
                       "Urut dari revenue terbesar. Bisa diunduh untuk ditindaklanjuti tim terkait.")
        tabel = (bad.sort_values("total_revenue", ascending=False)
                    [["booking_id", "purchase_date", "arrival_date", "customer_state", "promotion",
                      "sales_channel", "resort_category", "total_revenue"]])
        st.dataframe(tabel, hide_index=True, width="stretch", height=280, column_config={
            "booking_id": "Booking ID",
            "purchase_date": st.column_config.DateColumn("Tanggal beli", format="DD/MM/YYYY"),
            "arrival_date": st.column_config.DateColumn("Tanggal datang", format="DD/MM/YYYY"),
            "customer_state": "State",
            "promotion": "Promo",
            "sales_channel": "Channel",
            "resort_category": "Resort",
            "total_revenue": st.column_config.NumberColumn("Revenue (USD)", format="%.2f"),
        })
        st.download_button("Unduh daftar (CSV)", tabel.to_csv(index=False).encode("utf-8"),
                           "booking_perlu_ditinjau.csv", "text/csv")
    t.catatan("Aturan validitas (T06 pada ETL): promo Florida Resident hanya valid kalau state "
               "asal tamu adalah FL. Promo lain tidak punya syarat state sehingga dianggap valid.")


# ======================================================================
# 4. CROWD & OPERASIONAL (Analisis 4)
# ======================================================================
KONDISI = [
    ("Akhir pekan", "is_weekend"),
    ("Hari libur", "is_holiday"),
    ("Hujan", "is_rainy"),
    ("Ada special event", "has_special_event"),
    ("Ada early entry", "has_early_entry"),
    ("Ada extended evening", "has_extended_evening"),
]


def crowd(d, info):
    t.atur_aksen("crowd")
    t.spanduk("Crowd & Operasional Taman", "Park Operations, Guest Experience",
             "Analisis 4 (taman mana yang paling padat dan bagaimana kondisi hari memengaruhi crowd)")
    ops = d["ops"]
    t.judul_filter()
    th = filter_tahun("cr_tahun", sorted(ops["year"].unique()))
    tm_all = sorted(ops["park_name"].unique())
    tm = st.sidebar.multiselect("Taman", tm_all, default=tm_all, key="cr_taman")
    o = saring_tahun(ops, "year", th)
    o = o[o["park_name"].isin(tm)]
    if o.empty:
        t.kosong()
        return

    hujan = o.loc[o["is_rainy"], "crowd_level_pct"].mean()
    kering = o.loc[~o["is_rainy"], "crowd_level_pct"].mean()
    jam = o["operating_minutes_observed"].mean() / 60
    n_kosong = int(o["operating_minutes_missing"].sum())
    with t.papan():
        t.tiket("Average Crowd Level", t.persen(o["crowd_level_pct"].mean()),
                f"{t.angka(len(o))} hari-taman diamati")
        t.tiket("Rainy-Day Crowd Difference", t.poin(hujan - kering),
                f"hujan {t.persen(hujan)} vs tidak hujan {t.persen(kering)}")
        t.tiket("Operating Minutes", f"{t.angka(jam, 1)} jam/hari",
                f"{t.angka(n_kosong)} hari tanpa data jam tidak dihitung")
        tgl = o.groupby(o["full_date"].dt.to_period("M"))["crowd_level_pct"].mean()
        t.tiket("Bulan terpadat", t.label_bulan(tgl.idxmax().to_timestamp()),
                f"rata-rata {t.persen(tgl.max())}")

    with t.panel():
        hm = (o.assign(bulan=o["full_date"].dt.to_period("M").dt.to_timestamp())
               .groupby(["park_name", "bulan"])["crowd_level_pct"].mean().reset_index())
        urut = o.groupby("park_name")["crowd_level_pct"].mean().sort_values().index.tolist()
        piv = hm.pivot(index="park_name", columns="bulan", values="crowd_level_pct").reindex(urut)
        t.judul_grafik(f"{urut[-1]} paling padat hampir sepanjang periode",
                       "Rata-rata crowd level per taman per bulan. Warna makin gelap berarti makin padat, angka di kotak adalah crowd level.")
        fig = go.Figure(go.Heatmap(
            z=piv.values, x=[t.label_bulan(c) for c in piv.columns], y=piv.index,
            colorscale=t.SKALA, zmin=0, zmax=100, xgap=2, ygap=2,
            colorbar=dict(title="Crowd (%)", thickness=12),
            texttemplate="%{z:.0f}", textfont=dict(size=11),
            hovertemplate="%{y}<br>%{x}: %{z:.1f}%<extra></extra>"))
        t.tampil(t.gaya(fig, 110 + 52 * len(urut), x="Bulan", legenda=False, sumbu_nilai="none"))

    kiri, kanan = st.columns(2, gap="medium")
    with kiri:
        with t.panel():
            rows = []
            for label, kol in KONDISI:
                ya, tidak = o[o[kol]], o[~o[kol]]
                if len(ya) and len(tidak):
                    rows.append({"kondisi": label, "Ya": ya["crowd_level_pct"].mean(),
                                 "Tidak": tidak["crowd_level_pct"].mean()})
            kd = pd.DataFrame(rows)
            if kd.empty:
                t.judul_grafik("Tidak ada pembanding kondisi hari untuk filter ini")
            else:
                kd["selisih"] = kd["Ya"] - kd["Tidak"]
                besar = kd.loc[kd["selisih"].abs().idxmax()]
                arah = "lebih tinggi" if besar["selisih"] > 0 else "lebih rendah"
                t.judul_grafik(f"Selisih terbesar: saat {besar['kondisi'].lower()}, crowd {arah} "
                               f"{t.angka(abs(besar['selisih']), 1)} poin",
                               "Rata-rata crowd saat kondisi terjadi (Ya) dibanding tidak terjadi (Tidak). "
                               "Ini perbandingan rata-rata, bukan bukti sebab-akibat.")
                kl = kd.melt("kondisi", ["Ya", "Tidak"], var_name="terjadi", value_name="crowd")
                fig = px.bar(kl, x="crowd", y="kondisi", color="terjadi", barmode="group", orientation="h",
                             color_discrete_map={"Ya": t.UTAMA, "Tidak": t.KONTEKS},
                         text=kl["crowd"].map(lambda v: t.persen(v)),
                             category_orders={"kondisi": kd.sort_values("selisih")["kondisi"].tolist()[::-1]})
                fig.update_traces(hovertemplate="%{y} (%{fullData.name}): %{x:.1f}%<extra></extra>",
                                  textposition="outside", cliponaxis=False, textfont_size=11)
                fig = t.gaya(fig, 400, x="Rata-rata crowd level (%)", sumbu_nilai="x")
                fig.update_xaxes(range=[0, kl["crowd"].max() * 1.22])
                t.tampil(fig)
    with kanan:
        with t.panel():
            rd = o.groupby(["park_name", "is_rainy"])["crowd_level_pct"].mean().unstack()
            rd = rd.reindex(columns=[False, True])
            rd["selisih"] = rd[True] - rd[False]
            rd = rd.dropna(subset=["selisih"]).reset_index()
            if rd.empty:
                t.judul_grafik("Tidak ada hari hujan pada filter ini")
            else:
                low = rd.loc[rd["selisih"].idxmin()]
                t.judul_grafik(f"Pada hari hujan, crowd {low['park_name']} paling jauh di bawah "
                               f"hari biasa ({t.poin(low['selisih'])})",
                               "Rainy-Day Crowd Difference per taman (crowd hujan dikurangi tidak hujan)")
                rd = rd.sort_values("selisih")
                fig = go.Figure(go.Bar(x=rd["selisih"], y=rd["park_name"], orientation="h",
                                       marker_color=[t.WARNA_TAMAN.get(k, t.UTAMA) for k in rd["park_name"]],
                                       text=[t.poin(v) for v in rd["selisih"]], textposition="outside",
                                       cliponaxis=False, textangle=0,
                                       hovertemplate="%{y}: %{x:+.1f} poin<extra></extra>"))
                fig = t.gaya(fig, 380, x="Selisih crowd (poin)", legenda=False, sumbu_nilai="x")
                batas = rd["selisih"].abs().max() * 1.45
                fig.update_xaxes(range=[min(0, rd["selisih"].min()) - batas * 0.3 if rd["selisih"].min() < 0 else 0,
                                        max(0, rd["selisih"].max()) + batas * 0.3 if rd["selisih"].max() > 0 else 0])
                t.tampil(fig)


    kiri2, kanan2 = st.columns(2, gap="medium")
    with kiri2:
        with t.panel():
            urutan_hari = ["Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu", "Minggu"]
            hr = (o.assign(hari=o["day_of_week"].map(t.HARI).fillna(o["day_of_week"]))
                   .groupby("hari")["crowd_level_pct"].mean().reindex(urutan_hari).dropna())
            t.judul_grafik(f"Crowd paling tinggi pada hari {teratas(hr.round(1))}",
                           "Rata-rata crowd level menurut hari dalam minggu")
            warna = [t.UTAMA if v == hr.max() else t.KONTEKS for v in hr.values]
            fig = go.Figure(go.Bar(x=hr.index, y=hr.values, marker_color=warna,
                                   text=[t.persen(v) for v in hr.values], textposition="outside",
                                   cliponaxis=False, hovertemplate="%{x}: %{y:.1f}%<extra></extra>"))
            fig = t.gaya(fig, 260, x="Hari", y="Rata-rata crowd (%)", legenda=False)
            fig.update_yaxes(range=[0, hr.max() * 1.2])
            t.tampil(fig)
    with kanan2:
        with t.panel():
            om = o.groupby("park_name")["operating_minutes_observed"].mean().div(60).dropna().reset_index()
            if om.empty:
                t.judul_grafik("Tidak ada data jam operasional asli untuk filter ini")
            else:
                atas = om.loc[om["operating_minutes_observed"].idxmax()]
                t.judul_grafik(f"{atas['park_name']} buka paling lama "
                               f"({t.angka(atas['operating_minutes_observed'], 1)} jam/hari)",
                               "Operating Minutes per taman, dalam jam per hari (hanya data asli)")
                fig = bar_urut(om, "park_name", "operating_minutes_observed",
                               teks=[f"{t.angka(v, 1)} jam" for v in
                                     om.sort_values("operating_minutes_observed")["operating_minutes_observed"]],
                               tinggi=260)
                fig.update_xaxes(title_text="Jam operasional per hari")
                t.tampil(fig)
    t.catatan("Crowd level adalah indeks 0 sampai 100 dari sumber, bukan jumlah pengunjung. "
               "Hari yang jam operasionalnya kosong di sumber diisi median saat ETL, tetapi tidak "
               "dihitung pada KPI Operating Minutes.")


# ======================================================================
# 5. WAKTU TUNGGU WAHANA (Analisis 5)
# ======================================================================
def waktu_tunggu(d, info):
    t.atur_aksen("tunggu")
    t.spanduk("Waktu Tunggu Wahana", "Guest Experience, Park Operations",
             "Analisis 5 (wahana dengan average dan maximum wait time tertinggi per taman dan tahun)")
    wait = d["wait"]
    t.judul_filter()
    tahun = sorted(wait["year"].unique())
    th = filter_tahun("wt_tahun", tahun, boleh_semua=False, default=str(tahun[0]))
    tm_all = sorted(wait["park_name"].unique())
    tm = st.sidebar.multiselect("Taman", tm_all, default=tm_all, key="wt_taman")
    arsip = st.sidebar.toggle("Ikutkan wahana arsip", value=True, key="wt_arsip")
    w = wait[(wait["year"] == th) & wait["park_name"].isin(tm)]
    if not arsip:
        w = w[w["ride_status"] == "Active"]
    if w.empty:
        t.kosong()
        return

    mx = w.loc[w["max_wait_minutes"].idxmax()]
    n60 = int((w["avg_wait_minutes"] >= 60).sum())
    with t.papan():
        t.tiket("Average Wait Time", f"{t.angka(w['avg_wait_minutes'].mean())} menit",
                f"rata-rata {t.angka(len(w))} wahana")
        t.tiket("Max Wait Time", f"{t.angka(mx['max_wait_minutes'])} menit",
                f"{mx['ride_name']} ({mx['park_name']})")
        t.tiket("Wahana rata-rata 60 menit atau lebih", t.angka(n60),
                "prioritas pengaturan antrean", sorot=n60 > 0)
        per_taman = w.groupby("park_name")["avg_wait_minutes"].mean()
        t.tiket("Taman dengan tunggu terlama", per_taman.idxmax(),
                f"rata-rata {t.angka(per_taman.max())} menit per wahana")

    with t.panel():
        top = w.nlargest(10, "avg_wait_minutes").sort_values("avg_wait_minutes")
        satu = top.iloc[-1]
        t.judul_grafik(f"{satu['ride_name']} punya antrean rata-rata terlama "
                       f"({t.angka(satu['avg_wait_minutes'])} menit)",
                       "10 wahana dengan rata-rata tunggu tertinggi. Warna batang menunjukkan taman, "
                       "titik menunjukkan waktu tunggu maksimum.")
        t.chip_taman(sorted(top["park_name"].unique()))
        fig = go.Figure()
        fig.add_bar(x=top["avg_wait_minutes"], y=top["ride_name"], orientation="h", name="Rata-rata",
                    marker_color=[t.WARNA_TAMAN.get(k, t.UTAMA) for k in top["park_name"]],
                    customdata=top["park_name"], showlegend=False,
                    text=[f"{t.angka(v)} menit" for v in top["avg_wait_minutes"]], textposition="inside",
                    insidetextanchor="end", textfont=dict(color=t.TEKS),
                    hovertemplate="%{y} (%{customdata})<br>rata-rata %{x} menit<extra></extra>")
        fig.add_scatter(x=top["max_wait_minutes"], y=top["ride_name"], mode="markers", name="Maksimum",
                        marker=dict(color=t.UNGU, size=11, symbol="diamond"),
                        hovertemplate="%{y}<br>maksimum %{x} menit<extra></extra>")
        fig = t.gaya(fig, 440, x="Waktu tunggu (menit)", sumbu_nilai="x")
        fig.update_layout(uniformtext_minsize=12, uniformtext_mode="show", bargap=0.25)
        t.tampil(fig)

    kiri, kanan = st.columns([1, 1.6], gap="medium")
    with kiri:
        with t.panel():
            pt = per_taman.reset_index()
            t.judul_grafik(f"Wahana di {per_taman.idxmax()} rata-rata paling lama",
                           "Rata-rata waktu tunggu semua wahana per taman")
            fig = bar_urut(pt, "park_name", "avg_wait_minutes",
                           teks=[f"{t.angka(v)} menit" for v in pt.sort_values("avg_wait_minutes")["avg_wait_minutes"]],
                           tinggi=330)
            fig.update_xaxes(title_text="Rata-rata waktu tunggu (menit)")
            t.tampil(fig)
    with kanan:
        with t.panel():
            t.judul_grafik("Semua wahana", "Klik judul kolom untuk mengurutkan")
            st.dataframe(w.sort_values("avg_wait_minutes", ascending=False)
                          [["park_name", "ride_name", "ride_status", "avg_wait_minutes", "max_wait_minutes"]],
                         hide_index=True, width="stretch", height=330, column_config={
                             "park_name": st.column_config.TextColumn("Taman", width="small"),
                             "ride_name": st.column_config.TextColumn("Wahana", width="medium"),
                             "ride_status": st.column_config.TextColumn("Status", width="small"),
                             "avg_wait_minutes": st.column_config.NumberColumn("Rata-rata (menit)", format="%d"),
                             "max_wait_minutes": st.column_config.NumberColumn("Maksimum (menit)", format="%d"),
                         })
    t.catatan("Waktu tunggu di sumber hanya tersedia satu nilai per wahana per tahun, jadi tidak bisa "
               "dilihat per hari. Data 2026 belum satu tahun penuh. Wahana arsip adalah wahana yang "
               "sudah tidak beroperasi menurut sumber.")


# ======================================================================
# 6. KAMUS KPI & DATA
# ======================================================================
KAMUS = [
    ("Total Revenue", "Jumlah seluruh revenue booking", "SUM(total_revenue)", "v_sales_revenue",
     "Ringkasan, Penjualan"),
    ("Average Revenue per Booking", "Revenue rata-rata satu booking", "SUM(total_revenue) / COUNT(booking_id)",
     "v_sales_revenue", "Penjualan"),
    ("Revenue Mix", "Porsi tiket, hotel, dan add-on terhadap total revenue",
     "SUM(komponen) / SUM(total_revenue) x 100", "v_sales_revenue", "Ringkasan, Penjualan"),
    ("Revenue per Tamu", "Revenue dibagi jumlah tamu", "SUM(total_revenue) / SUM(total_guests)",
     "v_sales_revenue", "Penjualan"),
    ("Promo Validity Rate", "Booking berpromo yang memenuhi aturan dibagi seluruh booking berpromo",
     "SUM(promo_valid_flag) / COUNT(booking berpromo) x 100", "v_sales_revenue", "Ringkasan, Promo"),
    ("Average Crowd Level", "Rata-rata indeks kepadatan harian (0 sampai 100)", "AVG(crowd_level_pct)",
     "v_park_operations", "Ringkasan, Crowd"),
    ("Rainy-Day Crowd Difference", "Selisih crowd hari hujan dan tidak hujan",
     "AVG(crowd | hujan) - AVG(crowd | tidak hujan)", "v_park_operations", "Crowd"),
    ("Operating Minutes", "Rata-rata lama taman buka per hari, tanpa data hasil imputasi",
     "AVG(operating_minutes_observed)", "v_park_operations", "Crowd"),
    ("Average Wait Time", "Rata-rata waktu tunggu tahunan wahana", "AVG(avg_wait_minutes)", "v_wait_time",
     "Ringkasan, Waktu Tunggu"),
    ("Max Wait Time", "Waktu tunggu maksimum tertinggi", "MAX(max_wait_minutes)", "v_wait_time",
     "Waktu Tunggu"),
]


def kamus(d, info):
    t.atur_aksen("kamus")
    t.spanduk("Kamus KPI & Data", "semua pengguna dashboard",
             "arti setiap angka, asal datanya, dan kapan data terakhir diperbarui")
    t.judul_filter()
    st.sidebar.markdown('<div class="tw-text-[0.86rem] tw-text-tinta-lemah">Halaman ini tidak memakai filter.</div>',
                        unsafe_allow_html=True)
    t.subjudul("Definisi KPI")
    # st.table dipakai supaya teks panjang terbungkus dan semua kolom terlihat tanpa digeser
    st.table(pd.DataFrame(KAMUS, columns=["KPI", "Arti", "Cara hitung", "Sumber (schema mart)",
                                          "Dipakai di halaman"]).set_index("KPI"))

    t.subjudul("Catatan tentang data")
    st.markdown(
        "- Data berasal dari tiga sumber: booking (5.000 baris), kalender crowd harian, dan statistik "
        "waktu tunggu tahunan. Ketiganya sudah lewat proses ETL, validasi, dan dimuat ke data warehouse.\n"
        "- Mata uang tidak tercantum di sumber dan diasumsikan USD.\n"
        "- Crowd level adalah indeks dari sumber, bukan jumlah pengunjung.\n"
        "- Nama taman memakai nama Vistaland. Nama asli di sumber tetap disimpan di kolom "
        "source_park_name untuk keperluan audit.\n"
        "- Jam operasional yang kosong di sumber diisi median saat ETL (dengan penanda), tetapi tidak "
        "dihitung pada KPI Operating Minutes.\n"
        "- Waktu tunggu hanya ada satu nilai per wahana per tahun, dan data 2026 belum satu tahun penuh."
    )

    t.subjudul("Status data")
    s, o, w = d["sales"], d["ops"], d["wait"]
    status = pd.DataFrame([
        ("Sumber data dashboard", info["keterangan"]),
        ("Data mart terakhir diperbarui", t.waktu_orlando(info.get("mart_diperbarui"))),
        ("Hasil validasi source vs mart terakhir", info.get("status_validasi") or "-"),
        ("Booking (v_sales_revenue)", f"{t.angka(len(s))} baris, kedatangan "
                                       f"{s['arrival_date'].min():%d/%m/%Y} sampai {s['arrival_date'].max():%d/%m/%Y}"),
        ("Crowd harian (v_park_operations)", f"{t.angka(len(o))} baris, "
                                             f"{o['full_date'].min():%d/%m/%Y} sampai {o['full_date'].max():%d/%m/%Y}"),
        ("Waktu tunggu (v_wait_time)", f"{t.angka(len(w))} baris, tahun "
                                       f"{', '.join(str(x) for x in sorted(w['year'].unique()))}"),
    ], columns=["Keterangan", "Nilai"])
    st.dataframe(status, hide_index=True, width="stretch")
