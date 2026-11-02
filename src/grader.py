"""AI Evaluation Framework — Grader utama (Fase 1: rigor & reproducibility).

Membaca test case dari data/eval_cases.json, menjalankan tiap kasus N kali
terhadap model yang ditentukan lewat CLI, membandingkan jawaban dengan
expected_output (toleransi 0.01), lalu mengarsipkan bukti lengkap ke
results/<model>/*.json.

Menjalankan:
    python src/grader.py                      # default: MODEL_NAME, 3 runs
    python src/grader.py --model X --runs 3 --tag baseline
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from ai_client import DEFAULT_OPENROUTER_MODEL, get_ai_response

logger = logging.getLogger(__name__)

BASE_DIR: Path = Path(__file__).resolve().parent.parent
CASES_PATH: Path = BASE_DIR / "data" / "eval_cases.json"

# Selisih (absolut) yang masih dianggap benar.
TOLERANCE: float = 0.01
# Jeda (detik) antar request; 6.5s ≈ 9 RPM untuk menghormati limit free-tier
# gemini (10 RPM) — lebih hemat daripada siklus backoff 429 berulang.
REQUEST_DELAY: float = 6.5


@dataclass
class RunRecord:
    """Hasil satu kali run (satu panggilan model) untuk satu kasus."""
    run: int
    actual: Optional[float]
    passed: bool
    attempts: int
    duration_s: float
    raw: str
    error: Optional[str] = None


@dataclass
class CaseReport:
    """Arsip satu kasus: metadata + seluruh run + agregat."""
    case_id: str
    model: str
    prompt: str
    expected: float
    rules: str
    runs: List[RunRecord] = field(default_factory=list)
    passed_runs: int = 0
    pass_rate: float = 0.0


def load_cases(path: Path = CASES_PATH) -> List[Dict[str, Any]]:
    """Memuat daftar test case dari file JSON.

    Raises:
        FileNotFoundError / json.JSONDecodeError jika file bermasalah.
    """
    logger.info("Membaca test case dari %s", path)
    with path.open(mode="r", encoding="utf-8") as f:
        return list(json.load(f))


def build_parser() -> argparse.ArgumentParser:
    """Argumen CLI grader."""
    parser = argparse.ArgumentParser(
        description="AI Evaluation Framework - Grader e-commerce (reproducible)."
    )
    parser.add_argument("--model", default=DEFAULT_OPENROUTER_MODEL,
                        help="Slug model OpenRouter, atau 'gemini' / slug Gemini (default: %(default)s)")
    parser.add_argument("--runs", type=int, default=3,
                        help="Jumlah run per kasus (default: %(default)s)")
    parser.add_argument("--out", default="results",
                        help="Folder hasil arsip (default: %(default)s)")
    parser.add_argument("--tag", default="",
                        help="Tag run, disimpan sebagai subfolder di dalam folder model")
    parser.add_argument("--cases", default=None,
                        help="Path alternatif file eval_cases.json")
    parser.add_argument("--skip-existing", action="store_true",
                        help="Lewati kasus yang sudah terarsip dengan runs cukup (resumable)")
    return parser


def evaluate_case(case: Dict[str, Any], model: str, run: int) -> RunRecord:
    """Menjalankan satu kasus satu kali lalu membandingkan dengan expected.

    Returns:
        RunRecord lengkap (verdict, timing, raw response, jumlah attempt).
    """
    case_id = str(case.get("id", "<tanpa-id>"))
    expected = float(case["expected_output"])
    prompt = str(case["prompt"])

    ai = get_ai_response(prompt, model=model, temperature=0.0)

    if ai.error is not None or ai.number is None:
        return RunRecord(run=run, actual=ai.number, passed=False,
                         attempts=ai.attempts, duration_s=ai.duration_s,
                         raw=ai.raw, error=ai.error)

    is_correct = math.isclose(expected, ai.number, rel_tol=0.0, abs_tol=TOLERANCE)
    return RunRecord(
        run=run,
        actual=ai.number,
        passed=is_correct,
        attempts=ai.attempts,
        duration_s=ai.duration_s,
        raw=ai.raw,
        error=None if is_correct else (
            f"Expected: {expected:.2f}, Actual: {ai.number:.2f}, "
            f"Selisih: {abs(expected - ai.number):.2f} "
            f"(melebihi toleransi {TOLERANCE:.2f})"
        ),
    )


def run_grader(args: argparse.Namespace) -> int:
    """Menjalankan seluruh evaluasi + mengarsipkan hasil per kasus.

    Returns:
        0 jika semua run lolos, 1 jika ada yang gagal, 2 jika konfigurasi error.
    """
    try:
        cases = load_cases(args.cases and Path(args.cases) or CASES_PATH)
    except (OSError, json.JSONDecodeError) as exc:
        logger.critical("Gagal memuat test case: %s", exc)
        return 2

    model_slug: str = args.model.replace("/", "__")
    result_dir: Path = BASE_DIR / args.out / model_slug
    if args.tag:
        result_dir = result_dir / args.tag
    result_dir.mkdir(parents=True, exist_ok=True)

    reports: List[CaseReport] = []
    total_runs = 0
    passed_runs = 0
    first = True  # tanpa delay sebelum request pertama

    for case in cases:
        out_path = result_dir / f"{case.get('id', 'case')}.json"
        if getattr(args, "skip_existing", False) and out_path.exists():
            try:
                prior = json.loads(out_path.read_text(encoding="utf-8"))
                if len(prior.get("runs", [])) >= args.runs:
                    logger.info("SKIP %s (%d runs sudah terarsip)",
                                prior.get("case_id", out_path.stem), args.runs)
                    print(f"  [SKIP] {prior.get('case_id', out_path.stem)} "
                          f"(sudah {args.runs} run)")
                    continue
            except (json.JSONDecodeError, OSError):
                pass  # arsip rusak: evaluasi ulang
        report = CaseReport(
            case_id=str(case.get("id", "?")),
            model=args.model,
            prompt=str(case["prompt"]),
            expected=float(case["expected_output"]),
            rules=str(case.get("rules", "")),
        )
        for run in range(1, args.runs + 1):
            if not first:
                time.sleep(REQUEST_DELAY)
            first = False
            record = evaluate_case(case, args.model, run)
            report.runs.append(record)
            total_runs += 1
            passed_runs += 1 if record.passed else 0
            status = "PASS" if record.passed else "FAIL"
            detail = f"{record.actual:.2f}" if record.actual is not None else (record.error or "?")
            print(f"  [{status}] {report.case_id} run {run}/{args.runs} -> {detail} "
                  f"({record.duration_s:.1f}s, {record.attempts} attempt(s))")

        report.passed_runs = passed_runs_per_case(report.runs)
        report.pass_rate = report.passed_runs / len(report.runs) if report.runs else 0.0
        reports.append(report)

        out_path = result_dir / f"{report.case_id}.json"
        _write_json(out_path, {
            "case_id": report.case_id,
            "model": report.model,
            "prompt": report.prompt,
            "expected": report.expected,
            "rules": report.rules,
            "category": case.get("category", ""),
            "scenario": case.get("scenario", ""),
            "runs": [asdict(r) for r in report.runs],
            "passed_runs": report.passed_runs,
            "pass_rate": report.pass_rate,
        })
        logger.info("Arsip ditulis: %s", out_path)

    # Summary global: file + konsol. Jika semua kasus ter-skip (run-only
    # untuk re-summary), agregasi ulang dari arsip agar tidak accuracy 0.
    cases_map: Dict[str, Dict[str, float]] = {
        r.case_id: {"pass_rate": r.pass_rate} for r in reports
    }
    if total_runs == 0:
        total_runs = passed_runs = 0
        for path in sorted(result_dir.glob("*.json")):
            if path.name == "_summary.json":
                continue
            try:
                prior = json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            prior_runs = prior.get("runs", [])
            total_runs += len(prior_runs)
            passed_runs += sum(1 for r in prior_runs if r.get("passed"))
            cases_map[str(prior.get("case_id", path.stem))] = {
                "pass_rate": float(prior.get("pass_rate", 0.0))
            }
        if total_runs:
            print(f"  (agregasi dari arsip: {len(cases_map)} kasus)")

    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "model": args.model,
        "runs_per_case": args.runs,
        "total_runs": total_runs,
        "passed_runs": passed_runs,
        "accuracy": (passed_runs / total_runs) if total_runs else 0.0,
        "cases": cases_map,
    }
    _write_json(result_dir / "_summary.json", summary)

    print("")
    print(f"Model: {args.model} | Runs/kasus: {args.runs} | Arsip: {result_dir}")
    print(f"Passed: {passed_runs}/{total_runs} ({summary['accuracy']:.0%} akurasi)")
    for r in reports:
        if r.pass_rate < 1.0:
            fails = [f"run {x.run}: {x.error}" for x in r.runs if not x.passed]
            print(f"  - {r.case_id}: pass_rate {r.pass_rate:.0%}")
            for f_ in fails:
                print(f"    * {f_}")
    return 0 if passed_runs == total_runs else 1


def passed_runs_per_case(runs: List[RunRecord]) -> int:
    return sum(1 for r in runs if r.passed)


def _write_json(path: Path, payload: Any) -> None:
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2, default=str)


def main() -> None:
    """Entry point: parse CLI, konfigurasi logging, jalankan grader."""
    args = build_parser().parse_args()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    print(f"AI Evaluation Framework - Grader (model={args.model}, runs={args.runs})\n")
    sys.exit(run_grader(args))


if __name__ == "__main__":
    main()
