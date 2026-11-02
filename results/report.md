# Evaluation Report — gemini-3.1-flash-lite (tag: baseline)

_Generated 2026-11-02T15:29:01.411535+00:00 by src/report_generator.py; raw evidence: results/<model>/<tag>/<CASE>.json_

## Executive Summary

| Metric | Value |
|---|---|
| Model | `gemini-3.1-flash-lite` |
| Total cases | 46 |
| Total runs | 138 |
| Passing runs | 120 |
| **Overall accuracy** | **87.0%** |
| Perfect cases (100%) | 40 |
| Failing cases (<100%) | 6 |

## Accuracy by Failure Category

| Category | Cases | Runs | Passed | Accuracy |
|---|---|---|---|---|
| Boundary/Shipping | 12 | 36 | 36 | 100% |
| Category-binding | 6 | 18 | 18 | 100% |
| Exclusive-selection | 6 | 18 | 18 | 100% |
| Ordering | 6 | 18 | 0 | 0% |
| Points-cap | 6 | 18 | 18 | 100% |
| Rounding | 4 | 12 | 12 | 100% |
| Tax | 6 | 18 | 18 | 100% |

## 🏆 Trophy Findings

### (a) Ordering Bug — tiered discounts applied in the wrong order

Case: the 15% member discount applies first to the SUBTOTAL, then the 10% Electronics category discount is computed from each item's price. The model answers **1,615,000** while the correct answer is **1,585,000** (pass rate 0%) — it swaps the order: it takes 10% off the Electronics items first and then 15% off the new total, shifting the percentage base and missing by 30,000.

### (b) Isomorphic Scale Bug — consistently wrong at every scale

Case: identical parameters to the base variant, with prices multiplied by 2. The model answers **5,192,000** while the correct answer is **5,084,000** (pass rate 0%). The key signal: the wrong answer on the 2x variant (5,192,000) is an EXACT 2x multiple of the wrong answer on the base variant (2,596,000) — the model applies the SAME wrong rule consistently across price scales (systematic, not stochastic noise).

## Failing case details

- `GEN-001` [Ordering] pass rate 0% — expected 1,585,000; got 1,615,000 (delta 30,000; tolerance 0.01)
- `GEN-002` [Ordering] pass rate 0% — expected 1,902,000; got 1,938,000 (delta 36,000; tolerance 0.01)
- `GEN-003` [Ordering] pass rate 0% — expected 3,170,000; got 3,230,000 (delta 60,000; tolerance 0.01)
- `GEN-004` [Ordering] pass rate 0% — expected 2,542,000; got 2,596,000 (delta 54,000; tolerance 0.01)
- `GEN-005` [Ordering] pass rate 0% — expected 3,050,400; got 3,115,200 (delta 64,800; tolerance 0.01)
- `GEN-006` [Ordering] pass rate 0% — expected 5,084,000; got 5,192,000 (delta 108,000; tolerance 0.01)

## Reproduction

```bash
python src/grader.py --model gemini-3.1-flash-lite --runs 3 --cases data/eval_cases_generated.json --tag baseline
python src/report_generator.py --model gemini-3.1-flash-lite --tag baseline
```
