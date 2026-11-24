FROM apache/airflow:3.3.0

# ---- pg_dump / pg_restore versi 17 (harus sama dengan server PostgreSQL 17)
# untuk backup dan uji restore. Diambil dari repository resmi PostgreSQL (PGDG).
USER root
RUN apt-get update \
 && apt-get install -y --no-install-recommends curl ca-certificates gnupg \
 && install -d /usr/share/postgresql-common/pgdg \
 && curl -fsSL https://www.postgresql.org/media/keys/ACCC4CF8.asc \
      -o /usr/share/postgresql-common/pgdg/apt.postgresql.org.asc \
 && . /etc/os-release \
 && echo "deb [signed-by=/usr/share/postgresql-common/pgdg/apt.postgresql.org.asc] https://apt.postgresql.org/pub/repos/apt ${VERSION_CODENAME}-pgdg main" \
      > /etc/apt/sources.list.d/pgdg.list \
 && apt-get update \
 && apt-get install -y --no-install-recommends postgresql-client-17 \
 && apt-get clean && rm -rf /var/lib/apt/lists/*
USER airflow

# folder untuk database internal Airflow (supaya riwayat run tidak hilang)
RUN mkdir -p /opt/airflow/state

# library yang dipakai skrip ETL (sqlalchemy dan cryptography sudah ada di image Airflow)
RUN pip install --no-cache-dir pandas==2.3.3 openpyxl==3.1.5 psycopg2-binary==2.9.13 minio==7.2.20
