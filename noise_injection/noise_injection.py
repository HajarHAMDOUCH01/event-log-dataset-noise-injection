"""
Noise-injection pipeline that rebalances a XES event log's token-based-replay
fitness distribution toward:
    >= 70% of traces with fitness <= 0.70
    >= 20% of traces with fitness in [0.70, 0.80]
    >= 10% of traces with fitness in [0.80, 1.00]

Approach :
    - Multiple combinable control-flow noise operators: skip (remove event),
      insert (random foreign event), rework (duplicate an event), swap
      (transpose two adjacent events).
    - Severity controlled by a noise percentage p: num_edits per trace = max(1, round(p * len(trace))). Each edit randomly picks one enabled
      operator.
    - every candidate noised trace fitness is recalculated
      with real token-based replay against the PNML before being accepted.
    - Iterative retry: if a trace doesn't land in its target bin, noise
      percentage is increased and reapplied, up to a max number of attempts.

Output:
    - A new XES log with 'is_fit' / 'trace_fitness' trace attributes
      recomputed after noise injection.
    - A CSV with the final fitness-bin distribution stats.
"""

import argparse
import os
import copy
import random
import csv

import pm4py
from pm4py.objects.log.obj import EventLog, Trace, Event
from pm4py.objects.log.importer.xes import importer as xes_importer
from pm4py.objects.log.exporter.xes import exporter as xes_exporter
from pm4py.objects.petri_net.importer import importer as pnml_importer
from pm4py.algo.conformance.tokenreplay import algorithm as token_replay
from pathlib import Path

import pm4py
import matplotlib.pyplot as plt


def plot_fitness_distribution_before_after(
    before_xes: str,
    after_xes: str,
    output_path: str | None = None,
):
    """
    Compare the trace fitness distribution before and after noise injection.

    Fitness bins:
        - Low:    fitness <= 0.70
        - Medium: 0.70 < fitness <= 0.80
        - High:   fitness > 0.80

    Parameters
    ----------
    before_xes : str
        Path to the original XES event log.
    after_xes : str
        Path to the noisy XES event log.

    output_path : str | None
        If provided, saves the figure to this path.

    Returns
    -------
    dict
        Percentages of traces in each fitness bin before and after noise.
    """

    # ---------------------------------------------------------
    # 1. Load XES logs
    # ---------------------------------------------------------
    before_log = pm4py.read_xes(before_xes)
    after_log = pm4py.read_xes(after_xes)

    # ---------------------------------------------------------
    # 2. Extract trace fitness
    # ---------------------------------------------------------
    # def get_fitness_values(log):
    #     fitness_values = []

    #     for _, trace in log.groupby("case:concept:name"):
    #         if "trace_fitness" not in trace.columns:
    #             raise ValueError(
    #                 f"'trace_fitness' attribute not found in {before_xes}"
    #             )

    #         fitness = trace["trace_fitness"].iloc[0]

    #         if fitness is not None:
    #             fitness_values.append(float(fitness))

    #     if not fitness_values:
    #         raise ValueError("No valid trace fitness values found.")

    #     return fitness_values


    def get_fitness_values(xes_path):
        log = xes_importer.apply(xes_path)

        fitness_values = []

        for trace in log:
            fitness = trace.attributes.get("trace_fitness")

            if fitness is not None:
                fitness_values.append(float(fitness))

        if not fitness_values:
            raise ValueError(
                f"'trace_fitness' attribute not found in {xes_path}"
            )

        return fitness_values

    before_fitness = get_fitness_values(before_xes)
    after_fitness = get_fitness_values(after_xes)

    # ---------------------------------------------------------
    # 3. Count traces in each fitness bin
    # ---------------------------------------------------------
    def get_bin_percentages(fitness_values):
        total = len(fitness_values)

        low = sum(f <= 0.70 for f in fitness_values)
        medium = sum(0.70 < f <= 0.80 for f in fitness_values)
        high = sum(f > 0.80 for f in fitness_values)

        return [
            100 * low / total,
            100 * medium / total,
            100 * high / total,
        ]

    before_percentages = get_bin_percentages(before_fitness)
    after_percentages = get_bin_percentages(after_fitness)

    # ---------------------------------------------------------
    # 4. Plot
    # ---------------------------------------------------------
    bins = [
        "Low\n≤ 0.70",
        "Medium\n0.70–0.80",
        "High\n> 0.80",
    ]

    x = range(len(bins))
    width = 0.35

    fig, ax = plt.subplots(figsize=(9, 6))

    before_bars = ax.bar(
        [i - width / 2 for i in x],
        before_percentages,
        width,
        label="Before noise",
    )

    after_bars = ax.bar(
        [i + width / 2 for i in x],
        after_percentages,
        width,
        label="After noise",
    )

    # Add percentage labels above bars
    for bars in [before_bars, after_bars]:
        for bar in bars:
            height = bar.get_height()
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                height,
                f"{height:.1f}%",
                ha="center",
                va="bottom",
            )

    # Target percentages
    ax.axhline(
        70,
        linestyle="--",
        linewidth=1,
        label="Target: ≥70% low fitness",
    )

    ax.set_xticks(list(x))
    ax.set_xticklabels(bins)

    ax.set_ylabel("Percentage of traces")
    ax.set_xlabel("Fitness bin")

    ax.set_title("Trace Fitness Distribution Before and After Noise Injection")

    ax.set_ylim(0, 100)
    ax.legend()

    plt.tight_layout()

    # ---------------------------------------------------------
    # 5. Save / display
    # ---------------------------------------------------------
    if output_path is not None:
        Path(output_path).parent.mkdir(
            parents=True,
            exist_ok=True,
        )
        plt.savefig(output_path, dpi=300, bbox_inches="tight")

    plt.show()

    return {
        "before": dict(zip(bins, before_percentages)),
        "after": dict(zip(bins, after_percentages)),
    }
