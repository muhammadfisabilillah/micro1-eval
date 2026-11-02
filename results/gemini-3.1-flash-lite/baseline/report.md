# Laporan Evaluasi — gemini-3.1-flash-lite (tag: baseline)

_Dibangkitkan otomatis 2026-10-29T17:09:06.150265+00:00 oleh src/report_generator.py; bukti mentah: results/<model>/<tag>/<CASE>.json_

## Ringkasan Eksekutif

| Metrik | Nilai |
|---|---|
| Model | `gemini-3.1-flash-lite` |
| Total kasus | 46 |
| Total runs | 138 |
| Runs lolos | 120 |
| **Akurasi keseluruhan** | **87.0%** |
| Kasus perfect (100%) | 40 |
| Kasus bermasalah (<100%) | 6 |

## Akurasi per Kategori Kegagalan

| Kategori | Kasus | Runs | Lolos | Akurasi |
|---|---|---|---|---|
| Boundary/Shipping | 12 | 36 | 36 | 100% |
| Category-binding | 6 | 18 | 18 | 100% |
| Exclusive-selection | 6 | 18 | 18 | 100% |
| Ordering | 6 | 18 | 0 | 0% |
| Points-cap | 6 | 18 | 18 | 100% |
| Rounding | 4 | 12 | 12 | 100% |
| Tax | 6 | 18 | 18 | 100% |

## 🏆 Trophy Findings

### (a) Ordering Bug — diskon bertingkat diurutkan salah

Kasus: diskon member 15% berlaku dulu atas SUBTOTAL, lalu diskon kategori Elektronik 10% dihitung dari harga item. Model menjawab **1.615.000** padahal jawaban benar **1.585.000** (pass_rate 0%) — model menukar urutan: memotong 10% item Elektronik terlebih dahulu, baru 15% dari total baru, sehingga base-of-percentage bergeser dan hasilnya meleset 30.000.

### (b) Isomorphic Scale Bug — salah konsisten di semua skala

Kasus: parameter identik dengan varian dasar yang bisa dinilai, hanya harga dikalikan 2. Model menjawab **5.192.000** padahal benar **5.084.000** (pass_rate 0%). Yang signifikan: jawaban salah di varian 2x (5.192.000) adalah KELIPATAN EKSAK 2x dari jawaban salah varian dasar (2.596.000) — model menerapkan ATURAN YANG SALAH secara konsisten di semua skala (sistematis, bukan noise stokastik).

## Detail kasus bermasalah

- `GEN-001` [Ordering] pass_rate 0% — expected 1.585.000; contoh gagal: Expected: 1585000.00, Actual: 1615000.00, Selisih: 30000.00 (melebihi toleransi 0.01)
- `GEN-002` [Ordering] pass_rate 0% — expected 1.902.000; contoh gagal: Expected: 1902000.00, Actual: 1938000.00, Selisih: 36000.00 (melebihi toleransi 0.01)
- `GEN-003` [Ordering] pass_rate 0% — expected 3.170.000; contoh gagal: Expected: 3170000.00, Actual: 3230000.00, Selisih: 60000.00 (melebihi toleransi 0.01)
- `GEN-004` [Ordering] pass_rate 0% — expected 2.542.000; contoh gagal: Expected: 2542000.00, Actual: 2596000.00, Selisih: 54000.00 (melebihi toleransi 0.01)
- `GEN-005` [Ordering] pass_rate 0% — expected 3.050.400; contoh gagal: Expected: 3050400.00, Actual: 3115200.00, Selisih: 64800.00 (melebihi toleransi 0.01)
- `GEN-006` [Ordering] pass_rate 0% — expected 5.084.000; contoh gagal: Expected: 5084000.00, Actual: 5192000.00, Selisih: 108000.00 (melebihi toleransi 0.01)

## Replikasi

```bash
python src/grader.py --model gemini-3.1-flash-lite --runs 3 --cases data/eval_cases_generated.json --tag baseline
python src/report_generator.py --model gemini-3.1-flash-lite --tag baseline
```
