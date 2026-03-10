"""Score an autoresearch session from its results.tsv."""
import csv
import json
import sys


def score_session(tsv_path: str) -> dict:
    with open(tsv_path) as f:
        rows = list(csv.DictReader(f, delimiter="\t"))

    if not rows:
        raise ValueError(f"Empty results file: {tsv_path}")

    # Parse val_bpb, treating non-numeric values as None
    for row in rows:
        try:
            row["_bpb"] = float(row["val_bpb"])
        except (ValueError, TypeError):
            row["_bpb"] = None

    # First row must be the baseline
    baseline_row = rows[0]
    if baseline_row.get("_bpb") is None or baseline_row["_bpb"] == 0.0:
        raise ValueError(
            f"First row is not a valid baseline (val_bpb={baseline_row.get('val_bpb')})"
        )
    baseline = baseline_row["_bpb"]

    experiments = rows[1:]  # everything after baseline
    n_experiments = len(experiments)
    kept = [r for r in experiments if r["status"] == "keep"]
    crashed = [r for r in experiments if r["status"] == "crash"]
    discarded = [r for r in experiments if r["status"] == "discard"]

    # Best bpb across baseline + all kept experiments
    kept_bpbs = [r["_bpb"] for r in kept if r["_bpb"] is not None]
    best_bpb = min([baseline] + kept_bpbs)
    total_improvement = baseline - best_bpb
    keep_rate = len(kept) / max(n_experiments, 1)
    crash_rate = len(crashed) / max(n_experiments, 1)

    # Longest plateau (consecutive non-keep experiments)
    max_plateau = 0
    current = 0
    for row in experiments:
        if row["status"] != "keep":
            current += 1
            max_plateau = max(max_plateau, current)
        else:
            current = 0

    return {
        "final_best_bpb": best_bpb,
        "baseline_bpb": baseline,
        "total_improvement": total_improvement,
        "n_experiments": n_experiments,
        "n_kept": len(kept),
        "n_discarded": len(discarded),
        "n_crashed": len(crashed),
        "keep_rate": keep_rate,
        "crash_rate": crash_rate,
        "max_plateau": max_plateau,
        "improvement_per_experiment": total_improvement / max(n_experiments, 1),
    }


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <results.tsv>", file=sys.stderr)
        sys.exit(1)

    scores = score_session(sys.argv[1])
    print(json.dumps(scores, indent=2))