def parse_arguments():
    parser = argparse.ArgumentParser(
        description="Inject noise into XES event log to rebalance fitness distribution"
    )
    parser.add_argument(
        "--xes-input",
        type=str,
        required=True,
        help="Path to input XES event log file"
    )
    parser.add_argument(
        "--pnml-model",
        type=str,
        required=True,
        help="Path to input PNML Petri net model file"
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        required=True,
        help="Directory where output XES and CSV files will be saved"
    )
    parser.add_argument(
        "--target-bin1",
        type=float,
        default=0.70,
        help="Target proportion for bin_1 (fitness <= 0.70). Default: 0.70"
    )
    parser.add_argument(
        "--target-bin2",
        type=float,
        default=0.20,
        help="Target proportion for bin_2 (0.70 < fitness <= 0.80). Default: 0.20"
    )
    parser.add_argument(
        "--target-bin3",
        type=float,
        default=0.10,
        help="Target proportion for bin_3 (fitness > 0.80). Default: 0.10"
    )
    parser.add_argument(
        "--sample-size",
        type=int,
        default=13000,
        help="Maximum number of traces to process. If input has more, randomly subsample. Default: 50000"
    )
    parser.add_argument(
        "--noise-levels",
        type=str,
        default="0.10,0.20,0.35,0.50,0.70,0.90,1.00,1.50,2.00,3.00",
        help="Comma-separated noise percentages to try (ladder). Default: 0.10,0.20,0.35,0.50,0.70,0.90,1.00"
    )
    parser.add_argument(
        "--extra-retries",
        type=int,
        default=3,
        help="Extra random restarts at maximum noise level if trace unmatched. Default: 6"
    )
    parser.add_argument(
        "--random-seed",
        type=int,
        default=42,
        help="Random seed for reproducibility. Default: 42"
    )
    return parser.parse_args()


# ── Bin helpers ───────────────────────────────────────────────────────────────
def classify_bin(fitness):
    if fitness <= 0.70:
        return "bin_1"
    elif fitness <= 0.80:
        return "bin_2"
    else:
        return "bin_3"




