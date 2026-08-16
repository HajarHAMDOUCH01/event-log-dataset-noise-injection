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

# ── Config ──────────────────────────────────────────────────────────────────
# XES_IN_PATH   = r"C:\Users\LENONVO\Downloads\BPIC_2019\event_logs_BPIC_2019\BPIC_2019.xes\sm2_tbr_fitness_metric\tmpkt56wi_6xes_with_conf_metric_sm2.xes"    
# PNML_PATH     = r"C:\Users\LENONVO\Downloads\BPIC_2019\split_miner_models\split_miner_sm2_eps0.1_eta0.4.pnml"
# OUT_DIR       = r"C:\Users\LENONVO\Downloads\BPIC_2019\event_logs_BPIC_2019\BPIC_2019.xes\sm2_tbr_fitness_metric\noise_injection"
# XES_OUT_PATH  = os.path.join(OUT_DIR, "balanced_noise_injected.xes")
# STATS_CSV_OUT = os.path.join(OUT_DIR, "balanced_noise_injected_stats.csv")


XES_IN_PATH   = r"C:\Users\LENONVO\Downloads\junnea_data_sm2\xes_conf_metric_sm2_junneau_training_set.xes"
PNML_PATH     = r"C:\Users\LENONVO\Downloads\junnea_data_sm2\model_sm2_junneau_data.pnml"
OUT_DIR       = r"C:\Users\LENONVO\Downloads\junnea_data_sm2\noise_injection"
XES_OUT_PATH  = os.path.join(OUT_DIR, "balanced_noise_injected.xes")
STATS_CSV_OUT = os.path.join(OUT_DIR, "balanced_noise_injected_stats.csv")

TARGET_PROPORTIONS = {
    "bin_1": 0.70,   # fitness <= 0.70
    "bin_2": 0.20,   # 0.70 <= fitness <= 0.80
    "bin_3": 0.10,   # 0.80 <= fitness <= 1.00
}

NOISE_LEVELS = [0.10, 0.20, 0.35, 0.50, 0.70, 0.90, 1.00]  # ladder of noise % to try, per trace
EXTRA_RETRIES_AT_MAX_NOISE = 6   # extra random restarts at the top of the ladder if still unmatched
MAX_ATTEMPTS_PER_TRACE = len(NOISE_LEVELS) + EXTRA_RETRIES_AT_MAX_NOISE
RANDOM_SEED = 42

random.seed(RANDOM_SEED)


# ── Bin helpers ───────────────────────────────────────────────────────────────
def classify_bin(fitness):
    if fitness <= 0.70:
        return "bin_1"
    elif fitness <= 0.80:
        return "bin_2"
    else:
        return "bin_3"


# ── Noise operators ────────────────────────────────────────────────────────────
def _clone_event(ev):
    e = Event()
    for k, v in ev.items():
        e[k] = v
    return e


def op_skip(events, activity_alphabet):
    if len(events) <= 1:
        return events
    idx = random.randrange(len(events))
    return events[:idx] + events[idx + 1:]


def op_insert(events, activity_alphabet):
    idx = random.randrange(len(events) + 1)
    new_activity = random.choice(activity_alphabet)

    new_event = _clone_event(events[min(idx, len(events) - 1)]) if events else Event()
    new_event["concept:name"] = new_activity

    # crude timestamp interpolation so the log stays chronologically sane
    if events:
        left_ts = events[idx - 1]["time:timestamp"] if idx > 0 else events[0]["time:timestamp"]
        right_ts = events[idx]["time:timestamp"] if idx < len(events) else events[-1]["time:timestamp"]
        mid_ts = left_ts + (right_ts - left_ts) / 2
        new_event["time:timestamp"] = mid_ts

    return events[:idx] + [new_event] + events[idx:]


def op_rework(events, activity_alphabet):
    if not events:
        return events
    idx = random.randrange(len(events))
    dup = _clone_event(events[idx])
    insert_at = random.randrange(idx, len(events) + 1)
    return events[:insert_at] + [dup] + events[insert_at:]


