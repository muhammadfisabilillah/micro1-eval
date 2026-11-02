# AI Evaluation Framework — E-commerce Logic

Framework untuk menguji kelemahan AI (LLM) dalam menangani logika bisnis
e-commerce yang kompleks: **diskon bertingkat**, **aturan eksklusif**, **batas
minimum transaksi**, **PPN setelah diskon**, **pembulatan floor**, **cashback
kategori**, dan **batas poin** — via perturbation engine yang menghasilkan
varian isomorfik otomatis dari reference implementation.

## Struktur Project

```
micro1-eval-ecommerce/
├── data/
│   ├── eval_cases.json            # 8 kasus seed (manual, "discovery")
│   ├── cases_schema.json          # Schema terstruktur (8 template skenario)
│   └── eval_cases_generated.json  # 46 kasus hasil generator (+varian isomorfik)
├── src/
│   ├── reference.py       # Kalkulator Python murni = single source of truth
│   ├── test_reference.py  # Unit test kalkulator (mirrors 8 kasus seed)
│   ├── generator.py       # Schema -> prompt + expected (auto-verified)
│   ├── ai_client.py       # Multi-provider: OpenRouter SDK + Gemini REST
│   └── grader.py          # Grader utama (CLI rigor, arsip bukti)
├── results/               # Arsip hasil per model/kasus (bukti reproducibility)
├── .env                   # API key (di-gitignore, JANGAN di-commit)
└── README.md
```

## Menyiapkan API Key (file `.env`)

```
OPENROUTER_API_KEY=sk-or-v1-.....
GEMINI_API_KEY=AIza.....        # gratis via aistudio.google.com
# GEMINI_MODEL=gemini-3.5-flash # opsional; default sudah gemini-3.5-flash
```

Catatan:

- Key dari [openrouter.ai](https://openrouter.ai/keys) dan
  [aistudio.google.com](https://aistudio.google.com) (tanpa tanda kutip).
- File `.env` sudah masuk `.gitignore`, jadi key tidak akan ter-commit.
- Key juga bisa diberikan lewat environment variable biasa; jika tersedia,
  `os.environ` tetap yang dipakai (`.env` tidak menimpanya).

## Membangun Kasus (reference + generator)

Kalkulator SSOT dan unit-testnya:

```bash
python -m unittest discover -s src   # 12 test, semua harus OK
```

Membangkitkan kasus baru (prompt Indonesia + expected otomatis + varian
isomorfik harga x1.2/x2.0):

```bash
python src/generator.py                 # tulis data/eval_cases_generated.json (46 kasus)
python src/generator.py --preview 6     # lihat contoh tanpa menulis file
```

Kategori kasus: `ordering`, `exclusive-selection`, `boundary`, `tax-base`,
`category-binding`, `rounding`, `points-cap` — schema tinggal ditambah
paramset untuk memperluas eval tanpa menyentuh kode.

## Cara Menjalankan

Dari root project (Fase 1 — rigor & reproducibility):

```bash
# OpenRouter default
python src/grader.py

# Gemini (frontier) pada kasus generator
python src/grader.py --model gemini --runs 3 --cases data/eval_cases_generated.json --tag gemini-v1

# Open model pinned di OpenRouter
python src/grader.py --model google/gemma-2-9b-it --runs 5 --tag baseline
```

| Argumen | Default | Fungsi |
|---------|---------|--------|
| `--model` | `openrouter/free` | Model yang diuji: slug OpenRouter, atau `gemini`/`gemini-<x>` |
| `--runs` | `3` | Jumlah run per kasus (statistik pass-rate) |
| `--out` | `results` | Folder arsip hasil |
| `--tag` | (kosong) | Subfolder pelabelan eksperimen (mis. `baseline`) |
| `--cases` | `data/eval_cases.json` | Path alternatif file kasus |

Semua panggilan memakai **temperature=0** dan menanyakan reasoning dulu
lalu angka final di baris terakhir (parser hanya membaca baris berangka —
baris metadata provider seperti "User Safety: safe" difilter, dan format
ribuan Indonesia seperti `1.585.000` dinormalisasi).

Grader akan:

1. Membaca semua test case dari `data/eval_cases.json`.
2. Menjalankan tiap kasus sebanyak `--runs` kali.
3. Membandingkan jawaban dengan `expected_output` (toleransi absolut **0.01**).
4. Mengarsipkan bukti per kasus ke `results/<model>/<tag>/<CASE-ID>.json`:

```json
{
  "case_id": "TC-001",
  "model": "openrouter/free",
  "runs": [ { "run": 1, "actual": 1615000.0, "passed": false,
              "attempts": 1, "duration_s": 14.8, "raw": "Reasoning...",
              "error": "Expected: ... Actual: ..." } ],
  "passed_runs": 0,
  "pass_rate": 0.0
}
```

serta ringkasan global `results/<model>/<tag>/_summary.json` (accuracy
agregat). Contoh output konsol:

```
Model: openrouter/free | Runs/kasus: 3 | Arsip: results/openrouter__free/baseline
Passed: 19/24 (79% akurasi)
```

**Exit code**: `0` semua lolos, `1` ada kasus gagal, `2` konfigurasi rusak —
siap dipakai di CI/CD.

## Format Test Case

`data/eval_cases.json` adalah array berisi objek:

```json
{
  "id": "TC-001",
  "prompt": "Instruksi rumit untuk AI (diskon bertingkat, eksklusif, minimal transaksi).",
  "expected_output": 1585000.0,
  "rules": "Penjelasan langkah kalkulasi yang benar berdasarkan aturan bisnis."
}
```

| Key | Tipe | Desripsi |
|-----|------|----------|
| `id` | string | Identitas unik test case (mis. `TC-001`). |
| `prompt` | string | Soal kompleks yang dikirim ke AI. |
| `expected_output` | number | Jawaban yang 100% benar (int/float). |
| `rules` | string | Penjelasan aturan bisnis & cara kalkulasi yang diharapkan. |

## Mengganti Model / Provider, dan Catatan Quota

- **OpenRouter**: slug model. Banyak varian lama `:free` (llama-3, gemma-2-9b
  `:free`, mistral-7b `:free`) sudah 404 dari katalog. `openrouter/free`
  = auto-route ke model yang tersedia, tetapi jatah `free-models-per-day`
  terbatas (tanpa kredit: kuota harian kecil).
- **Gemini**: `--model gemini` memakai `GEMINI_MODEL` (default
  `gemini-3.5-flash`). Model Gemini ditutup cepat untuk pengguna baru
  (2.0/2.5-flash sudah 404 — verifikasi lewat `GET /v1beta/models`).
- Retry/backoff 429 sudah ditangani client; grader bank jeda 3 detik antar
  request (`REQUEST_DELAY`). To-go proyeksi biaya nol via Gemini + sebagian
  OpenRouter.

## Tuning

- **Toleransi error**: ubah konstanta `TOLERANCE` (default `0.01`) di `src/grader.py`.
- **Tingkat log**: ubah `level=logging.INFO` menjadi `logging.DEBUG` di `main()`
  untuk melihat log detail pemanggilan AI client.

## Dependensi

```bash
pip install openai python-dotenv
```
