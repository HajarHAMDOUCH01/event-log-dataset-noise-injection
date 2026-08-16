import argparse
import pm4py


def parse_arguments():
    parser = argparse.ArgumentParser(
        description="Visualize a Petri net model from a PNML file and save as PNG"
    )
    parser.add_argument(
        "--pnml-input",
        type=str,
        required=True,
        help="Path to input PNML Petri net model file"
    )
    parser.add_argument(
        "--png-output",
        type=str,
        required=True,
        help="Path to output PNG visualization file"
    )
    return parser.parse_args()


def main():
    args = parse_arguments()
    
    PNML_PATH = args.pnml_input
    PNG_PATH = args.png_output

    print(f"[PNML] Loading Petri net from {PNML_PATH} ...")
    net, initial_marking, final_marking = pm4py.read_pnml(PNML_PATH)
    print(f"[PNML] Net loaded - places: {len(net.places)}, transitions: {len(net.transitions)}")

    print(f"[VIZ] Generating visualization ...")
    pm4py.save_vis_petri_net(net, initial_marking, final_marking, PNG_PATH)
    print(f"[VIZ] Visualization saved to {PNG_PATH}")


if __name__ == "__main__":
    main()