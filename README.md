# AI Evaluation Framework — E-Commerce Business Logic

A reproducible evaluation framework that probes a blind spot of modern LLMs:
**multi-step e-commerce pricing logic**. Models are asked to compute a final
amount under layered business rules — tiered discounts, exclusive promotions,
minimum-subtotal gates, VAT after discount, per-item floor rounding,
category-bound cashback, and points caps.

The framework generates isomorphic case variants (same logic, shifted prices),
grades each case multiple times at `temperature=0`, and archives every raw
response as evidence. Accuracy is reported per failure category, not just as a
single score.

## Headline result

Baseline on `gemini-3.1-flash-lite`: **87.0% accuracy** (120 / 138 runs,
46 cases x 3 runs) — with a striking, fully deterministic failure mode.

| Category | Cases | Runs | Accuracy |
|---|---:|---:|---:|
| Ordering | 6 | 18 | **0%** |
| Tax | 6 | 18 | 100% |
| Boundary/Shipping | 12 | 36 | 100% |
| Exclusive-selection | 6 | 18 | 100% |
| Category-binding | 6 | 18 | 100% |
| Points-cap | 6 | 18 | 100% |
| Rounding | 4 | 12 | 100% |

Full report with raw numbers: [`results/report.md`](results/report.md).

### Trophy findings

1. **Ordering bug (0 / 18 runs).** In the tiered-discount rule, the 15% member
   discount must apply first to the subtotal, and only then the 10% category
   discount is computed from each item's price. The model consistently swaps the
   order (category discount first, then member discount on the new total),
   shifting the percentage base. Every one of the 6 price/param variants fails
   on all 3 runs.

2. **The wrong rule is scale-invariant (systematic, not noise).** The wrong
   answer on the 2x-price variant is an **exact 2x multiple** of the wrong answer
   on the base variant (`5,192,000` vs `2,596,000`; correct answers are
   `5,084,000` and `2,542,000`). The model does not "get confused by big
   numbers" — it applies the same incorrect rule consistently at every scale.

## Why this is different from a prompt benchmark

- **A single source of truth.** All expected answers are computed by pure
  Python (`src/reference.py`), unit-tested (`src/test_reference.py`), never
  hand-written. This removes grader ambiguity.
- **Isomorphic perturbation testing.** Every template is instantiated at
  multiple price scales. Business logic is identical, so a correct model must
  scale its answer linearly. This isolates reasoning errors from arithmetic
  errors.
- **Evidence, not claims.** Every call's raw response, latency, retry count,
  verdict, expected and actual value are archived under
  `results/<model>/<tag>/<CASE>.json`. The report is generated from those files.
- **Rigor under audit.** While building this framework we found and fixed two
  bugs in the framework itself (see "Framework self-audit" below). That process
  is part of the provenance of the results.

## Repository layout

```
.
├── data/
│   ├── eval_cases.json          # 8 hand-written seed cases
│   ├── cases_schema.json        # 8 scenario templates x paramsets x price shifts
│   ├── eval_cases_generated.json# 46 canonical cases (Indonesian prompts)
│   └── eval_cases_en.json       # English mirror of the same 46 cases
├── src/
│   ├── reference.py             # Pure-Python calculator = source of truth
│   ├── test_reference.py        # 12 unit tests for the calculator
│   ├── generator.py             # Schema -> prompts + expected (+ EN mirror)
│   ├── ai_client.py             # OpenRouter + Gemini REST client, parser, retry
│   ├── grader.py                # CLI runner, archives evidence per case
│   └── report_generator.py      # Aggregates archives -> Markdown report
├── results/
│   ├── report.md                # Generated baseline report (English)
│   └── gemini-3.1-flash-lite/baseline/   # Raw per-case evidence + summary
└── .env                         # API keys (gitignored)
```

## Quick start

```bash
pip install -r requirements.txt   # or: pip install openai python-dotenv

cp .env.example .env              # then fill in your keys

# 1. Verify the source of truth
python -m unittest discover -s src

# 2. (Optional) regenerate cases
python src/generator.py           # writes data/eval_cases_generated.json
python src/generator.py --lang en # writes data/eval_cases_en.json

# 3. Run the baseline (reproducible)
python src/grader.py --model gemini-3.1-flash-lite --runs 3 \
  --cases data/eval_cases_generated.json --tag baseline

# 4. Build the report
python src/report_generator.py --model gemini-3.1-flash-lite --tag baseline \
  --out results/report.md
```

