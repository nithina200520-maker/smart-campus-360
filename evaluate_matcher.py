"""
PHASE 5: LOST & FOUND MATCHER EVALUATION - command line runner.

Evaluation procedure (see evaluation/README.md for the full protocol):
  1. Place labeled photographs in the dataset folders:
         evaluation/lost_found_dataset/gallery/<label>/*.jpg
         evaluation/lost_found_dataset/queries/<label>/*.jpg
     (optionally describe each photo's metadata in metadata.csv).
  2. Run:  python evaluate_matcher.py                 # real dataset
             python evaluate_matcher.py --generate-synthetic
             python evaluate_matcher.py --dataset path/to/dir --full-composite
  3. The report (Precision@1, Hit@3, Hit@5, MRR, threshold sweep, per-query
     outcomes) is written to evaluation/lost_found_dataset/evaluation_report.md.

Accuracy percentages are ONLY ever reported from an actual measured run of
this script against a concrete dataset. Never quote a number from the
synthetic smoke test as real-world accuracy.
"""
import argparse
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_DATASET = BASE_DIR / "evaluation" / "lost_found_dataset"
DEFAULT_REPORT = DEFAULT_DATASET / "evaluation_report.md"


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate the Lost & Found AI matcher")
    parser.add_argument("--dataset", default=str(DEFAULT_DATASET),
                        help="Dataset root containing queries/<label>/ and gallery/<label>/")
    parser.add_argument("--report", default=None, help="Markdown report output path")
    parser.add_argument("--generate-synthetic", action="store_true",
                        help="Create deterministic SYNTHETIC labeled images first "
                             "(procedure smoke test; results describe the synthetic set only)")
    parser.add_argument("--full-composite", action="store_true",
                        help="Rank with image + text metadata composite instead of image-only cosine")
    args = parser.parse_args()

    from app.utils.matcher_eval import (
        generate_synthetic_dataset, run_evaluation, format_report)

    root = Path(args.dataset)
    if args.generate_synthetic:
        counts = generate_synthetic_dataset(str(root))
        print(f"Synthetic sample set generated: {sum(counts.values())} images across "
              f"{len(counts)} labels under {root}")
        print("NOTE: synthetic images validate the PROCEDURE, not real-world accuracy.\n")

    metrics = run_evaluation(str(root), use_text_context=args.full_composite)
    report = format_report(metrics)
    print(report)

    out_path = Path(args.report) if args.report else root / "evaluation_report.md"
    if "error" not in metrics:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(report, encoding="utf-8")
        print(f"\nReport saved to {out_path}")
        return 0
    print(f"\nEvaluation did not run: {metrics['error']}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
