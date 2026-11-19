# WIP & Low Stock Alert Bot — versi Superset API
# alert_bot_superset.py
#
# Cara kerja (tanpa bantuan IT database):
# Bot TIDAK konek langsung ke ClickHouse / database. Bot minta data
# chart yang sudah jadi ke API Superset, pakai sesi login Google
# yang sudah ada. Superset yang menjalankan query ke ClickHouse.
#
# Endpoint yang dipakai (terverifikasi 19 Nov 2026 di
# dash.astronauts.id, Superset 4.1.2, sesi llukman hakim):
#   GET /api/v1/chart/33325
#       -> metadata chart, query_context-nya memuat filter
#          product_detail_status_name IN (Available),
#          location_name IN 19 lokasi, sku_number IN (700700, 700701),
#          metrik SUM(stock). Jadi data yang kembali SUDAH hanya
#          stok available — bad dan lost tidak masuk.
#   GET /api/v1/chart/33325/data/?force=true
#       -> baris data chart itu (38 baris: 19 lokasi x 2 SKU).
#       GET /api/v1/chart/data tanpa pk mengembalikan 405, karena
#       endpoint itu hanya menerima POST — jadi pakai endpoint
#       per-chart di atas, jangan yang tanpa pk.
#
# Autentikasi:
#   Cookie sesi browser yang sudah login Google ("session").
#   Simpan sebagai secret, JANGAN di kode, JANGAN di chat.
#   Cookie bisa kedaluwarsa (biasanya sampai 31 hari, bisa lebih
#   cepat). Kalau bot dapat HTTP 401, itu tandanya cookie habis:
#   login ulang di browser, salin cookie "session" yang baru,
#   simpan lagi sebagai secret. Bot menulis pesan jelas di log
#   saat 401, dan TIDAK mengirim alert palsu.
#
# Aturan alert dan format pesan: SAMA dengan alert_bot.py v3
# (19 Nov 2026, disamakan dengan screenshot Google Chat
# "Alert & Report" 19 Nov 2026 06:00 WIB):
# - Trigger hanya dari stok available.
# - Kategori berprioritas tunggal: Habis = 0, WIP Nasi (700701) < 10,
#   WIP lain < 3. Kategori Stok < 50 diabaikan dulu (ditampilkan 0).
# - Alert dikirim setiap kali dijalankan kalau ada item di bawah
#   threshold. Jadwal tiap 10 menit diatur di luar script
#   (GitHub Actions), jadi JANGAN jalankan loop bawaan dan cron
#   bersamaan — akan terjadi pengiriman ganda.
#
# Cara pakai:
#   pip install -r requirements.txt
#   python alert_bot_superset.py --once   # uji satu siklus
#   python alert_bot_superset.py          # loop bawaan tiap 10 menit

import os, sys, time, logging
from collections import defaultdict
from datetime import datetime
from zoneinfo import ZoneInfo

import requests
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("wip-alert-superset")

SUPERSET_BASE = os.environ.get(
    "SUPERSET_BASE_URL", "https://dash.astronauts.id").rstrip("/")
CHART_ID = int(os.environ.get("SUPERSET_CHART_ID", "33325"))
SESSION_COOKIE = os.environ.get("SUPERSET_SESSION_COOKIE", "")
WEBHOOK = os.environ["GCHAT_WEBHOOK_URL"]
INTERVAL = int(os.environ.get("CHECK_INTERVAL_MINUTES", "10"))
TZ = ZoneInfo(os.environ.get("TIMEZONE", "Asia/Jakarta"))

SKU_NASI = 700701
WIP_SKUS = {700700, 700701}


def hub_code(location_name: str) -> str:
    return location_name.split(" - ")[0].strip()


def kategorikan(sku: int, sisa: int):
    if sisa == 0:
        return "habis"
    if sku == SKU_NASI and sisa < 10:
        return "nasi"
    if sku in WIP_SKUS and sisa < 3:
        return "wip"
    return None


def _nilai_sisa(row: dict):
    # Nama kolom metrik di Superset bisa "SUM(stock)",
    # "sum__stock", atau "stock" tergantung versi. Cari yang
    # mengandung "stock" dan bukan kolom status/nama.
    for kunci in ("SUM(stock)", "sum__stock", "stock"):
        if kunci in row:
            return int(row[kunci])
    for kunci, nilai in row.items():
        if "stock" in kunci.lower():
            return int(nilai)
    raise KeyError(f"Kolom stok tidak ditemukan di baris: {row!r}")


def _baris_data(payload: dict):
    # Bentuk balasan GET /api/v1/chart/<pk>/data/:
    # {"result": [{"data": [...], "colnames": [...], ...}]}
    # Terima juga varian {"result": {"data": [...]}} dan
    # {"data": [...]} supaya tidak rapuh.
    hasil = payload.get("result", payload)
    if isinstance(hasil, list):
        if not hasil:
            return []
        hasil = hasil[0]
    if isinstance(hasil, dict):
        return hasil.get("data", [])
    return []


