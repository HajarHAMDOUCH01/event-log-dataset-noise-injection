"""
Train / validation / test split for the balanced fitness dataset.

Strategy:
    - TEST is the bottom N_test traces by fitness (the hardest / lowest-fitness
      cases in the whole dataset). This guarantees every test-set fitness value
      is strictly lower than every train/val fitness value.
    - TRAIN and VAL are a stratified split of everything else, preserving the
      relative bin_1/bin_2/bin_3 proportions between train and val (both see
      all three bins, same as the full balanced dataset).

Ratios: 70% train / 15% val / 15% test (of the total dataset size).
"""

import os
import csv
import random

from pm4py.objects.log.obj import EventLog
from pm4py.objects.log.importer.xes import importer as xes_importer
from pm4py.objects.log.exporter.xes import exporter as xes_exporter

# ── Config ──────────────────────────────────────────────────────────────────
XES_IN_PATH = r"C:\Users\LENONVO\Downloads\junnea_data_sm2\noise_injection\subset_of_500\final_balanced_dataset.xes"
OUT_DIR     = r"C:\Users\LENONVO\Downloads\junnea_data_sm2\noise_injection\subset_of_500\splits"

TRAIN_FRAC = 0.70
VAL_FRAC   = 0.15
TEST_FRAC  = 0.15   

# Optional: force a manual fitness cutoff for test instead of the auto rank-based
# 15% cutoff (e.g. 0.6). Leave as None to use the automatic rank-based split.
MANUAL_TEST_FITNESS_THRESHOLD = None   # e.g. 0.60

RANDOM_SEED = 42
random.seed(RANDOM_SEED)


def classify_bin(fitness):
    if fitness <= 0.70:
        return "bin_1"
    elif fitness <= 0.80:
        return "bin_2"
    else:
        return "bin_3"


def stratified_split(traces_with_fitness, train_ratio, val_ratio):
    """Split traces into train/val, preserving per-bin proportions."""
    by_bin = {"bin_1": [], "bin_2": [], "bin_3": []}
    for trace, fitness in traces_with_fitness:
        by_bin[classify_bin(fitness)].append((trace, fitness))

    train, val = [], []
    for bin_name, items in by_bin.items():
        random.shuffle(items)
        n_val = round(len(items) * (val_ratio / (train_ratio + val_ratio)))
        val.extend(items[:n_val])
        train.extend(items[n_val:])

    random.shuffle(train)
    random.shuffle(val)
    return train, val


def bin_composition(traces_with_fitness):
    counts = {"bin_1": 0, "bin_2": 0, "bin_3": 0}
    for _, fitness in traces_with_fitness:
        counts[classify_bin(fitness)] += 1
    return counts


def to_event_log(traces_with_fitness):
    log = EventLog()
    for trace, _ in traces_with_fitness:
        log.append(trace)
    return log


def main():
    os.makedirs(OUT_DIR, exist_ok=True)

    print(f"[XES] Loading log from {XES_IN_PATH} ...")
    log = xes_importer.apply(XES_IN_PATH)
    n = len(log)
    print(f"[XES] Log loaded , {n} traces")

    traces_with_fitness = [
        (trace, float(trace.attributes["trace_fitness"])) for trace in log
    ]

    # ── 1.TEST ────────────────
    traces_with_fitness.sort(key=lambda x: x[1])  # ascending: hardest first

    if MANUAL_TEST_FITNESS_THRESHOLD is not None:
        test_set = [tf for tf in traces_with_fitness if tf[1] <= MANUAL_TEST_FITNESS_THRESHOLD]
        remaining = [tf for tf in traces_with_fitness if tf[1] > MANUAL_TEST_FITNESS_THRESHOLD]
        print(f"\n[TEST] Using manual threshold <= {MANUAL_TEST_FITNESS_THRESHOLD} "
              f"-> {len(test_set)} traces")
    else:
        n_test = round(TEST_FRAC * n)
        if 0 < n_test < n:
            boundary_fitness = traces_with_fitness[n_test - 1][1]
            while n_test < n and traces_with_fitness[n_test][1] == boundary_fitness:
                n_test += 1
        test_set = traces_with_fitness[:n_test]
        remaining = traces_with_fitness[n_test:]
        print(f"\n[TEST] Auto rank-based split -> {len(test_set)} traces (target {round(TEST_FRAC * n)}, "
              f"adjusted for ties)")

    if test_set and remaining:
        test_max_fitness = max(f for _, f in test_set)
        remaining_min_fitness = min(f for _, f in remaining)
        print(f"[TEST] Test fitness range   : {min(f for _, f in test_set):.4f} - {test_max_fitness:.4f}")
        print(f"[TEST] Train/Val min fitness: {remaining_min_fitness:.4f}")
        if test_max_fitness >= remaining_min_fitness:
            print("[TEST] WARNING , fitness ranges overlap due to ties at the cutoff boundary.")
        else:
            print(f"[TEST] Confirmed: every test trace has strictly lower fitness "
                  f"than every train/val trace (gap = {remaining_min_fitness - test_max_fitness:.4f}).")

    # ── 2.TRAIN / VAL ─────────────────
    train_set, val_set = stratified_split(remaining, TRAIN_FRAC, VAL_FRAC)

    print(f"\n[SPLIT] train={len(train_set)}  val={len(val_set)}  test={len(test_set)}  "
          f"(total={len(train_set) + len(val_set) + len(test_set)}, expected {n})")

    # ── 3. Bin composition per split ───────────────────────────────────────────
    splits = {"train": train_set, "val": val_set, "test": test_set}
    stats_rows = []
    print("\n── Bin composition per split ──────────────────────────────────────────")
    for split_name, split_data in splits.items():
        comp = bin_composition(split_data)
        total = len(split_data)
        print(f"  {split_name:<6} : total={total:>5}  "
              f"bin_1={comp['bin_1']:>5} ({100*comp['bin_1']/total if total else 0:.1f}%)  "
              f"bin_2={comp['bin_2']:>5} ({100*comp['bin_2']/total if total else 0:.1f}%)  "
              f"bin_3={comp['bin_3']:>5} ({100*comp['bin_3']/total if total else 0:.1f}%)")
        for bin_name in ("bin_1", "bin_2", "bin_3"):
            stats_rows.append({
                "split": split_name,
                "bin": bin_name,
                "count": comp[bin_name],
                "percentage": 100 * comp[bin_name] / total if total else 0.0,
            })
        stats_rows.append({"split": split_name, "bin": "TOTAL", "count": total, "percentage": 100.0})

    # ── 4. Export XES files ─────────────────────────────────────────────────────
    for split_name, split_data in splits.items():
        out_path = os.path.join(OUT_DIR, f"{split_name}.xes")
        print(f"\n[XES] Exporting {split_name} ({len(split_data)} traces) to {out_path} ...")
        xes_exporter.apply(to_event_log(split_data), out_path)

    # ── 5. Save stats CSV ────────────────────────────────────────────────────────
    stats_csv_path = os.path.join(OUT_DIR, "split_stats.csv")
    with open(stats_csv_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["split", "bin", "count", "percentage"])
        writer.writeheader()
        writer.writerows(stats_rows)
    print(f"\n[CSV] Split stats saved to {stats_csv_path}")

    print("\n[DONE] train/val/test split complete.")


if __name__ == "__main__":
    main()