def op_swap(events, activity_alphabet):
    if len(events) < 2:
        return events
    idx = random.randrange(len(events) - 1)
    new_events = list(events)
    new_events[idx], new_events[idx + 1] = new_events[idx + 1], new_events[idx]
    return new_events


NOISE_OPERATORS = [op_skip, op_insert, op_rework, op_swap]


def apply_noise_to_trace(trace, noise_pct, activity_alphabet):
    """Return a new list of events with noise_pct-controlled combined edits."""
    events = list(trace)
    num_edits = max(1, round(noise_pct * len(events)))
    for _ in range(num_edits):
        if not events:
            break
        op = random.choice(NOISE_OPERATORS)
        events = op(events, activity_alphabet)
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


# ── Main pipeline ──────────────────────────────────────────────────────────────
def main():
    os.makedirs(OUT_DIR, exist_ok=True)

    print(f"[XES] Loading log from {XES_IN_PATH} ...")
    log = xes_importer.apply(XES_IN_PATH)
    n_full = len(log)
    print(f"[XES] Log loaded - {n_full} traces")

    # ── Randomly subsample down to a target size ──────────────────────────────
    SAMPLE_SIZE = 50000

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

    activity_alphabet = sorted({
        ev["concept:name"] for trace in log for ev in trace
    })
    print(f"[ALPHABET] {len(activity_alphabet)} distinct activities available for 'insert' noise")

    # ── 1. Classify traces by their existing (pre-noise) fitness ─────────────
    traces_with_fitness = []
    for trace in log:
        fitness = float(trace.attributes.get("trace_fitness", 0.0))
        traces_with_fitness.append((trace, fitness))

    # Sort descending by fitness: highest-fitness traces are the ones we have
    # spare / scarce-noise-needed candidates for. We reserve the best ones for
    # bin_3, and noise-inject the rest toward bin_1 / bin_2.
    traces_with_fitness.sort(key=lambda x: x[1], reverse=True)

    target_counts = {
        "bin_1": round(TARGET_PROPORTIONS["bin_1"] * n),
        "bin_2": round(TARGET_PROPORTIONS["bin_2"] * n),
    }
    target_counts["bin_3"] = n - target_counts["bin_1"] - target_counts["bin_2"]

    print(f"\n[TARGET] bin_1(<=0.70): {target_counts['bin_1']}  "
          f"bin_2(0.70-0.80): {target_counts['bin_2']}  "
          f"bin_3(0.80-1.00): {target_counts['bin_3']}  (total={n})")

    # ── 2. Reserve bin_3 quota from traces that are already high-fitness ─────
    bin3_reserved = []
    remaining = []
    for trace, fitness in traces_with_fitness:
        if len(bin3_reserved) < target_counts["bin_3"] and fitness >= 0.80:
            bin3_reserved.append((trace, fitness))
        else:
            remaining.append((trace, fitness))

    print(f"\n[RESERVE] {len(bin3_reserved)} traces reserved untouched for bin_3 "
          f"(target was {target_counts['bin_3']})")
    if len(bin3_reserved) < target_counts["bin_3"]:
        print("[RESERVE] WARNING - not enough naturally high-fitness traces to "
              "fully cover bin_3 quota; shortfall will be left for bin_1/bin_2 assignment.")

    # ── 3. Assign remaining traces to bin_1 / bin_2 targets ──────────────────
    need_bin1 = target_counts["bin_1"]
    need_bin2 = target_counts["bin_2"] + max(0, target_counts["bin_3"] - len(bin3_reserved))

    assignment_plan = []
    for i, (trace, fitness) in enumerate(remaining):
        if i < need_bin1:
            assignment_plan.append((trace, "bin_1"))
        else:
            assignment_plan.append((trace, "bin_2"))

    print(f"[PLAN] {len(assignment_plan)} traces will be noise-injected "
          f"({sum(1 for _, b in assignment_plan if b == 'bin_1')} -> bin_1, "
          f"{sum(1 for _, b in assignment_plan if b == 'bin_2')} -> bin_2)")

    # ── 4. Noise-inject each assigned trace with iterative retry ─────────────
    new_log = EventLog()
    unmatched_count = 0

    def in_target_bin(fitness, bin_name):
        if bin_name == "bin_1":
            return fitness <= 0.70
        elif bin_name == "bin_2":
            return 0.70 <= fitness <= 0.80
        return 0.80 <= fitness <= 1.00

    def is_closer_to_target(candidate_fitness, current_best_fitness, target_bin):
        """True if candidate is a better fallback choice than current_best for target_bin."""
        if target_bin == "bin_1":       
            return candidate_fitness < current_best_fitness
        elif target_bin == "bin_3":     
            return candidate_fitness > current_best_fitness
        else:                            
            return abs(candidate_fitness - 0.75) < abs(current_best_fitness - 0.75)

    for idx, (trace, target_bin) in enumerate(assignment_plan):
        case_id = trace.attributes["concept:name"]
        best_events, best_fitness, best_is_fit = None, None, None
        matched = False

        # Ladder of increasing noise levels, then extra random restarts at max noise
        # if the ladder alone wasn't enough to reach the target bin.
        noise_pct_sequence = list(NOISE_LEVELS) + [NOISE_LEVELS[-1]] * EXTRA_RETRIES_AT_MAX_NOISE

        for noise_pct in noise_pct_sequence:
            noised_events = apply_noise_to_trace(list(trace), noise_pct, activity_alphabet)
            candidate_trace = build_trace(case_id, noised_events)
            fitness, is_fit = replay_fitness_single(candidate_trace, net, im, fm)

            if best_fitness is None or is_closer_to_target(fitness, best_fitness, target_bin):
                best_events, best_fitness, best_is_fit = noised_events, fitness, is_fit

            if in_target_bin(fitness, target_bin):
                best_events, best_fitness, best_is_fit = noised_events, fitness, is_fit
                matched = True
                break

        if not matched:
            unmatched_count += 1

        final_trace = build_trace(case_id, best_events)
        final_trace.attributes["is_fit"] = bool(best_is_fit)
        final_trace.attributes["trace_fitness"] = float(best_fitness)
        new_log.append(final_trace)

        if (idx + 1) % 200 == 0:
            print(f"[NOISE] Processed {idx + 1}/{len(assignment_plan)} traces...")

    print(f"\n[NOISE] Done - {unmatched_count}/{len(assignment_plan)} traces "
          f"did not land in their target bin after {MAX_ATTEMPTS_PER_TRACE} attempts "
          f"(kept their closest result instead).")

    # ── 5. Append untouched bin_3-reserved traces as-is ───────────────────────
    for trace, fitness in bin3_reserved:
        t = copy.deepcopy(trace)
        # is_fit / trace_fitness already present on these from the input XES
        new_log.append(t)

    print(f"\n[LOG] Final balanced log size: {len(new_log)} traces (expected {n})")

    # ── 6. Final stats ────────────────────────────────────────────────────────
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

    print("\n── Final fitness distribution (post noise-injection) ────────────────")
    for r in rows:
        print(f"  {r['bin']:<14} : count={r['count']:>6}   percentage={r['percentage']:.2f}%")

    with open(STATS_CSV_OUT, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["bin", "count", "percentage"])
        writer.writeheader()
        writer.writerows(rows)
    print(f"\n[CSV] Final stats saved to {STATS_CSV_OUT}")

    # ── 7. Export balanced XES ────────────────────────────────────────────────
    print(f"\n[XES] Exporting balanced log to {XES_OUT_PATH} ...")
    xes_exporter.apply(new_log, XES_OUT_PATH)
    print("[XES] Export complete")


if __name__ == "__main__":
    main()