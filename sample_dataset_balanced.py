"""
Build the final balanced dataset by taking EXACT trace counts from each
fitness bin out of an already fitness-annotated XES (e.g. the output of
noise_injection.py or fitness_stats.py's input log). No further noise
injection needed, this just subsamples what's already in the noise ijected xes traces.
"""

import os
import csv
import random

from pm4py.objects.log.obj import EventLog
from pm4py.objects.log.importer.xes import importer as xes_importer
from pm4py.objects.log.exporter.xes import exporter as xes_exporter

# ── Config ──────────────────────────────────────────────────────────────────
XES_IN_PATH  = r"C:\Users\LENONVO\Downloads\junnea_data_sm2\noise_injection\balanced_noise_injected.xes"
OUT_DIR      = r"C:\Users\LENONVO\Downloads\junnea_data_sm2\noise_injection\subset_of_500"
XES_OUT_PATH  = os.path.join(OUT_DIR, "final_balanced_dataset.xes")
STATS_CSV_OUT = os.path.join(OUT_DIR, "final_balanced_dataset_stats.csv")

# Exact trace counts to pull from each bin. Adjust freely , total dataset
# size is just the sum of these three.
DESIRED_COUNTS = {
    "bin_1": 300,   # fitness <= 0.70          (take ALL available if this equals the max)
    "bin_2": 100,   # 0.70 <= fitness <= 0.80
    "bin_3": 100,    # 0.80 <= fitness <= 1.00
    # "bin_1": 3709,   # fitness <= 0.70          (take ALL available if this equals the max)
    # "bin_2": 1500,   # 0.70 <= fitness <= 0.80
    # "bin_3": 500,    # 0.80 <= fitness <= 1.00
}

RANDOM_SEED = 42
random.seed(RANDOM_SEED)


def classify_bin(fitness):
    if fitness <= 0.70:
        return "bin_1"
    elif fitness <= 0.80:
        return "bin_2"
    else:
        return "bin_3"


def main():
    os.makedirs(OUT_DIR, exist_ok=True)

    print(f"[XES] Loading log from {XES_IN_PATH} ...")
    log = xes_importer.apply(XES_IN_PATH)
    print(f"[XES] Log loaded , {len(log)} traces")

    missing = [t.attributes.get("concept:name") for t in log if "trace_fitness" not in t.attributes]
    if missing:
        raise ValueError(
            f"{len(missing)} traces are missing 'trace_fitness' attribute. "
            f"Sample missing case ids: {missing[:5]}"
        )

    # ── Bucket traces by bin ──────────────────────────────────────────────────
    buckets = {"bin_1": [], "bin_2": [], "bin_3": []}
    for trace in log:
        fitness = float(trace.attributes["trace_fitness"])
        buckets[classify_bin(fitness)].append(trace)

    for bin_name in ("bin_1", "bin_2", "bin_3"):
        print(f"[BUCKET] {bin_name}: {len(buckets[bin_name])} traces available "
              f"(want {DESIRED_COUNTS[bin_name]})")

    # ── Sample exact desired counts (capped to what's available) ─────────────
    final_traces = []
    shortfall = {}
    for bin_name in ("bin_1", "bin_2", "bin_3"):
        available = buckets[bin_name]
        want = DESIRED_COUNTS[bin_name]
        if want > len(available):
            shortfall[bin_name] = want - len(available)
            sampled = available  # take everything available
        else:
            sampled = random.sample(available, want)
        final_traces.extend(sampled)

    if shortfall:
        print("\n[WARNING] Requested more traces than available in these bins "
              "(took everything available instead):")
        for bin_name, missing_n in shortfall.items():
            print(f"  {bin_name}: short by {missing_n}")

    random.shuffle(final_traces)  # avoid bin-ordered blocks in the final log

    new_log = EventLog()
    for t in final_traces:
        new_log.append(t)

    print(f"\n[LOG] Final dataset size: {len(new_log)} traces")

    # ── Final stats ────────────────────────────────────────────────────────────
    fitnesses = [float(t.attributes["trace_fitness"]) for t in new_log]
    n_final = len(fitnesses)
    bin_1 = [f for f in fitnesses if f <= 0.70]
    bin_2 = [f for f in fitnesses if 0.70 <= f <= 0.80]
    bin_3 = [f for f in fitnesses if 0.80 <= f <= 1.00]

    rows = [
        {"bin": "<= 0.70", "count": len(bin_1), "percentage": 100 * len(bin_1) / n_final},
        {"bin": "0.70 - 0.80", "count": len(bin_2), "percentage": 100 * len(bin_2) / n_final},
        {"bin": "0.80 - 1.00", "count": len(bin_3), "percentage": 100 * len(bin_3) / n_final},
        {"bin": "TOTAL traces", "count": n_final, "percentage": 100.0},
    ]

    print("\n── Final dataset distribution ───────────────────────────────────────")
    for r in rows:
        print(f"  {r['bin']:<14} : count={r['count']:>6}   percentage={r['percentage']:.2f}%")

    with open(STATS_CSV_OUT, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["bin", "count", "percentage"])
        writer.writeheader()
        writer.writerows(rows)
    print(f"\n[CSV] Final stats saved to {STATS_CSV_OUT}")

    # ── Export final XES ────────────────────────────────────────────────────────
    print(f"\n[XES] Exporting final dataset to {XES_OUT_PATH} ...")
    xes_exporter.apply(new_log, XES_OUT_PATH)
    print("[XES] Export complete")


if __name__ == "__main__":
    main()