def ambil_alert():
    if not SESSION_COOKIE:
        raise SystemExit(
            "SUPERSET_SESSION_COOKIE kosong. Isi dulu dari cookie "
            "'session' browser Superset yang sudah login Google, "
            "sebagai secret — jangan tulis di kode atau di chat.")
    url = f"{SUPERSET_BASE}/api/v1/chart/{CHART_ID}/data/"
    r = requests.get(url, params={"force": "true"},
                     cookies={"session": SESSION_COOKIE},
                     timeout=60)
    if r.status_code == 401:
        log.error(
            "Superset menolak sesi (HTTP 401): cookie 'session' "
            "sudah kedaluwarsa. Login ulang di browser Superset "
            "pakai Google, salin cookie 'session' yang baru, dan "
            "simpan lagi sebagai secret. Bot berhenti tanpa "
            "mengirim alert.")
        raise SystemExit(2)
    r.raise_for_status()
    rows = _baris_data(r.json())
    log.info("Data chart %s: %d baris.", CHART_ID, len(rows))
    hasil = []
    for row in rows:
        sku = int(row["sku_number"])
        sisa = _nilai_sisa(row)
        kat = kategorikan(sku, sisa)
        if kat:
            hasil.append({
                "location_name": row["location_name"],
                "sku_number": sku,
                "product_name": row["product_name"],
                "sisa": sisa, "kategori": kat})
    return hasil


def format_pesan(alerts, sekarang: datetime) -> str:
    jumlah = {"habis": 0, "nasi": 0, "wip": 0}
    per_hub = defaultdict(list)
    for a in alerts:
        jumlah[a["kategori"]] += 1
        per_hub[hub_code(a["location_name"])].append(a)
    total_hub = len(per_hub)
    baris = ["WIP & LOW STOCK ALERT",
        f"Update: {sekarang:%d %b %Y, %H:%M} WIB",
        f"Total: {len(alerts)} item di {total_hub} hub",
        f"🔴 Habis: {jumlah['habis']} | "
        f"🍚 WIP Nasi <10: {jumlah['nasi']} | "
        f"🟠 WIP <3: {jumlah['wip']} | "
        f"🟡 Stok <50: 0"]
    if jumlah["nasi"] > 0:
        baris.append("⚠️ PERHATIAN: Ada WIP Nasi kritis "
            "(<10) - Alert akan terus dikirim tiap 10 menit!")
    baris.append("")
    baris.append("Per hub: " + " | ".join(
        f"{h} {len(v)}" for h, v in
        sorted(per_hub.items())))
    baris.append("")
    baris.append("------------")
    for hub, items in sorted(per_hub.items()):
        items.sort(key=lambda x: x["sisa"])
        baris.append("")
        wip_count = sum(1 for a in items
                        if a["kategori"] in ("nasi", "wip"))
        habis_count = sum(1 for a in items
                          if a["kategori"] == "habis")
        bagian = []
        if wip_count:
            bagian.append(f"{wip_count} WIP")
        if habis_count:
            bagian.append(f"{habis_count} Habis")
        baris.append(f"{hub} - {len(items)} item "
                     f"({', '.join(bagian)})")
        for a in items:
            nama = a["product_name"].replace(" - AC", "")
            emoji = {"habis": "🔴", "nasi": "🍚",
                     "wip": "🟠"}[a["kategori"]]
            teks = (f"{emoji} {nama} ({a['sku_number']}): "
                    f"sisa {a['sisa']}")
            if a["kategori"] == "nasi":
                teks += " (WIP NASI < 10)"
            elif a["kategori"] == "wip":
                teks += " (WIP < 3)"
            elif a["kategori"] == "habis":
                teks += " (HABIS)"
            baris.append(teks)
    return "\n".join(baris)


def kirim_ke_gchat(pesan: str) -> None:
    r = requests.post(WEBHOOK, json={"text": pesan}, timeout=30)
    r.raise_for_status()
    log.info("Alert terkirim ke Google Chat: HTTP %s",
             r.status_code)


def satu_siklus() -> None:
    alerts = ambil_alert()
    if not alerts:
        log.info("Tidak ada item di bawah threshold.")
        return
    pesan = format_pesan(alerts, datetime.now(TZ))
    kirim_ke_gchat(pesan)
    log.info("Siklus selesai: %d item alert.", len(alerts))


def main() -> None:
    if "--once" in sys.argv:
        satu_siklus()
        return
    while True:
        try:
            satu_siklus()
        except SystemExit:
            raise
        except Exception:
            log.exception("Siklus gagal, coba lagi nanti.")
        time.sleep(INTERVAL * 60)


if __name__ == "__main__":
    main()
