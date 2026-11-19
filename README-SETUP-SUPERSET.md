# Bot Alert Stok — Versi Superset API (Tanpa Bantuan IT Database)

Dibuat: 19 November 2026 — untuk Lukman

Paket ini adalah jalan yang dipakai bot teman Lukman: ambil data
dari Superset, bukan dari database langsung. Tidak butuh host, port,
atau akun database dari tim IT.

## Yang sudah terverifikasi 19 Nov 2026

- Superset di `dash.astronauts.id` versi **4.1.2**.
- `GET /api/v1/chart/33325` berhasil dengan sesi login Google
  Lukman, mengembalikan metadata chart "CEK STOCK - ALERT AREA
  LUKMAN". Query_context-nya memuat filter
  `product_detail_status_name IN (Available)`, 19 lokasi, SKU
  700700/700701, metrik `SUM(stock)`. Jadi data yang kembali
  sudah hanya stok available — bad dan lost tidak masuk.
- `GET /api/v1/dataset/273` berhasil: dataset virtual
  `dm_inventory.fact_product_details`, SQL-nya
  `SELECT * FROM dm_inventory.dim_product_details`, database
  "[PROD] ClickHouse astro-dashboard".
- `GET /api/v1/chart/data` (tanpa pk) mengembalikan 405, karena
  endpoint itu hanya menerima POST. Script ini memakai endpoint
  per-chart `GET /api/v1/chart/33325/data/?force=true`.
- Chart 33325 tidak dirender di tab dashboard 1401 mana pun
  (tidak ada di position_json), tapi bisa dibuka lewat Explore
  dan mengembalikan 38 baris (19 lokasi x 2 SKU).
- **Tidak ada** menu API Key / Personal Access Token di akun
  Lukman (role Gamma). Superset 4.1.2 belum punya menu itu.
  Login username/password lewat API juga tidak berlaku untuk
  akun Google OAuth. Jadi autentikasi bot memakai cookie sesi.

## Isi paket

- `alert_bot_superset.py` — script bot versi Superset API.
  Aturan alert dan format pesan sama dengan `alert_bot.py` v3.
- `requirements.txt` — hanya `requests` dan `python-dotenv`.
  Tidak ada driver database.
- `.env.example` — contoh variabel yang dibutuhkan.
- `.github/workflows/stock-alert-superset.yml` — jadwal tiap
  10 menit di GitHub Actions + tombol jalan manual.

## Setup

1. Buat repo GitHub baru, sebaiknya **publik** (menit Actions
   gratis tanpa batas; repo privat gratis ~2.000 menit/bulan
   tidak cukup untuk ~4.320 run/bulan).
2. Upload semua file paket ini ke repo, jaga struktur foldernya
   (terutama `.github/workflows/`), ke branch default.
3. Ambil cookie sesi Superset:
   - Buka `dash.astronauts.id` di browser, pastikan sudah login
     pakai Google seperti biasa.
   - Buka DevTools (F12) > Application > Cookies >
     `https://dash.astronauts.id` > cari cookie bernama
     `session`, salin nilainya.
   - **Jangan kirim nilai cookie itu lewat chat, jangan taruh
     di kode, jangan commit.** Cookie itu sama dengan login
     sebagai kamu di Superset.
4. Di repo, buka Settings → Secrets and variables → Actions →
   New repository secret, buat dua secret ini:
   - `SUPERSET_SESSION_COOKIE` — nilai cookie `session` tadi.
   - `GCHAT_WEBHOOK_URL` — URL webhook Space Google Chat
     tujuan (misal grup "Monitor WIP").
5. Uji manual: tab Actions → WIP Low Stock Alert (Superset API)
   → Run workflow. Kalau sukses dan pesan alert yang benar
   muncul di Google Chat, jadwal otomatisnya sudah aktif.
   Kalau tidak ada stok di bawah threshold, log menulis
   "Tidak ada item di bawah threshold." dan tidak ada pesan
   yang dikirim — itu normal.
6. Cocokkan hasil uji dengan chart di Explore
   (`/explore/?slice_id=33325`, 38 baris): item dan angkanya
   harus sama.

## Kalau bot berhenti (cookie kedaluwarsa)

Cookie sesi bisa kedaluwarsa (biasanya sampai 31 hari, bisa
lebih cepat). Tandanya: log workflow menulis HTTP 401 dan
pesan "cookie 'session' sudah kedaluwarsa", dan tidak ada
alert yang dikirim. Perbaikannya: login ulang di browser
Superset pakai Google, salin cookie `session` yang baru,
perbarui secret `SUPERSET_SESSION_COOKIE` di repo. Tidak
perlu ubah kode.

## Verifikasi paket ini

- 19 Nov 2026: `alert_bot_superset.py` lolos
  `python -m py_compile`.
- Uji parsing dengan data contoh bergaya Superset (BRY Nasi 3,
  TDN Nasi 4, MTG Nasi 38, SKR Chocolate Sauce 3): hanya BRY
  dan TDN yang jadi alert, format pesan sama persis dengan
  screenshot "Alert & Report" 19 Nov 2026 06:00 WIB.
- Yang BELUM bisa diuji tanpa cookie sesi asli: panggilan
  sungguhan ke `GET /api/v1/chart/33325/data/` dan pengiriman
  sungguhan ke Google Chat. Itu langkah 5 di atas.

## Jangka panjang (opsional, bukan syarat jalan)

Minta ke admin Superset (bukan ke IT database) salah satu dari:
- mengaktifkan API Key Superset, atau
- membuatkan akun service read-only ber-auth database untuk bot.

Setelah itu bot tidak lagi bergantung pada cookie browser.
Sampai saat itu, paket ini sudah bisa jalan.
