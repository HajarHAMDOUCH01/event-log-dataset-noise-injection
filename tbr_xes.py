# ══════════════════════════════════════════════════════════════════════════════
# TOKEN REPLAY ON XES EVENT LOG
# ══════════════════════════════════════════════════════════════════════════════

import argparse
import pm4py
from pm4py.objects.log.importer.xes import importer as xes_importer
from pm4py.objects.petri_net.importer import importer as pnml_importer
from pm4py.algo.conformance.tokenreplay import algorithm as token_replay
from pm4py.objects.log.exporter.xes import exporter as xes_exporter


def parse_arguments():
    parser = argparse.ArgumentParser(
        description="Run token-based replay on XES event log against a Petri net model"
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
        "--xes-output",
        type=str,
        required=True,
        help="Path to output XES file with fitness metrics added"
    )
    return parser.parse_args()


def main():
    args = parse_arguments()
    
    XES_PATH = args.xes_input
    PNML_PATH = args.pnml_model
    XES_OUT_PATH = args.xes_output

    # ── 1. Load XES log ────────────────────────────────────────────────────────────
    print(f"[XES] Loading log from {XES_PATH} ...")
    log = xes_importer.apply(XES_PATH)
    print(f"[XES] Log loaded , {len(log)} traces")

    # ── 2. Load PNML model ─────────────────────────────────────────────────────────
    print(f"\n[PNML] Loading model from {PNML_PATH} ...")
    net, im, fm = pnml_importer.apply(PNML_PATH)
    print(f"[PNML] Net loaded , places: {len(net.places)}, transitions: {len(net.transitions)}, arcs: {len(net.arcs)}")

    print("\n[MARKING] Initial marking:")
    for place, tokens in im.items():
        print(f"  place='{place.name}'  tokens={tokens}")

    print("[MARKING] Final marking:")
    for place, tokens in fm.items():
        print(f"  place='{place.name}'  tokens={tokens}")

    if not im:
        raise ValueError("Initial marking is empty - the PNML may be missing the <initialMarking> tag.")
    if not fm:
        raise ValueError("Final marking is empty - the PNML may be missing the <finalMarking> tag.")

    # ── 3. Run token replay ────────────────────────────────────────────────────────
    print("\n── Token Replay ──────────────────────────────────────────────────────")
    print(f"[REPLAY] Running token replay on {len(log)} traces...")
    replayed = token_replay.apply(log, net, im, fm)
    print(f"[REPLAY] Done , {len(replayed)} results returned")
    print(f"[REPLAY] Sample result keys : {list(replayed[0].keys())}")

    # ── 4. Build fitness map keyed by case id ──────────────────────────────────────
    case_ids = [trace.attributes["concept:name"] for trace in log]
    print(f"\n[FITNESS MAP] Extracted {len(case_ids)} case IDs from log")

    fitness_map = {
        case_id: {
            "is_fit":        result["trace_is_fit"],
            "trace_fitness": result["trace_fitness"],
        }
        for case_id, result in zip(case_ids, replayed)
    }
    print(f"[FITNESS MAP] Built map for {len(fitness_map)} cases")

    # ── 5. Promote is_fit / trace_fitness to trace attributes ─────────────────────
    missing_cases = []
    for trace in log:
        case_id = trace.attributes["concept:name"]
        attrs   = fitness_map.get(case_id, {})
        if not attrs:
            missing_cases.append(case_id)
        for key, val in attrs.items():
            trace.attributes[key] = val

    print(f"\n[PROMOTE] Trace attributes set on {len(log)} traces")
    if missing_cases:
        print(f"[PROMOTE] WARNING , {len(missing_cases)} cases had no entry in fitness_map: {missing_cases[:5]}")
    else:
        print(f"[PROMOTE] All cases matched successfully")
    print(f"[PROMOTE] Sample trace attributes after promotion: {dict(log[0].attributes)}")

    # ── 6. Summary stats ───────────────────────────────────────────────────────────
    fit_count      = sum(1 for t in replayed if t["trace_is_fit"])
    global_fitness = sum(t["trace_fitness"] for t in replayed) / len(replayed)
    print(f"\nFit traces     : {fit_count} / {len(replayed)} ({100 * fit_count / len(replayed):.1f}%)")
    print(f"Global fitness : {global_fitness:.4f}")

    # ── 7. Export enriched XES ──────────────────────────────────────────────────────
    print(f"\n[XES] Exporting to {XES_OUT_PATH} ...")
    xes_exporter.apply(log, XES_OUT_PATH)
    print(f"[XES] Export complete")


if __name__ == "__main__":
    main()