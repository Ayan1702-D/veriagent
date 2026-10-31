"""Run the evaluation dataset and emit machine- and human-readable reports."""

import argparse
import asyncio
import json
import os
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Literal

from eval.dataset import (
    EvalClaim,
    RecordedRun,
    RecordedSource,
    load_claims,
    load_recorded_run,
    write_recorded_run,
)
from eval.metrics import EvalReport, evaluate_runs

Mode = Literal["replay", "live", "record"]
_BACKEND_ROOT = Path(__file__).resolve().parents[1]
_HIGHER_IS_BETTER = (
    "retrieval_precision",
    "citation_validity",
    "classification_accuracy",
    "human_agreement",
    "adjacent_agreement",
)
_LOWER_IS_BETTER = ("unsupported_claim_rate",)


def _path(value: str) -> Path:
    candidate = Path(value)
    return candidate if candidate.is_absolute() else _BACKEND_ROOT / candidate


def _providers(settings: Any, *, include_corpus: bool) -> list[Any]:
    from veriagent.tools.search import (
        DuckDuckGoSearchProvider,
        OpenAlexSearchProvider,
        TavilySearchProvider,
        WikipediaSearchProvider,
    )

    providers: list[Any] = []
    if include_corpus and settings.corpus_enabled:
        from veriagent.rag import CorpusIndex, CorpusSearchProvider

        providers.append(
            CorpusSearchProvider(
                CorpusIndex(
                    persist_path=Path(settings.chroma_path),
                    collection_name=settings.corpus_collection,
                    embedding_model_name=settings.corpus_embedding_model,
                    chunk_size=settings.corpus_chunk_size,
                    chunk_overlap=settings.corpus_chunk_overlap,
                ),
                top_k=settings.corpus_top_k,
            )
        )
    providers.extend(
        [
            DuckDuckGoSearchProvider(),
            WikipediaSearchProvider(),
            OpenAlexSearchProvider(mailto=settings.openalex_mailto),
        ]
    )
    if settings.tavily_api_key:
        providers.append(TavilySearchProvider(settings.tavily_api_key))
    return providers


async def _execute_graph(
    case: EvalClaim,
    mode: Literal["live", "record"],
    cassette_dir: Path,
    *,
    include_corpus: bool,
) -> RecordedRun:
    # Keep all graph/network dependencies lazy: replay mode must not initialize LiteLLM
    # or any search client, let alone make a network request.
    from veriagent.audit.recorder import AuditRecorder
    from veriagent.config import Settings
    from veriagent.core.budget import BudgetGovernor
    from veriagent.graph import GraphState, build_verification_graph
    from veriagent.llm import CassetteCache, LLMClient, ModelRouter
    from veriagent.schemas import Claim
    from veriagent.tools.fetch import fetch_url

    settings = Settings()
    llm = LLMClient(
        ModelRouter(settings),
        cache=CassetteCache(mode=mode, cassette_dir=cassette_dir),
    )
    governor = BudgetGovernor(case.budget)
    recorder = AuditRecorder(f"eval:{case.id}")
    graph = build_verification_graph()
    state: GraphState = {
        "claim": Claim(text=case.claim),
        "subquestions": [],
        "sources": [],
        "snapshots": {},
        "evidence": [],
        "findings": [],
        "report": None,
        "loop_count": 0,
        "max_loops": case.budget.max_loops,
        "has_gaps": False,
        "budget": governor,
        "recorder": recorder,
        "llm": llm,
        "search_providers": _providers(settings, include_corpus=include_corpus),
        "fetch_fn": fetch_url,
    }
    result: Mapping[str, Any] = await graph.ainvoke(state)
    report = result.get("report")
    if report is None:
        raise RuntimeError(f"Evaluation graph produced no report for {case.id!r}")
    sources = result.get("sources", [])
    evidence = result.get("evidence", [])
    findings = result.get("findings", [])
    return RecordedRun(
        case_id=case.id,
        sources=[RecordedSource(url=source.url, domain=source.domain) for source in sources],
        evidence=evidence,
        findings=findings or report.findings,
        verdict=report.verdict,
    )


async def collect_runs(
    claims: Sequence[EvalClaim],
    mode: Mode,
    replay_dir: Path,
    cassette_dir: Path,
    *,
    include_corpus: bool = True,
) -> list[RecordedRun]:
    """Load offline results, or execute the graph sequentially for stable budgets."""
    if mode == "replay":
        return [load_recorded_run(replay_dir / f"{case.id}.json", case.id) for case in claims]

    runs: list[RecordedRun] = []
    for index, case in enumerate(claims, 1):
        print(f"[{index}/{len(claims)}] Running {case.id}: {case.claim}")
        run = await _execute_graph(case, mode, cassette_dir, include_corpus=include_corpus)
        runs.append(run)
        if mode == "record":
            write_recorded_run(replay_dir / f"{case.id}.json", run)
    return runs


def load_replay_runs(claims: Sequence[EvalClaim], replay_dir: Path) -> list[RecordedRun]:
    """Load compact artifacts without creating an event loop or runtime clients."""
    return [load_recorded_run(replay_dir / f"{case.id}.json", case.id) for case in claims]