# ── Bypassability analysis ─────────────────────────────────────────────────
def find_non_bypassable_activities(net):
    """
    Returns the set of activity labels whose transition has NO invisible
    (tau) transition sharing an input place — meaning token-replay has no
    silent path to route around a missing/extra occurrence of that activity.
    Noise applied to these activities actually moves fitness; noise applied
    to "bypassable" activities is often absorbed for free by the model.
    """
    bypassable = set()
    for t in net.transitions:
        if t.label is None:
            continue
        for arc in t.in_arcs:
            place = arc.source
            for out_arc in place.out_arcs:
                other_t = out_arc.target
                if other_t.label is None:
                    bypassable.add(t.label)
    all_labels = {t.label for t in net.transitions if t.label is not None}
    non_bypassable = all_labels - bypassable
    return non_bypassable

# ── Noise operators ────────────────────────────────────────────────────────────
def _clone_event(ev):
    e = Event()
    for k, v in ev.items():
        e[k] = v
    return e


def _weighted_index(events, hard_activities, bias=0.7):
    """
    Pick an event index to target. With probability `bias`, prefer an
    event whose activity has no invisible bypass (so the edit actually
    costs fitness). Falls back to uniform random otherwise.
    """
    if not events:
        return 0
    if hard_activities:
        hard_idxs = [i for i, ev in enumerate(events)
                     if ev.get("concept:name") in hard_activities]
        if hard_idxs and random.random() < bias:
            return random.choice(hard_idxs)
    return random.randrange(len(events))


def op_skip(events, activity_alphabet, hard_activities=None):
    if len(events) <= 1:
        return events
    idx = _weighted_index(events, hard_activities)
    return events[:idx] + events[idx + 1:]


