"""
Compute and save the fitness-bin distribution of a XES log that already has
'trace_fitness' set as a trace-level attribute (e.g. produced by the
token-based-replay enrichment script).

Bins (all boundaries inclusive, as requested):
    bin_1 : fitness <= 0.70
    bin_2 : 0.70 <= fitness <= 0.80
    bin_3 : 0.80 <= fitness <= 1.00

Note: 0.70 and 0.80 are deliberately counted in BOTH adjacent bins since the
boundaries are non-strict on both sides , the printed/saved counts for
bin_1+bin_2+bin_3 can therefore sum to slightly more than the total trace
count. This is intentional, not a bug.
"""

import argparse
import csv
import pm4py
from pm4py.objects.log.importer.xes import importer as xes_importer


def parse_arguments():
    parser = argparse.ArgumentParser(
        description="Compute and save fitness-bin distribution of a XES log"
    )
    parser.add_argument(
        "--xes-input",
        type=str,
        required=True,
        help="Path to input XES event log file (must have 'trace_fitness' attribute)"
    )
    parser.add_argument(
        "--csv-output",
        type=str,
        required=True,
        help="Path to output CSV file with fitness statistics"
    )
    return parser.parse_args()


def compute_fitness_bins(log):
    fitnesses = [float(trace.attributes["trace_fitness"]) for trace in log]
    n = len(fitnesses)

    bin_1 = [f for f in fitnesses if f <= 0.70]
    bin_2 = [f for f in fitnesses if 0.70 <= f <= 0.80]
    bin_3 = [f for f in fitnesses if 0.80 <= f <= 1.00]

    rows = [
        {
            "bin": "<= 0.70",
            "count": len(bin_1),
            "percentage": 100 * len(bin_1) / n if n else 0.0,
        },
        {
            "bin": "0.70 - 0.80",
            "count": len(bin_2),
            "percentage": 100 * len(bin_2) / n if n else 0.0,
        },
        {
            "bin": "0.80 - 1.00",
            "count": len(bin_3),
            "percentage": 100 * len(bin_3) / n if n else 0.0,
        },
        {
            "bin": "TOTAL traces",
            "count": n,
            "percentage": 100.0,
        },
    ]
    return rows


def main():
    args = parse_arguments()
    
    XES_PATH = args.xes_input
    STATS_CSV_OUT = args.csv_output

    print(f"[XES] Loading log from {XES_PATH} ...")
    log = xes_importer.apply(XES_PATH)
    print(f"[XES] Log loaded , {len(log)} traces")

    missing = [t.attributes.get("concept:name") for t in log if "trace_fitness" not in t.attributes]
    if missing:
        raise ValueError(
            f"{len(missing)} traces are missing 'trace_fitness' attribute. "
            f"Sample missing case ids: {missing[:5]}"
        )

    rows = compute_fitness_bins(log)

    print("\n── Fitness distribution ─────────────────────────────────────────────")
    for r in rows:
        print(f"  {r['bin']:<14} : count={r['count']:>6}   percentage={r['percentage']:.2f}%")

    with open(STATS_CSV_OUT, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["bin", "count", "percentage"])
        writer.writeheader()
        writer.writerows(rows)

    print(f"\n[CSV] Stats saved to {STATS_CSV_OUT}")


if __name__ == "__main__":
    main()