def render_markdown(report: EvalReport) -> str:
    """Render a compact research-style evaluation report."""
    lines = [
        "# VeriAgent evaluation report",
        "",
        f"Generated: {report.generated_at.isoformat()}",
        f"Mode: `{report.mode}` · Dataset: {report.dataset_size} claims",
        "",
        "## Summary",
        "",
        "| Metric | Score |",
        "|---|---:|",
        f"| Retrieval precision | {report.retrieval_precision:.3f} |",
        f"| Citation validity | {report.citation_validity:.3f} |",
        f"| Classification accuracy | {report.classification_accuracy:.3f} |",
        f"| Unsupported-claim rate | {report.unsupported_claim_rate:.3f} |",
        f"| Human verdict agreement | {report.human_agreement:.3f} |",
        f"| Adjacent human match | {report.adjacent_agreement:.3f} |",
        "",
        "## Confusion matrix",
        "",
    ]
    labels = list(report.confusion_matrix)
    lines.extend(
        [
            "| Expected \\ Predicted | " + " | ".join(labels) + " |",
            "|---|" + "---:|" * len(labels),
        ]
    )
    for actual in labels:
        row = report.confusion_matrix[actual]
        lines.append(f"| {actual} | " + " | ".join(str(row[label]) for label in labels) + " |")

    lines.extend(
        [
            "",
            "## Cases",
            "",
            "| Case | Predicted | Expected | Retrieval | Citations | Unsupported |",
            "|---|---|---|---:|---:|---:|",
        ]
    )
    for case in report.cases:
        lines.append(
            f"| {case.case_id} | {case.predicted_verdict.value} | "
            f"{case.expected_verdict.value} | {case.retrieval_precision:.3f} | "
            f"{case.citation_validity:.3f} | {case.unsupported_claim_rate:.3f} |"
        )
    return "\n".join(lines) + "\n"


def write_reports(report: EvalReport, reports_dir: Path) -> tuple[Path, Path]:
    """Write timestamped reports plus stable latest.json/latest.md aliases."""
    reports_dir.mkdir(parents=True, exist_ok=True)
    stamp = report.generated_at.strftime("%Y%m%dT%H%M%SZ")
    json_path = reports_dir / f"eval-{stamp}.json"
    markdown_path = reports_dir / f"eval-{stamp}.md"
    json_text = report.model_dump_json(indent=2)
    markdown_text = render_markdown(report)
    json_path.write_text(json_text, encoding="utf-8")
    markdown_path.write_text(markdown_text, encoding="utf-8")
    (reports_dir / "latest.json").write_text(json_text, encoding="utf-8")
    (reports_dir / "latest.md").write_text(markdown_text, encoding="utf-8")
    return json_path, markdown_path


def write_corpus_comparison(
    without_corpus: EvalReport,
    with_corpus: EvalReport,
    reports_dir: Path,
) -> tuple[Path, Path]:
    """Write side-by-side corpus ablation metrics and deltas."""
    reports_dir.mkdir(parents=True, exist_ok=True)
    metric_names = (
        "retrieval_precision",
        "citation_validity",
        "classification_accuracy",
        "unsupported_claim_rate",
        "human_agreement",
        "adjacent_agreement",
    )
    deltas = {
        metric: getattr(with_corpus, metric) - getattr(without_corpus, metric)
        for metric in metric_names
    }
    payload = {
        "generated_at": with_corpus.generated_at.isoformat(),
        "without_corpus": without_corpus.model_dump(mode="json"),
        "with_corpus": with_corpus.model_dump(mode="json"),
        "delta_with_minus_without": deltas,
    }
    lines = [
        "# Corpus ablation comparison",
        "",
        "| Metric | Without corpus | With corpus | Delta |",
        "|---|---:|---:|---:|",
    ]
    for metric in metric_names:
        lines.append(
            f"| {metric.replace('_', ' ').title()} | "
            f"{getattr(without_corpus, metric):.3f} | "
            f"{getattr(with_corpus, metric):.3f} | {deltas[metric]:+.3f} |"
        )
    stamp = with_corpus.generated_at.strftime("%Y%m%dT%H%M%SZ")
    json_path = reports_dir / f"corpus-comparison-{stamp}.json"
    markdown_path = reports_dir / f"corpus-comparison-{stamp}.md"
    json_text = json.dumps(payload, indent=2)
    markdown_text = "\n".join(lines) + "\n"
    json_path.write_text(json_text, encoding="utf-8")
    markdown_path.write_text(markdown_text, encoding="utf-8")
    (reports_dir / "corpus-comparison-latest.json").write_text(json_text, encoding="utf-8")
    (reports_dir / "corpus-comparison-latest.md").write_text(markdown_text, encoding="utf-8")
    return json_path, markdown_path


