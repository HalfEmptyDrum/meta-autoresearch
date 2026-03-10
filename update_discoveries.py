"""Update discoveries.md from a completed autoresearch session's results.tsv.

Reads the experiment log, extracts what worked, what failed, and what crashed,
then merges with any existing discoveries.md to build a persistent cross-session
knowledge base. The agent reads this file at the start of each session.

Usage:
    python update_discoveries.py results.tsv [--session-tag TAG]
"""
import csv
import sys
import argparse
import re
from pathlib import Path
from score_session import score_session

DISCOVERIES_PATH = Path("discoveries.md")


def parse_results(tsv_path: str) -> list[dict]:
    """Parse results.tsv and compute per-experiment deltas."""
    with open(tsv_path) as f:
        rows = list(csv.DictReader(f, delimiter="\t"))

    if not rows:
        raise ValueError(f"Empty results file: {tsv_path}")

    # Parse val_bpb
    for row in rows:
        try:
            row["_bpb"] = float(row["val_bpb"])
        except (ValueError, TypeError):
            row["_bpb"] = None

    baseline = rows[0]
    if baseline.get("_bpb") is None or baseline["_bpb"] == 0.0:
        raise ValueError("First row is not a valid baseline")

    # Track the running best to compute deltas
    best_so_far = baseline["_bpb"]
    experiments = []
    for row in rows[1:]:
        entry = {
            "description": row.get("description", "").strip(),
            "status": row.get("status", "").strip(),
            "val_bpb": row["_bpb"],
            "best_before": best_so_far,
        }
        if row["status"] == "keep" and row["_bpb"] is not None:
            entry["delta"] = best_so_far - row["_bpb"]
            best_so_far = row["_bpb"]
        elif row["status"] == "discard" and row["_bpb"] is not None:
            entry["delta"] = best_so_far - row["_bpb"]  # negative = worse
        else:
            entry["delta"] = None
        experiments.append(entry)

    return experiments


def parse_existing_discoveries(path: Path) -> dict:
    """Parse an existing discoveries.md into sections.

    Returns a dict with keys: kept, dead_ends, crashes, promising, sessions.
    Each value is a list of strings (one per bullet point).
    """
    result = {"kept": [], "dead_ends": [], "crashes": [], "promising": [], "sessions": []}

    if not path.exists():
        return result

    text = path.read_text()
    current_section = None
    section_map = {
        "kept improvements": "kept",
        "dead ends": "dead_ends",
        "crashes": "crashes",
        "promising but unfinished": "promising",
        "session history": "sessions",
    }

    for line in text.splitlines():
        lower = line.strip().lower()
        # Check if this line is a section header
        for header, key in section_map.items():
            if header in lower and line.strip().startswith("#"):
                current_section = key
                break
        else:
            # It's a content line — add to current section if it's a bullet
            if current_section and line.strip().startswith("- "):
                result[current_section].append(line.strip())

    return result


