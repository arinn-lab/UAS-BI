"""
extract.py
Tahap Extract: baca file sumber apa adanya lalu simpan ke schema stg.
Belum ada pembersihan di sini (nilai sumber tidak diubah). Tiap baris ditambah
kolom source_file dan extracted_at supaya asal datanya bisa dilacak.

Mode extract mengikuti rancangan UTS:
  booking   : full load awal; selanjutnya incremental (hanya BookingID baru)
  calendar  : full load awal; selanjutnya upsert per (park_id, date)
  ridestats : full load awal; selanjutnya upsert per (year, park_id, ride_id, metric)

Sebelum dimuat, file sumber asli diarsipkan ke object storage (MinIO) supaya
staging bisa dibangun ulang dari awal kalau diperlukan.
"""
from datetime import datetime

import pandas as pd
from sqlalchemy import inspect, text

import config
import storage

logger = config.get_logger()

META_COLS = ("source_file", "extracted_at")

# nama sumber: file, jenis file, tabel staging, mode, kolom kunci
SOURCES = {
    "booking": {
        "path": config.BOOKING_FILE, "kind": "excel", "table": "stg_booking",
        "mode": "incremental", "keys": ["BookingID"],
    },
    "calendar": {
        "path": config.CALENDAR_FILE, "kind": "excel", "table": "stg_calendar",
        "mode": "upsert", "keys": ["park_id", "date"],
    },
    "ridestats": {
        "path": config.RIDESTATS_FILE, "kind": "csv", "table": "stg_ridestats",
        "mode": "upsert", "keys": ["year", "park_id", "ride_id", "metric"],
    },
}


def q(col):
    """Kutip nama kolom (nama kolom sumber memakai huruf besar)."""
    return '"' + col.replace('"', '""') + '"'


def read_source(path, kind):
    if not path.exists():
        raise FileNotFoundError(f"File sumber tidak ditemukan: {path}")
    if kind == "excel":
        return pd.read_excel(path)
    # year di ridestats berisi angka dan 'all_time', jadi dibaca sebagai teks
    return pd.read_csv(path, dtype={"year": str})


def _scalar(conn, sql, params=None):
    return conn.execute(text(sql), params or {}).scalar()