On Windows, use `py` instead of `python` if that is how Python is registered.

`.env` format:

```
OPENROUTER_API_KEY=sk-or-v1-...
GEMINI_API_KEY=AIza...
# GEMINI_MODEL=gemini-3.5-flash   # optional override for --model gemini
```

## How the pipeline works

1. `cases_schema.json` describes each scenario as structured parameters
   (items, prices, thresholds, percentages) — not as prose. Prices can be
   shifted by a multiplier (`1.0`, `1.2`, `2.0`).
2. `generator.py` calls `reference.py` to compute the expected answer for every
   parameter set and price shift, then renders the prompt and a rule
   explanation. The same numeric answers are used for the Indonesian canonical
   file and the English mirror.
3. `grader.py` sends each prompt `--runs` times at `temperature=0`, extracts the
   final number from the last numeric line (filtering provider metadata lines),
   normalizes Indonesian thousands/decimal separators, compares with an absolute
   tolerance of `0.01`, and writes evidence files.
4. `report_generator.py` aggregates the evidence into per-category accuracy and
   data-driven trophy findings.

### CLI options (grader)

| Argument | Default | Purpose |
|---|---|---|
| `--model` | `openrouter/free` | OpenRouter slug, or `gemini` / a Gemini slug |
| `--runs` | `3` | Runs per case (pass-rate statistics) |
| `--out` | `results` | Archive root |
| `--tag` | (empty) | Experiment label, stored as a subfolder |
| `--cases` | `data/eval_cases.json` | Alternative cases file |
| `--skip-existing` | off | Resume: skip cases with enough archived runs |

Exit codes: `0` = all runs passed, `1` = at least one failure, `2` = configuration
error. Suitable for CI.

### Failure categories

`ordering`, `exclusive-selection`, `boundary` (minimum subtotal / free-shipping
threshold), `tax-base` (VAT after discount), `category-binding` (category vs
product-name traps), `rounding` (floor per item), `points-cap` (cap as a
percentage of the post-discount total).

## Case format

```json
{
  "id": "GEN-001",
  "prompt": "The store applies TIERED discounts. ...",
  "expected_output": 1585000.0,
  "rules": "Computed by reference.py ... Subtotal 2,100,000; member discount 315,000; category extra 200,000.",
  "category": "ordering + category-binding",
  "scenario": "tiered_disc",
  "paramset": 0,
  "shift": 1.0
}
```

`expected_output` is always produced by `reference.py`; `rules` records the
intermediate arithmetic for inspection.

## Framework self-audit (why the numbers can be trusted)

Two bugs were found during this work by treating the framework as an object of
evaluation:

1. **Poisoned isomorphic prompts.** An earlier generator rendered unshifted
   prices in the prompt while computing `expected_output` from shifted prices.
   The model's answers looked like "copies of the small variant", which was
   actually correct behavior for the poisoned prompt. After the audit, the
   prompt renderer uses the shifted item list everywhere; the whole baseline was
   discarded and re-run from scratch. The `results/` directory contains only
   post-fix evidence.
2. **Number parser misread Indonesian decimals.** `1.500.364,80` was split into
   `1.500.364` and `,80`, yielding `8.0` and a false failure. The parser now
   understands thousands dots plus comma decimals; `GEN-023` passes 3/3. This
   is a reminder that an evaluator must be audited before it audits a model.

## Provider notes (free-tier reality)

- **OpenRouter**: `openrouter/free` auto-routes to available free models, but the
  `free-models-per-day` quota is small without credits. Several legacy `:free`
  slugs have been retired (404).
- **Gemini**: the REST API is used directly (no extra SDK). Some older models
  return 404 for new accounts, and a few frontier models have a 20-request/day
  free-tier cap. `gemini-3.1-flash-lite` was stable for this baseline; transient
  503s are handled by exponential backoff.
- The client retries 429/5xx/network errors and empty/number-less responses,
  and the grader spaces requests (`REQUEST_DELAY = 6.5s`) to respect free-tier
  rate limits.

## Adding cases

Add a template (or paramset) to `data/cases_schema.json`, then run
`python src/generator.py` and `python src/generator.py --lang en`. `reference.py`
is the only place where business logic lives; the generator must never hard-code
an expected value.

## License

For the micro1 Eval Hackathon submission. Code is provided as-is for review and
reproduction.