def format_discoveries(
    experiments: list[dict],
    scores: dict,
    session_tag: str,
    existing: dict,
) -> str:
    """Build the updated discoveries.md content."""
    # Categorize new experiments
    new_kept = []
    new_dead_ends = []
    new_crashes = []
    new_promising = []

    for exp in experiments:
        desc = exp["description"]
        if not desc:
            continue

        if exp["status"] == "keep":
            delta = exp["delta"]
            new_kept.append(f"- {desc}: +{delta:.4f} bpb improvement [{session_tag}]")
        elif exp["status"] == "crash":
            new_crashes.append(f"- {desc} [{session_tag}]")
        elif exp["status"] == "discard":
            # "Promising" = discard but close (within 0.001 of the best)
            if exp["delta"] is not None and exp["delta"] > -0.001:
                new_promising.append(
                    f"- {desc}: missed by {abs(exp['delta']):.4f} bpb [{session_tag}]"
                )
            else:
                if exp["delta"] is not None:
                    new_dead_ends.append(
                        f"- {desc}: {exp['delta']:.4f} bpb [{session_tag}]"
                    )
                else:
                    new_dead_ends.append(f"- {desc} [{session_tag}]")

    # Merge with existing
    all_kept = existing["kept"] + new_kept
    all_dead_ends = existing["dead_ends"] + new_dead_ends
    all_crashes = existing["crashes"] + new_crashes
    all_promising = existing["promising"] + new_promising

    # Remove promising entries that later became kept or dead ends
    # (simple dedup by checking if the description prefix appears in kept/dead)
    kept_descs = {extract_desc(line) for line in all_kept}
    dead_descs = {extract_desc(line) for line in all_dead_ends}
    all_promising = [
        p for p in all_promising
        if extract_desc(p) not in kept_descs and extract_desc(p) not in dead_descs
    ]

    # Session history line
    session_line = (
        f"- **{session_tag}**: {scores['n_experiments']} experiments, "
        f"{scores['n_kept']} kept, {scores['n_crashed']} crashed, "
        f"best bpb={scores['final_best_bpb']:.6f} "
        f"(improved {scores['total_improvement']:.4f} from baseline {scores['baseline_bpb']:.6f})"
    )
    all_sessions = existing["sessions"] + [session_line]

    # Build output
    lines = [
        "# discoveries.md — Cross-Session Knowledge Base",
        "",
        "This file is auto-generated by `update_discoveries.py` and read by the agent",
        "at the start of each session. Use this to skip known dead ends and prioritize",
        "known high-value changes.",
        "",
    ]

    lines.append("## Kept Improvements")
    lines.append("")
    if all_kept:
        # Sort by delta (largest first), keeping original order for unparseable lines
        all_kept.sort(key=lambda l: _extract_delta(l), reverse=True)
        lines.extend(all_kept)
    else:
        lines.append("- (none yet)")
    lines.append("")

    lines.append("## Dead Ends")
    lines.append("")
    if all_dead_ends:
        lines.extend(all_dead_ends)
    else:
        lines.append("- (none yet)")
    lines.append("")

    lines.append("## Crashes")
    lines.append("")
    if all_crashes:
        lines.extend(all_crashes)
    else:
        lines.append("- (none yet)")
    lines.append("")

    lines.append("## Promising But Unfinished")
    lines.append("")
    if all_promising:
        lines.extend(all_promising)
    else:
        lines.append("- (none yet)")
    lines.append("")

    lines.append("## Session History")
    lines.append("")
    lines.extend(all_sessions)
    lines.append("")

    return "\n".join(lines)


def extract_desc(line: str) -> str:
    """Extract the description part from a bullet line, ignoring delta and tag."""
    # "- some description: +0.0070 bpb improvement [mar5]" -> "some description"
    text = line.lstrip("- ").strip()
    # Remove trailing tag like [mar5]
    text = re.sub(r"\s*\[.*?\]\s*$", "", text)
    # Remove trailing delta like ": +0.0070 bpb improvement" or ": -0.0123 bpb"
    text = re.sub(r":\s*[+-]?\d+\.\d+\s+bpb.*$", "", text)
    # Remove trailing ": missed by ..."
    text = re.sub(r":\s*missed by.*$", "", text)
    return text.strip().lower()


def _extract_delta(line: str) -> float:
    """Extract the bpb delta from a bullet line for sorting. Returns 0 if unparseable."""
    match = re.search(r"[+-]?(\d+\.\d+)\s+bpb", line)
    if match:
        return float(match.group(1))
    return 0.0


def main():
    parser = argparse.ArgumentParser(description="Update discoveries.md from results.tsv")
    parser.add_argument("results_tsv", help="Path to results.tsv")
    parser.add_argument(
        "--session-tag", default=None,
        help="Tag for this session (default: auto-detected from git branch)"
    )
    args = parser.parse_args()

    # Auto-detect session tag from git branch if not provided
    tag = args.session_tag
    if tag is None:
        import subprocess
        try:
            branch = subprocess.run(
                ["git", "branch", "--show-current"],
                capture_output=True, text=True, check=True
            ).stdout.strip()
            if branch.startswith("autoresearch/"):
                tag = branch.removeprefix("autoresearch/")
            else:
                tag = branch or "unknown"
        except (subprocess.CalledProcessError, FileNotFoundError):
            tag = "unknown"

    experiments = parse_results(args.results_tsv)
    scores = score_session(args.results_tsv)
    existing = parse_existing_discoveries(DISCOVERIES_PATH)
    content = format_discoveries(experiments, scores, tag, existing)

    DISCOVERIES_PATH.write_text(content)

    n_kept = sum(1 for e in experiments if e["status"] == "keep")
    n_dead = sum(1 for e in experiments if e["status"] == "discard")
    n_crash = sum(1 for e in experiments if e["status"] == "crash")
    print(f"Updated {DISCOVERIES_PATH}: {n_kept} kept, {n_dead} discarded, {n_crash} crashed")
    print(f"Session {tag}: best bpb={scores['final_best_bpb']:.6f}")


if __name__ == "__main__":
    main()