def extract_source(engine, run_id, name):
    """Extract satu sumber ke staging. Return ringkasan dict."""
    src = SOURCES[name]
    path, table, keys = src["path"], src["table"], src["keys"]
    load_table = f"{table}_load"
    started = datetime.now()
    step = f"extract_{name}"

    try:
        df = read_source(path, src["kind"])
        rows_in = len(df)
        data_cols = [c for c in df.columns if c not in META_COLS]

        # arsip file asli ke object storage (gagal arsip tidak menghentikan ETL)
        try:
            arsip = storage.archive_source_file(path, name)
            info_arsip = f"arsip={arsip}" if arsip else "arsip=MinIO tidak dikonfigurasi"
        except Exception as exc:              # noqa: BLE001
            info_arsip = f"arsip GAGAL: {exc}"
            logger.warning("%s | arsip ke object storage gagal: %s", step, exc)

        df["source_file"] = path.name
        df["extracted_at"] = started
        cols = data_cols + list(META_COLS)
        col_list = ", ".join(q(c) for c in cols)
        key_list = ", ".join(q(k) for k in keys)
        join_keys = " AND ".join(f"s.{q(k)} = l.{q(k)}" for k in keys)

        # 1. tulis isi file ke tabel bantu stg.<table>_load
        df.to_sql(load_table, engine, schema="stg", if_exists="replace",
                  index=False, chunksize=1000)

        first_load = not inspect(engine).has_table(table, schema="stg")

        with engine.begin() as conn:
            if first_load:
                # full load awal: struktur staging mengikuti file sumber
                conn.execute(text(
                    f"CREATE TABLE stg.{table} AS "
                    f"SELECT {col_list} FROM stg.{load_table} WITH NO DATA"))
                if src["mode"] == "upsert":
                    conn.execute(text(
                        f"CREATE UNIQUE INDEX ux_{table}_key ON stg.{table} ({key_list})"))
                else:
                    conn.execute(text(
                        f"CREATE INDEX ix_{table}_key ON stg.{table} ({key_list})"))

            # duplikat kunci di dalam file sumber (dicatat untuk Data Steward)
            dup_in_file = _scalar(conn, (
                f"SELECT COUNT(*) - COUNT(DISTINCT ({key_list})) "
                f"FROM stg.{load_table}"))

            new_rows = _scalar(conn, (
                f"SELECT COUNT(*) FROM (SELECT DISTINCT {key_list} "
                f"FROM stg.{load_table}) l WHERE NOT EXISTS "
                f"(SELECT 1 FROM stg.{table} s WHERE {join_keys})"))

            if src["mode"] == "incremental":
                # hanya baris dengan BookingID yang belum ada di staging
                changed = 0
                conn.execute(text(
                    f"INSERT INTO stg.{table} ({col_list}) "
                    f"SELECT {col_list} FROM stg.{load_table} l "
                    f"WHERE NOT EXISTS (SELECT 1 FROM stg.{table} s WHERE {join_keys})"))
            else:
                value_cols = [c for c in data_cols if c not in keys]
                cmp_s = ", ".join(f"s.{q(c)}" for c in value_cols)
                cmp_l = ", ".join(f"l.{q(c)}" for c in value_cols)
                changed = _scalar(conn, (
                    f"SELECT COUNT(*) FROM stg.{load_table} l "
                    f"JOIN stg.{table} s ON {join_keys} "
                    f"WHERE ROW({cmp_s}) IS DISTINCT FROM ROW({cmp_l})"))
                set_list = ", ".join(f"{q(c)} = EXCLUDED.{q(c)}"
                                     for c in value_cols + list(META_COLS))
                conn.execute(text(
                    f"INSERT INTO stg.{table} ({col_list}) "
                    f"SELECT DISTINCT ON ({key_list}) {col_list} "
                    f"FROM stg.{load_table} ORDER BY {key_list} "
                    f"ON CONFLICT ({key_list}) DO UPDATE SET {set_list}"))

            # semua kunci di file harus ada di staging
            missing = _scalar(conn, (
                f"SELECT COUNT(*) FROM (SELECT DISTINCT {key_list} "
                f"FROM stg.{load_table}) l WHERE NOT EXISTS "
                f"(SELECT 1 FROM stg.{table} s WHERE {join_keys})"))
            total_stg = _scalar(conn, f"SELECT COUNT(*) FROM stg.{table}")

            config.write_dq(conn, run_id, "duplikat kunci di file sumber",
                            f"stg.{table}", rows_in, dup_in_file,
                            f"{dup_in_file} baris duplikat berdasarkan {keys}")
            conn.execute(text(f"DROP TABLE stg.{load_table}"))

        if missing:
            raise ValueError(f"{missing} kunci dari file tidak masuk ke stg.{table}")

        mode = "full load awal" if first_load else src["mode"]
        pesan = (f"{path.name} -> stg.{table} | mode={mode} | baru={new_rows} "
                 f"berubah={changed} total_staging={total_stg} | {info_arsip}")
        logger.info("%s | in=%d | %s | OK", step, rows_in, pesan)
        config.write_audit(engine, run_id, step, path.name, rows_in, total_stg,
                           0, "SUCCESS", pesan, started)
        return {"rows_in": rows_in, "baru": new_rows, "berubah": changed,
                "total_staging": total_stg}

    except Exception as exc:
        logger.error("%s | GAGAL | %s", step, exc)
        config.write_audit(engine, run_id, step, path.name,
                           None, None, None, "FAILED", str(exc)[:1500], started)
        raise


def extract_to_staging(engine, run_id):
    """Extract ketiga sumber (dipakai run manual)."""
    return {name: extract_source(engine, run_id, name) for name in SOURCES}


if __name__ == "__main__":
    import uuid

    hasil = extract_to_staging(config.get_engine(), str(uuid.uuid4()))
    logger.info("Extract selesai: %s", hasil)
