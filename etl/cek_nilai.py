"""
cek_nilai.py
Skrip bantu untuk melihat nilai asli di staging sebelum menulis transform
(misalnya isi kolom Yes/No atau tipe flag). Tidak dipakai di pipeline.
"""
import pandas as pd

import config

engine = config.get_engine()


def tampil(judul, sql):
    print("\n=== " + judul + " ===")
    print(pd.read_sql(sql, engine).to_string(index=False))


tampil("ridestats: year, metric, is_archived",
       "select year, metric, is_archived, count(*) as n from stg.stg_ridestats "
       "group by 1,2,3 order by 1,2,3")

tampil("calendar: per park",
       "select park_id, park_name, count(*) as n, min(date) as awal, "
       "max(date) as akhir, "
       "sum(case when operating_minutes is null then 1 else 0 end) as menit_kosong "
       "from stg.stg_calendar group by 1,2 order by 1")

tampil("calendar: tipe data flag",
       "select is_rainy, has_special_event, is_holiday, count(*) as n "
       "from stg.stg_calendar group by 1,2,3 order by 4 desc limit 8")

for kolom in ["FirstTimeGuest", "ParkHopper", "LightningLane", "DiningPlan",
              "Promotion", "SpecialEvent", "SalesChannel", "CustomerSegment",
              "ResortCategory"]:
    tampil("booking: " + kolom,
           'select "' + kolom + '" as nilai, count(*) as n from stg.stg_booking '
           'group by 1 order by 2 desc')