def op_bulk_skip(events, activity_alphabet, hard_activities=None):
    """Remove a contiguous span (20-50% of the trace) instead of one event.
    Much harder for the model to absorb via invisible transitions than a
    single skip."""
    if len(events) <= 2:
        return events
    span = max(1, round(random.uniform(0.2, 0.5) * len(events)))
    span = min(span, len(events) - 1)
    center = _weighted_index(events, hard_activities)
    start = max(0, min(center - span // 2, len(events) - span))
    return events[:start] + events[start + span:]


def op_insert(events, activity_alphabet, hard_activities=None):
    idx = random.randrange(len(events) + 1)
    new_activity = random.choice(activity_alphabet)

    new_event = _clone_event(events[min(idx, len(events) - 1)]) if events else Event()
    new_event["concept:name"] = new_activity

    if events:
        left_ts = events[idx - 1]["time:timestamp"] if idx > 0 else events[0]["time:timestamp"]
        right_ts = events[idx]["time:timestamp"] if idx < len(events) else events[-1]["time:timestamp"]
        mid_ts = left_ts + (right_ts - left_ts) / 2
        new_event["time:timestamp"] = mid_ts

    return events[:idx] + [new_event] + events[idx:]


def op_replace(events, activity_alphabet, hard_activities=None):
    """Swap an existing event's label for a foreign one — corrupts an
    event the model was expecting, rather than just adding an extra one
    it might tolerate via an invisible transition."""
    if not events:
        return events
    idx = _weighted_index(events, hard_activities)
    new_events = list(events)
    ev = _clone_event(new_events[idx])
    ev["concept:name"] = random.choice(activity_alphabet)
    new_events[idx] = ev
    return new_events


def op_rework(events, activity_alphabet, hard_activities=None):
    if not events:
        return events
    idx = random.randrange(len(events))
    dup = _clone_event(events[idx])
    insert_at = random.randrange(idx, len(events) + 1)
    return events[:insert_at] + [dup] + events[insert_at:]


def op_swap(events, activity_alphabet, hard_activities=None):
    if len(events) < 2:
        return events
    idx = random.randrange(len(events) - 1)
    new_events = list(events)
    new_events[idx], new_events[idx + 1] = new_events[idx + 1], new_events[idx]
    return new_events


NOISE_OPERATORS = [op_skip, op_insert, op_rework, op_swap, op_bulk_skip, op_replace]

def apply_noise_to_trace(trace, noise_pct, activity_alphabet, hard_activities=None):
    """Return a new list of events with noise_pct-controlled combined edits."""
    events = list(trace)
    num_edits = max(1, round(noise_pct * len(events)))
    for _ in range(num_edits):
        if not events:
            break
        op = random.choice(NOISE_OPERATORS)
        events = op(events, activity_alphabet, hard_activities)
    return events


def build_trace(case_id, events):
    t = Trace()
    t.attributes["concept:name"] = case_id
    for ev in events:
        t.append(ev)
    return t


# ── Token replay helper (single trace) ────────────────────────────────────────
def replay_fitness_single(trace, net, im, fm):
    tmp_log = EventLog()
    tmp_log.append(trace)
    result = token_replay.apply(tmp_log, net, im, fm)[0]
    return result["trace_fitness"], result["trace_is_fit"]

def add_token_replay_fitness(log, net, im, fm):
    """
    Compute token-based replay fitness for every trace
    and store the results as trace attributes.
    """
    replay_results = token_replay.apply(log, net, im, fm)

    for trace, result in zip(log, replay_results):
        trace.attributes["trace_fitness"] = float(result["trace_fitness"])
        trace.attributes["is_fit"] = bool(result["trace_is_fit"])

    return log
# ── Main pipeline ──────────────────────────────────────────────────────────────
def main():
    args = parse_arguments()
    
    XES_IN_PATH = args.xes_input
    PNML_PATH = args.pnml_model
    OUT_DIR = args.output_dir
    XES_OUT_PATH = os.path.join(OUT_DIR, "balanced_noise_injected.xes")
    PLOT_OUT_PATH = os.path.join(OUT_DIR, "comparison_plot.png")
    STATS_CSV_OUT = os.path.join(OUT_DIR, "balanced_noise_injected_stats.csv")
    
    TARGET_PROPORTIONS = {
        "bin_1": args.target_bin1,
        "bin_2": args.target_bin2,
        "bin_3": args.target_bin3,
    }
    
    NOISE_LEVELS = [float(x.strip()) for x in args.noise_levels.split(",")]
    EXTRA_RETRIES_AT_MAX_NOISE = args.extra_retries
    MAX_ATTEMPTS_PER_TRACE = len(NOISE_LEVELS) + EXTRA_RETRIES_AT_MAX_NOISE
    SAMPLE_SIZE = args.sample_size
    RANDOM_SEED = args.random_seed
    
    random.seed(RANDOM_SEED)
    os.makedirs(OUT_DIR, exist_ok=True)

    print(f"[XES] Loading log from {XES_IN_PATH} ...")
    log = xes_importer.apply(XES_IN_PATH)
    n_full = len(log)
    print(f"[XES] Log loaded - {n_full} traces")

    # ── Randomly subsample down to a target size ──────────────────────────────
    if n_full > SAMPLE_SIZE:
        sampled_traces = random.sample(list(log), SAMPLE_SIZE)
        log = EventLog(sampled_traces)
        print(f"[SAMPLE] Randomly subsampled log from {n_full} to {len(log)} traces")
    else:
        print(f"[SAMPLE] Log has {n_full} traces, <= target {SAMPLE_SIZE}, keeping all")

    n = len(log)
    print(f"[XES] Log loaded - {n} traces")

    print(f"\n[PNML] Loading model from {PNML_PATH} ...")
    net, im, fm = pnml_importer.apply(PNML_PATH)
    print(f"[PNML] Net loaded - places: {len(net.places)}, transitions: {len(net.transitions)}, arcs: {len(net.arcs)}")
    print("[TBR] Computing token-based replay fitness for original log...")
    log = add_token_replay_fitness(log, net, im, fm)

    print("[TBR] Original trace fitness computed.")

    ORIGINAL_FITNESS_XES = os.path.join(
        OUT_DIR,
        "original_with_fitness.xes"
    )

    xes_exporter.apply(
        log,
        ORIGINAL_FITNESS_XES
    )
    # activity_alphabet = sorted({
    #     ev["concept:name"] for trace in log for ev in trace
    # })
    # print(f"[ALPHABET] {len(activity_alphabet)} distinct activities available for 'insert' noise")


    # hard_activities = find_non_bypassable_activities(net)
    # print(f"[BYPASS] {len(hard_activities)}/{len(activity_alphabet)} activities have no "
    #     f"invisible-transition bypass (noise on these actually costs fitness)")
    # if len(hard_activities) == 0:
    #     print("[BYPASS] WARNING - every activity has a silent bypass; noise operators "
    #         "may struggle to reduce fitness regardless of intensity.")




    # # ── 1. Classify traces by their existing (pre-noise) fitness ─────────────
    # traces_with_fitness = []
    # for trace in log:
    #     fitness = float(trace.attributes.get("trace_fitness", 0.0))
    #     traces_with_fitness.append((trace, fitness))

    # # Sort descending by fitness: highest-fitness traces are the ones we have
    # # spare / scarce-noise-needed candidates for. We reserve the best ones for
    # # bin_3, and noise-inject the rest toward bin_1 / bin_2.
    # traces_with_fitness.sort(key=lambda x: x[1], reverse=True)

    # target_counts = {
    #     "bin_1": round(TARGET_PROPORTIONS["bin_1"] * n),
    #     "bin_2": round(TARGET_PROPORTIONS["bin_2"] * n),
    # }
    # target_counts["bin_3"] = n - target_counts["bin_1"] - target_counts["bin_2"]

    # print(f"\n[TARGET] bin_1(<=0.70): {target_counts['bin_1']}  "
    #       f"bin_2(0.70-0.80): {target_counts['bin_2']}  "
    #       f"bin_3(0.80-1.00): {target_counts['bin_3']}  (total={n})")

    # # ── 2. Reserve bin_3 quota from traces that are already high-fitness ─────
    # bin3_reserved = []
    # remaining = []
    # for trace, fitness in traces_with_fitness:
    #     if len(bin3_reserved) < target_counts["bin_3"] and fitness >= 0.80:
    #         bin3_reserved.append((trace, fitness))
    #     else:
    #         remaining.append((trace, fitness))

    # print(f"\n[RESERVE] {len(bin3_reserved)} traces reserved untouched for bin_3 "
    #       f"(target was {target_counts['bin_3']})")
    # if len(bin3_reserved) < target_counts["bin_3"]:
    #     print("[RESERVE] WARNING - not enough naturally high-fitness traces to "
    #           "fully cover bin_3 quota; shortfall will be left for bin_1/bin_2 assignment.")

    # # ── 3. Assign remaining traces to bin_1 / bin_2 targets ──────────────────
    # need_bin1 = target_counts["bin_1"]
    # need_bin2 = target_counts["bin_2"] + max(0, target_counts["bin_3"] - len(bin3_reserved))

    # assignment_plan = []
    # for i, (trace, fitness) in enumerate(remaining):
    #     if i < need_bin1:
    #         assignment_plan.append((trace, "bin_1"))
    #     else:
    #         assignment_plan.append((trace, "bin_2"))

    # print(f"[PLAN] {len(assignment_plan)} traces will be noise-injected "
    #       f"({sum(1 for _, b in assignment_plan if b == 'bin_1')} -> bin_1, "
    #       f"{sum(1 for _, b in assignment_plan if b == 'bin_2')} -> bin_2)")

    # # ── 4. Noise-inject each assigned trace with iterative retry ─────────────
    # new_log = EventLog()
    # unmatched_count = 0

    # def in_target_bin(fitness, bin_name):
    #     if bin_name == "bin_1":
    #         return fitness <= 0.70
    #     elif bin_name == "bin_2":
    #         return 0.70 <= fitness <= 0.80
    #     return 0.80 <= fitness <= 1.00

    # def is_closer_to_target(candidate_fitness, current_best_fitness, target_bin):
    #     """True if candidate is a better fallback choice than current_best for target_bin."""
    #     if target_bin == "bin_1":       
    #         return candidate_fitness < current_best_fitness
    #     elif target_bin == "bin_3":     
    #         return candidate_fitness > current_best_fitness
    #     else:                            
    #         return abs(candidate_fitness - 0.75) < abs(current_best_fitness - 0.75)

    # for idx, (trace, target_bin) in enumerate(assignment_plan):
    #     case_id = trace.attributes["concept:name"]
    #     best_events, best_fitness, best_is_fit = None, None, None
    #     matched = False

    #     # Ladder of increasing noise levels, then extra random restarts at max noise
    #     # if the ladder alone wasn't enough to reach the target bin.
    #     noise_pct_sequence = list(NOISE_LEVELS) + [NOISE_LEVELS[-1]] * EXTRA_RETRIES_AT_MAX_NOISE

    #     for noise_pct in noise_pct_sequence:
    #         noised_events = apply_noise_to_trace(list(trace), noise_pct, activity_alphabet, hard_activities)
    #         candidate_trace = build_trace(case_id, noised_events)
    #         fitness, is_fit = replay_fitness_single(candidate_trace, net, im, fm)

    #         if best_fitness is None or is_closer_to_target(fitness, best_fitness, target_bin):
    #             best_events, best_fitness, best_is_fit = noised_events, fitness, is_fit

    #         if in_target_bin(fitness, target_bin):
    #             best_events, best_fitness, best_is_fit = noised_events, fitness, is_fit
    #             matched = True
    #             break

    #     if not matched:
    #         unmatched_count += 1

    #     final_trace = build_trace(case_id, best_events)
    #     final_trace.attributes["is_fit"] = bool(best_is_fit)
    #     final_trace.attributes["trace_fitness"] = float(best_fitness)
    #     new_log.append(final_trace)

    #     if (idx + 1) % 200 == 0:
    #         print(f"[NOISE] Processed {idx + 1}/{len(assignment_plan)} traces...")

    # print(f"\n[NOISE] Done - {unmatched_count}/{len(assignment_plan)} traces "
    #       f"did not land in their target bin after {MAX_ATTEMPTS_PER_TRACE} attempts "
    #       f"(kept their closest result instead).")

    # # ── 5. Append untouched bin_3-reserved traces as-is ───────────────────────
    # for trace, fitness in bin3_reserved:
    #     t = copy.deepcopy(trace)
    #     # is_fit / trace_fitness already present on these from the input XES
    #     new_log.append(t)

    # print(f"\n[LOG] Final balanced log size: {len(new_log)} traces (expected {n})")

    # # ── 6. Final stats ────────────────────────────────────────────────────────
    # fitnesses = [float(t.attributes["trace_fitness"]) for t in new_log]
    # n_final = len(fitnesses)
    # bin_1 = [f for f in fitnesses if f <= 0.70]
    # bin_2 = [f for f in fitnesses if 0.70 <= f <= 0.80]
    # bin_3 = [f for f in fitnesses if 0.80 <= f <= 1.00]

    # rows = [
    #     {"bin": "<= 0.70", "count": len(bin_1), "percentage": 100 * len(bin_1) / n_final},
    #     {"bin": "0.70 - 0.80", "count": len(bin_2), "percentage": 100 * len(bin_2) / n_final},
    #     {"bin": "0.80 - 1.00", "count": len(bin_3), "percentage": 100 * len(bin_3) / n_final},
    #     {"bin": "TOTAL traces", "count": n_final, "percentage": 100.0},
    # ]

    # print("\n── Final fitness distribution (post noise-injection) ────────────────")
    # for r in rows:
    #     print(f"  {r['bin']:<14} : count={r['count']:>6}   percentage={r['percentage']:.2f}%")

    # with open(STATS_CSV_OUT, "w", newline="") as f:
    #     writer = csv.DictWriter(f, fieldnames=["bin", "count", "percentage"])
    #     writer.writeheader()
    #     writer.writerows(rows)
    # print(f"\n[CSV] Final stats saved to {STATS_CSV_OUT}")

    # # ── 7. Export balanced XES ────────────────────────────────────────────────
    # print(f"\n[XES] Exporting balanced log to {XES_OUT_PATH} ...")
    # xes_exporter.apply(new_log, XES_OUT_PATH)
    # print("[XES] Export complete")

    plot_fitness_distribution_before_after(
        before_xes=ORIGINAL_FITNESS_XES,
        after_xes=XES_OUT_PATH,
        output_path=PLOT_OUT_PATH
    )

if __name__ == "__main__":
    main()