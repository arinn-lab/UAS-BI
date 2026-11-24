"""
uji_ambang.py
Uji aturan kualitas UTS: "baris ditolak > 1% -> load fakta dihentikan,
data lama tetap dipakai, email darurat".

    python etl/uji_ambang.py buat       siapkan file booking rusak untuk uji
    python etl/uji_ambang.py pulihkan   kembalikan file asli + bersihkan staging

'buat' menyalin file booking asli ke data/raw/_cadangan/, lalu menambahkan
60 booking baru (TST001-TST060) yang ArrivalDate-nya lebih awal dari
PurchaseDate. 60 dari 5.060 baris = 1,19%, di atas ambang 1%.
Karena extract booking incremental, hanya 60 baris baru ini yang masuk staging.

Jalankan di container Airflow (pandas & openpyxl sudah terpasang):
    docker compose exec airflow python /opt/airflow/project/etl/uji_ambang.py buat
"""
import shutil
import sys

import pandas as pd
from sqlalchemy import text

import config

CADANGAN = config.RAW_DIR / "_cadangan" / config.BOOKING_FILE.name
JUMLAH = 60


def buat():
    if CADANGAN.exists():
        print(f"Cadangan sudah ada ({CADANGAN}). Jalankan 'pulihkan' dulu.")
        return 1
    CADANGAN.parent.mkdir(exist_ok=True)
    shutil.copyfile(config.BOOKING_FILE, CADANGAN)

    df = pd.read_excel(config.BOOKING_FILE)
    rusak = df.head(JUMLAH).copy()
    rusak["BookingID"] = [f"TST{i:03d}" for i in range(1, JUMLAH + 1)]
    pdate = pd.to_datetime(rusak["PurchaseDate"])
    rusak["ArrivalDate"] = pdate - pd.to_timedelta(5, unit="D")      # melanggar aturan
    pd.concat([df, rusak], ignore_index=True).to_excel(config.BOOKING_FILE, index=False)

    print(f"OK: {JUMLAH} baris rusak ditambahkan ke {config.BOOKING_FILE.name} "
          f"({JUMLAH}/{len(df) + JUMLAH} = {JUMLAH / (len(df) + JUMLAH):.2%}).")
    print("Sekarang trigger DAG vistaland_etl di Airflow.")
    return 0


def pulihkan():
    if CADANGAN.exists():
        # copyfile (bukan copy2): folder Windows yang di-mount ke container
        # tidak mengizinkan perubahan waktu file
        shutil.copyfile(CADANGAN, config.BOOKING_FILE)
        CADANGAN.unlink()
        try:
            CADANGAN.parent.rmdir()
        except OSError:
            pass
        print("File booking asli dikembalikan.")
    else:
        print("Tidak ada cadangan; file booking dianggap sudah asli.")

    with config.get_engine().begin() as conn:
        n = conn.execute(text(
            "DELETE FROM stg.stg_booking WHERE \"BookingID\" LIKE 'TST%'")).rowcount
        conn.execute(text(
            "DELETE FROM stg.stg_rejected WHERE source_name = 'booking' "
            "AND record_key LIKE 'TST%'"))
    print(f"{n} baris uji dihapus dari stg.stg_booking.")
    print("Sekarang trigger DAG vistaland_etl lagi sampai semua hijau.")
    return 0


if __name__ == "__main__":
    perintah = sys.argv[1] if len(sys.argv) > 1 else ""
    if perintah == "buat":
        sys.exit(buat())
    if perintah == "pulihkan":
        sys.exit(pulihkan())
    print("Pakai: python etl/uji_ambang.py buat | pulihkan")
    sys.exit(1)
