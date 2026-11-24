"""
notify.py
Pengiriman email notifikasi sesuai tabel Error Handling di UTS:
  - file sumber/proses gagal      -> Data Engineer
  - kegagalan database            -> DBA
  - ambang kualitas terlampaui    -> email darurat (Data Engineer + Data Steward)
  - ringkasan harian baris ditolak -> Data Steward
  - data tidak siap sebelum 06:00 -> Data Engineer

Di lingkungan pengembangan/uji email dikirim ke Mailpit (container penangkap
email, UI di http://localhost:8025), jadi tidak ada email yang keluar ke
internet. Untuk produksi cukup ganti SMTP_HOST/SMTP_PORT/SMTP_USER/SMTP_PASSWORD.
"""
import os
import smtplib
from email.message import EmailMessage

SMTP_HOST = os.getenv("SMTP_HOST", "localhost")
SMTP_PORT = int(os.getenv("SMTP_PORT", "1025"))
SMTP_USER = os.getenv("SMTP_USER") or None
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD") or None
SMTP_FROM = os.getenv("SMTP_FROM", "airflow@vistaland.local")

PENERIMA = {
    "engineer": os.getenv("EMAIL_DATA_ENGINEER", "data.engineer@vistaland.local"),
    "dba": os.getenv("EMAIL_DBA", "dba@vistaland.local"),
    "steward": os.getenv("EMAIL_DATA_STEWARD", "data.steward@vistaland.local"),
}


def send_email(subject, body, to_roles):
    """Kirim email ke satu atau beberapa peran (engineer/dba/steward).
    Return True kalau terkirim. Kegagalan kirim email tidak menghentikan
    pipeline; dicatat oleh pemanggil."""
    to = sorted({PENERIMA[r] for r in to_roles})
    msg = EmailMessage()
    msg["Subject"] = f"[Vistaland DWH] {subject}"
    msg["From"] = SMTP_FROM
    msg["To"] = ", ".join(to)
    msg.set_content(body)
    with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=15) as s:
        if SMTP_USER:
            s.starttls()
            s.login(SMTP_USER, SMTP_PASSWORD)
        s.send_message(msg)
    return True