def regression_failures(
    current: Mapping[str, Any], baseline: Mapping[str, Any], tolerance: float
) -> list[str]:
    """Return direction-aware metric regressions larger than tolerance."""
    if tolerance < 0:
        raise ValueError("regression tolerance must be non-negative")
    failures: list[str] = []
    for metric in _HIGHER_IS_BETTER:
        if metric not in baseline:
            continue
        old, new = float(baseline[metric]), float(current[metric])
        drop = old - new
        if drop > tolerance:
            failures.append(f"{metric}: {old:.3f} -> {new:.3f} (drop {drop:.3f})")
    for metric in _LOWER_IS_BETTER:
        if metric not in baseline:
            continue
        old, new = float(baseline[metric]), float(current[metric])
        increase = new - old
        if increase > tolerance:
            failures.append(f"{metric}: {old:.3f} -> {new:.3f} (increase {increase:.3f})")
    return failures


def _print_summary(report: EvalReport) -> None:
    rows = [
        ("Retrieval precision", report.retrieval_precision),
        ("Citation validity", report.citation_validity),
        ("Classification accuracy", report.classification_accuracy),
        ("Unsupported-claim rate", report.unsupported_claim_rate),
        ("Human agreement", report.human_agreement),
        ("Adjacent human match", report.adjacent_agreement),
    ]
    print("\nMetric                       Score")
    print("---------------------------  -----")
    for name, score in rows:
        print(f"{name:<27}  {score:>5.3f}")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", default="eval/dataset/claims.jsonl")
    parser.add_argument("--mode", choices=("replay", "live", "record"), default="replay")
    parser.add_argument("--replay-dir", default="eval/dataset/replays")
    parser.add_argument("--cassette-dir", default="tests/fixtures/cassettes")
    parser.add_argument("--reports-dir", default="eval/reports")
    parser.add_argument("--baseline", default="eval/reports/baseline.json")
    parser.add_argument(
        "--tolerance",
        type=float,
        default=float(os.getenv("EVAL_REGRESSION_TOLERANCE", "0.02")),
    )
    parser.add_argument("--update-baseline", action="store_true")
    parser.add_argument("--no-regression-gate", action="store_true")
    corpus_group = parser.add_mutually_exclusive_group()
    corpus_group.add_argument(
        "--compare-corpus",
        action="store_true",
        help="run an ablation and report metrics with versus without curated retrieval",
    )
    corpus_group.add_argument(
        "--without-corpus",
        action="store_true",
        help="disable the curated corpus provider for a live or record evaluation",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        claims = load_claims(_path(args.dataset))
        replay_dir = _path(args.replay_dir)
        cassette_dir = _path(args.cassette_dir)
        if args.compare_corpus:
            if args.mode == "replay":
                without_runs = load_replay_runs(claims, replay_dir / "without-corpus")
                with_runs = load_replay_runs(claims, replay_dir / "with-corpus")
            else:
                without_runs = asyncio.run(
                    collect_runs(
                        claims,
                        args.mode,
                        replay_dir / "without-corpus",
                        cassette_dir,
                        include_corpus=False,
                    )
                )
                with_runs = asyncio.run(
                    collect_runs(
                        claims,
                        args.mode,
                        replay_dir / "with-corpus",
                        cassette_dir,
                        include_corpus=True,
                    )
                )
            without_report = evaluate_runs(claims, without_runs, mode=f"{args.mode}:without-corpus")
            report = evaluate_runs(claims, with_runs, mode=f"{args.mode}:with-corpus")
            comparison_paths = write_corpus_comparison(
                without_report, report, _path(args.reports_dir)
            )
            print(f"Corpus comparison: {comparison_paths[0]} and {comparison_paths[1]}")
        elif args.mode == "replay":
            runs = load_replay_runs(claims, replay_dir)
            report = evaluate_runs(claims, runs, mode=args.mode)
        else:
            runs = asyncio.run(
                collect_runs(
                    claims,
                    args.mode,
                    replay_dir,
                    cassette_dir,
                    include_corpus=not args.without_corpus,
                )
            )
            report = evaluate_runs(
                claims,
                runs,
                mode=(f"{args.mode}:without-corpus" if args.without_corpus else args.mode),
            )
        json_path, markdown_path = write_reports(report, _path(args.reports_dir))
        _print_summary(report)
        print(f"\nReports: {json_path} and {markdown_path}")

        baseline_path = _path(args.baseline)
        if args.update_baseline:
            baseline_path.parent.mkdir(parents=True, exist_ok=True)
            baseline_path.write_text(report.model_dump_json(indent=2), encoding="utf-8")
            print(f"Baseline updated: {baseline_path}")
            return 0
        if args.no_regression_gate:
            return 0
        if not baseline_path.is_file():
            print(f"Regression gate failed: baseline not found: {baseline_path}", file=sys.stderr)
            return 2
        baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
        failures = regression_failures(report.model_dump(mode="json"), baseline, args.tolerance)
        if failures:
            print("Regression gate failed:", file=sys.stderr)
            for failure in failures:
                print(f"  - {failure}", file=sys.stderr)
            return 1
        print(f"Regression gate passed (tolerance={args.tolerance:.3f}).")
        return 0
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as exc:
        print(f"Evaluation failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
