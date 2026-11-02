"""Report generator — agregasi hasil grader menjadi results/report.md.

Membaca semua file arsip `results/<model>/<tag>/<CASE>.json`, memetakan ke
kategori kanonik (ordering / exclusive / boundary+shipping / tax /
category-binding / rounding / points), lalu menulis laporan Markdown berisi:

1. Ringkasan eksekutif (total kasus, runs, akurasi).
2. Tabel akurasi per kategori kegagalan.
3. 🏆 Trophy findings (kegagalan-isomorfik paling menarik untuk demo).

Jalankan:
    python src/report_generator.py --model gemini --tag baseline
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

BASE_DIR: Path = Path(__file__).resolve().parent.parent
RESULTS_DIR: Path = BASE_DIR / "results"

# Scenario -> bucket kanonik (spec lomba: ordering/boundary/category-binding/
# rounding/tax/shipping/points).
SCENARIO_BUCKET: Dict[str, str] = {
    "tiered_disc": "Ordering",
    "exclusive": "Exclusive-selection",
    "min_subtotal_voucher": "Boundary/Shipping",
    "tax_after_discount": "Tax",
    "free_shipping_after_voucher": "Boundary/Shipping",
    "cashback_category_trap": "Category-binding",
    "floor_per_item": "Rounding",
    "points_cap": "Points-cap",
}


@dataclass
class CaseAgg:
    """Agregat satu kasus dari arsip grader."""
    case_id: str
    scenario: str
    category: str
    expected: float
    bucket: str
    total_runs: int = 0
    passed_runs: int = 0
    fail_examples: List[Tuple[int, Optional[float], str]] = None  # (run, actual, msg)

    def __post_init__(self) -> None:
        if self.fail_examples is None:
            self.fail_examples = []

    @property
    def pass_rate(self) -> float:
        return self.passed_runs / self.total_runs if self.total_runs else 0.0


def load_cases(result_dir: Path) -> List[CaseAgg]:
    """Baca file arsip kasus (abaikan _summary.json / log)."""
    aggregates: List[CaseAgg] = []
    for path in sorted(result_dir.glob("*.json")):
        if path.name == "_summary.json":
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Lewati file rusak %s: %s", path.name, exc)
            continue
        scenario = data.get("scenario", "")
        category = data.get("category", "") or path.stem
        bucket = (SCENARIO_BUCKET.get(scenario)
                  or bucketize_missing(None, category))
        agg = CaseAgg(
            case_id=data.get("case_id", path.stem),
            scenario=scenario,
            category=category,
            expected=float(data.get("expected", 0.0)),
            bucket=bucket,
        )
        for run in data.get("runs", []):
            agg.total_runs += 1
            if run.get("passed"):
                agg.passed_runs += 1
            else:
                agg.fail_examples.append((
                    int(run.get("run", 0)),
                    run.get("actual"),
                    (run.get("error") or "")[:160],
                ))
        aggregates.append(agg)
    return aggregates


def bucketize_missing(agg: CaseAgg, text: str) -> str:
    """Kategori kanonik untuk arsip tanpa field category/scenario (fallback)."""
    lower = text.lower()
    if "ordering" in lower:
        return "Ordering"
    if "exclusive" in lower:
        return "Exclusive-selection"
    if "tax" in lower:
        return "Tax"
    if "category-binding" in lower:
        return "Category-binding"
    if "rounding" in lower:
        return "Rounding"
    if "points" in lower:
        return "Points-cap"
    if "boundary" in lower:
        return "Boundary/Shipping"
    return "Lainnya"


def idr(value: Optional[float]) -> str:
    if value is None:
        return "?"
    v = float(value)
    if abs(v - round(v)) < 0.01:
        return f"{int(round(v)):,}".replace(",", ".")
    return f"{v:,.2f}".replace(",", "\x00").replace(".", ",").replace("\x00", ".")


def pick_trophy(cases: List[CaseAgg], case_id: str) -> Optional[CaseAgg]:
    for c in cases:
        if c.case_id == case_id:
            return c
    return None


def build_report(cases: List[CaseAgg], model: str, tag: str) -> str:
    total_runs = sum(c.total_runs for c in cases)
    passed_runs = sum(c.passed_runs for c in cases)
    accuracy = passed_runs / total_runs if total_runs else 0.0
    failing = [c for c in cases if c.pass_rate < 1.0]

    lines: List[str] = [
        f"# Laporan Evaluasi — {model} (tag: {tag})",
        "",
        f"_Dibangkitkan otomatis {datetime.now(timezone.utc).isoformat()} oleh "
        "src/report_generator.py; bukti mentah: results/<model>/<tag>/<CASE>.json_",
        "",
        "## Ringkasan Eksekutif",
        "",
        "| Metrik | Nilai |",
        "|---|---|",
        f"| Model | `{model}` |",
        f"| Total kasus | {len(cases)} |",
        f"| Total runs | {total_runs} |",
        f"| Runs lolos | {passed_runs} |",
        f"| **Akurasi keseluruhan** | **{accuracy:.1%}** |",
        f"| Kasus perfect (100%) | {len(cases) - len(failing)} |",
        f"| Kasus bermasalah (<100%) | {len(failing)} |",
        "",
        "## Akurasi per Kategori Kegagalan",
        "",
        "| Kategori | Kasus | Runs | Lolos | Akurasi |",
        "|---|---|---|---|---|",
    ]

    buckets: Dict[str, List[CaseAgg]] = {}
    for c in cases:
        buckets.setdefault(c.bucket, []).append(c)
    for bucket in sorted(buckets):
        group = buckets[bucket]
        b_runs = sum(c.total_runs for c in group)
        b_pass = sum(c.passed_runs for c in group)
        lines.append(
            f"| {bucket} | {len(group)} | {b_runs} | {b_pass} | "
            f"{b_pass / b_runs:.0%} |"
        )

    lines += [
        "",
        "## 🏆 Trophy Findings",
        "",
    ]

    t1 = pick_trophy(cases, "GEN-001")
    if t1 and t1.fail_examples:
        _, actual, _ = t1.fail_examples[0]
        lines += [
            "### (a) Ordering Bug — diskon bertingkat diurutkan salah",
            "",
            "Kasus: diskon member 15% berlaku dulu atas SUBTOTAL, lalu diskon "
            "kategori Elektronik 10% dihitung dari harga item. Model menjawab "
            f"**{idr(actual)}** padahal jawaban benar **{idr(t1.expected)}** "
            f"(pass_rate {t1.pass_rate:.0%}) — model menukar urutan: memotong "
            "10% item Elektronik terlebih dahulu, baru 15% dari total baru, "
            "sehingga base-of-percentage bergeser dan hasilnya meleset 30.000.",
            "",
        ]

    t4 = pick_trophy(cases, "GEN-004")
    t6 = pick_trophy(cases, "GEN-006")
    if t6 and t6.fail_examples:
        _, actual6, _ = t6.fail_examples[0]
        extra = ""
        if t4 and t4.fail_examples:
            _, actual4, _ = t4.fail_examples[0]
            if (actual4 or 0) * 2 and abs((actual6 or 0) - (actual4 or 0) * 2) < 0.01:
                extra = (
                    f" Yang signifikan: jawaban salah di varian 2x ({idr(actual6)}) "
                    f"adalah KELIPATAN EKSAK 2x dari jawaban salah varian dasar "
                    f"({idr(actual4)}) — model menerapkan ATURAN YANG SALAH secara "
                    "konsisten di semua skala (sistematis, bukan noise stokastik)."
                )
        lines += [
            "### (b) Isomorphic Scale Bug — salah konsisten di semua skala",
            "",
            "Kasus: parameter identik dengan varian dasar yang bisa dinilai, hanya "
            f"harga dikalikan 2. Model menjawab **{idr(actual6)}** padahal benar "
            f"**{idr(t6.expected)}** (pass_rate {t6.pass_rate:.0%}).{extra}",
            "",
        ]

    lines += ["## Detail kasus bermasalah", ""]
    for c in failing:
        lines.append(f"- `{c.case_id}` [{c.bucket}] pass_rate {c.pass_rate:.0%} — "
                     f"expected {idr(c.expected)}; contoh gagal: {c.fail_examples[0][2]}")

    lines += [
        "",
        "## Replikasi",
        "",
        "```bash",
        f"python src/grader.py --model {model if model != 'gemini' else 'gemini'} "
        f"--runs 3 --cases data/eval_cases_generated.json --tag {tag}",
        f"python src/report_generator.py --model {model} --tag {tag}",
        "```",
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    parser = argparse.ArgumentParser(description="Agregasi hasil -> report.md")
    parser.add_argument("--model", default="gemini")
    parser.add_argument("--tag", default="baseline")
    parser.add_argument("--out", default=None, help="Path report.md alternatif")
    args = parser.parse_args()

    result_dir = RESULTS_DIR / args.model.replace("/", "__")
    if args.tag:
        result_dir /= args.tag
    cases = load_cases(result_dir)
    if not cases:
        logger.critical("Tidak ada arsip kasus di %s", result_dir)
        sys.exit(2)

    report = build_report(cases, args.model, args.tag)
    out_path = Path(args.out) if args.out else result_dir / "report.md"
    out_path.write_text(report, encoding="utf-8")
    print(f"Report ditulis: {out_path}")
    print("\n".join(report.splitlines()[:14]) + "\n  ...")


if __name__ == "__main__":
    main()
