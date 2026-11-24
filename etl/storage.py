"""
storage.py
Object storage (MinIO, kompatibel S3) untuk:
  - arsip file sumber asli (permanen) -> staging bisa dibangun ulang dari awal
  - salinan backup database (terpisah dari database utama, retensi 30 hari)

Pada rancangan UTS, object storage berada di cloud. Di lingkungan
pengembangan/uji, MinIO berjalan sebagai container di docker-compose.
"""
import hashlib
import os
from datetime import datetime, timedelta, timezone

RAW_BUCKET = os.getenv("MINIO_RAW_BUCKET", "vistaland-raw")
BACKUP_BUCKET = os.getenv("MINIO_BACKUP_BUCKET", "vistaland-backup")


def get_client():
    """Client MinIO, atau None kalau MinIO tidak dikonfigurasi."""
    endpoint = os.getenv("MINIO_ENDPOINT")
    user = os.getenv("MINIO_ROOT_USER")
    password = os.getenv("MINIO_ROOT_PASSWORD")
    if not (endpoint and user and password):
        return None
    from minio import Minio

    return Minio(endpoint, access_key=user, secret_key=password, secure=False)


def _ensure_bucket(client, bucket):
    if not client.bucket_exists(bucket):
        client.make_bucket(bucket)


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def archive_source_file(path, source_name):
    """Arsipkan file sumber. Nama objek memakai hash isi file, jadi file yang
    sama tidak diunggah dua kali. Return nama objek, atau None kalau MinIO
    tidak dikonfigurasi."""
    client = get_client()
    if client is None:
        return None
    _ensure_bucket(client, RAW_BUCKET)
    digest = sha256_file(path)[:16]
    obj = f"{source_name}/{digest}_{path.name}"
    try:
        client.stat_object(RAW_BUCKET, obj)
        return obj                       # sudah pernah diarsipkan
    except Exception:
        pass
    client.fput_object(RAW_BUCKET, obj, str(path))
    return obj


def upload_backup(path):
    client = get_client()
    if client is None:
        return None
    _ensure_bucket(client, BACKUP_BUCKET)
    client.fput_object(BACKUP_BUCKET, path.name, str(path))
    return f"{BACKUP_BUCKET}/{path.name}"


def delete_old_backups(days):
    """Hapus objek backup yang lebih tua dari `days` hari. Return jumlahnya."""
    client = get_client()
    if client is None or not client.bucket_exists(BACKUP_BUCKET):
        return 0
    batas = datetime.now(timezone.utc) - timedelta(days=days)
    n = 0
    for obj in client.list_objects(BACKUP_BUCKET):
        if obj.last_modified and obj.last_modified < batas:
            client.remove_object(BACKUP_BUCKET, obj.object_name)
            n += 1
    return n


def latest_backup_name():
    client = get_client()
    if client is None or not client.bucket_exists(BACKUP_BUCKET):
        return None
    objs = [o for o in client.list_objects(BACKUP_BUCKET) if o.object_name.endswith(".enc")]
    if not objs:
        return None
    return max(objs, key=lambda o: o.last_modified).object_name


def download_backup(name, dest):
    client = get_client()
    client.fget_object(BACKUP_BUCKET, name, str(dest))
    return dest
