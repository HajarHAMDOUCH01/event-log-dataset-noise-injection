# XES event log noise injection and dataset split Scripts - Command-Line Interface

---

##  Quick Start

---

## Scripts and Their Usage

### 1. Token-Based Replay (`tbr_xes.py`)

**Purpose:** Run token-based replay conformance checking on an XES log against a Petri net model.

**Usage:**
```bash
python tbr_xes.py \
  --xes-input <input.xes> \
  --pnml-model <model.pnml> \
  --xes-output <output.xes>
```

**Example:**
```bash
python tbr_xes.py \
  --xes-input ./data/input_log.xes \
  --pnml-model ./models/my_model.pnml \
  --xes-output ./output/log_with_tbr_fitness.xes
```

**Arguments:**
- `--xes-input` (required): Path to input XES event log file
- `--pnml-model` (required): Path to input PNML Petri net model file
- `--xes-output` (required): Path to output XES file with fitness metrics added

---

### 2. Alignment-Based Conformance (`align_based_fitness_xes.py`)

**Purpose:** Run alignment-based conformance checking on an XES log against a Petri net model.

**Usage:**
```bash
python align_based_fitness_xes.py \
  --xes-input <input.xes> \
  --pnml-model <model.pnml> \
  --xes-output <output.xes>
```

**Example:**
```bash
python align_based_fitness_xes.py \
  --xes-input ./data/input_log.xes \
  --pnml-model ./models/my_model.pnml \
  --xes-output ./output/log_with_alignment_fitness.xes
```

**Arguments:**
- `--xes-input` (required): Path to input XES event log file
- `--pnml-model` (required): Path to input PNML Petri net model file
- `--xes-output` (required): Path to output XES file with alignment-based fitness metrics

---

### 3. Fitness Statistics (`fitness_stats.py`)

**Purpose:** Compute and save the fitness-bin distribution of a fitness-annotated XES log.

**Usage:**
```bash
python fitness_stats.py \
  --xes-input <input.xes> \
  --csv-output <output.csv>
```

**Example:**
```bash
python fitness_stats.py \
  --xes-input ./data/annotated_log.xes \
  --csv-output ./output/fitness_distribution.csv
```

**Arguments:**
- `--xes-input` (required): Path to input XES log (must have `trace_fitness` attribute)
- `--csv-output` (required): Path to output CSV file with fitness statistics

**Fitness Bins:**
- `bin_1`: fitness ≤ 0.70
- `bin_2`: 0.70 ≤ fitness ≤ 0.80
- `bin_3`: 0.80 ≤ fitness ≤ 1.00

---

### 4. Sample Balanced Dataset (`sample_dataset_balanced.py`)

**Purpose:** Build a final balanced dataset by subsampling traces from each fitness bin.

**Usage:**
```bash
python sample_dataset_balanced.py \
  --xes-input <input.xes> \
  --output-dir <output_directory>
```

**Example:**
```bash
python sample_dataset_balanced.py \
  --xes-input ./data/balanced_noise_injected.xes \
  --output-dir ./output/balanced_dataset \
  --bin1-count 300 \
  --bin2-count 100 \
  --bin3-count 100
```

**Arguments:**
- `--xes-input` (required): Path to input XES log with `trace_fitness` attribute
- `--output-dir` (required): Directory where output files will be saved
- `--bin1-count` (optional, default: 300): Number of traces to sample from bin_1 (≤0.70)
- `--bin2-count` (optional, default: 100): Number of traces to sample from bin_2 (0.70-0.80)
- `--bin3-count` (optional, default: 100): Number of traces to sample from bin_3 (0.80-1.00)
- `--random-seed` (optional, default: 42): Random seed for reproducibility

**Output:**
- `final_balanced_dataset.xes`: The balanced XES log
- `final_balanced_dataset_stats.csv`: Statistics on the balanced dataset

---

### 5. Split into Train/Val/Test (`split_dataset.py`)

**Purpose:** Split a balanced dataset into train/val/test sets with stratification.

**Usage:**
```bash
python split_dataset.py \
  --xes-input <input.xes> \
  --output-dir <output_directory>
```

**Example:**
```bash
python split_dataset.py \
  --xes-input ./data/final_balanced_dataset.xes \
  --output-dir ./output/splits
```

**Arguments:**
- `--xes-input` (required): Path to input balanced XES log with `trace_fitness` attribute
- `--output-dir` (required): Directory where output files will be saved
- `--train-ratio` (optional, default: 0.70): Proportion for training set
- `--val-ratio` (optional, default: 0.15): Proportion for validation set
- `--test-ratio` (optional, default: 0.15): Proportion for test set
- `--test-fitness-threshold` (optional, default: None): Manual fitness threshold for test set (overrides auto split)
- `--random-seed` (optional, default: 42): Random seed for reproducibility

**Output:**
- `train.xes`: Training set (70% by default)
- `val.xes`: Validation set (15% by default)
- `test.xes`: Test set (15% by default) - lowest fitness traces
- `split_stats.csv`: Detailed statistics per split

**Strategy:**
- Test set contains the **hardest traces** (lowest fitness)
- Train/Val are stratified to preserve fitness bin proportions

---

### 6. Noise Injection (`noise_injection.py`)

**Purpose:** Inject noise into an XES log to rebalance fitness distribution.

**Usage:**
```bash
python noise_injection.py \
  --xes-input <input.xes> \
  --pnml-model <model.pnml> \
  --output-dir <output_directory>
```

**Example:**
```bash
python noise_injection.py \
  --xes-input ./data/input_log.xes \
  --pnml-model ./models/my_model.pnml \
  --output-dir ./output/noise_injection
```

**Arguments:**
- `--xes-input` (required): Path to input XES log with `trace_fitness` attribute
- `--pnml-model` (required): Path to PNML Petri net model
- `--output-dir` (required): Directory where output files will be saved
- `--target-bin1` (optional, default: 0.70): Target proportion for bin_1 (≤0.70)
- `--target-bin2` (optional, default: 0.20): Target proportion for bin_2 (0.70-0.80)
- `--target-bin3` (optional, default: 0.10): Target proportion for bin_3 (0.80-1.00)
- `--sample-size` (optional, default: 50000): Max traces to process (subsamples if needed)
- `--noise-levels` (optional, default: 0.10,0.20,0.35,0.50,0.70,0.90,1.00): Comma-separated noise percentages
- `--extra-retries` (optional, default: 6): Extra retries at max noise level
- `--random-seed` (optional, default: 42): Random seed for reproducibility

**Output:**
- `balanced_noise_injected.xes`: Balanced XES log with noise injection
- `balanced_noise_injected_stats.csv`: Final distribution statistics

**Noise Operators:**
- **Skip**: Remove an event
- **Insert**: Add a random foreign event
- **Rework**: Duplicate an event
- **Swap**: Transpose two adjacent events

---

### 7. Visualize Petri Net (`viz_petri_net.py`)

**Purpose:** Visualize a Petri net from a PNML file and save as PNG.

**Usage:**
```bash
python viz_petri_net.py \
  --pnml-input <model.pnml> \
  --png-output <output.png>
```

**Example:**
```bash
python viz_petri_net.py \
  --pnml-input ./models/my_model.pnml \
  --png-output ./output/model_visualization.png
```

**Arguments:**
- `--pnml-input` (required): Path to input PNML Petri net model file
- `--png-output` (required): Path to output PNG visualization file

**Output:**
- PNG file with visual representation of the Petri net

---

## Complete Workflow Example

Here's a complete workflow from raw log to train/val/test splits:

```bash
# Step 1: Run token-based replay to compute fitness
python tbr_xes.py \
  --xes-input ./raw_data/original_log.xes \
  --pnml-model ./models/split_miner_model.pnml \
  --xes-output ./intermediate/log_with_tbr_fitness.xes

# Step 2: Compute initial fitness distribution
python fitness_stats.py \
  --xes-input ./intermediate/log_with_tbr_fitness.xes \
  --csv-output ./stats/initial_fitness_distribution.csv

# Step 3: Inject noise to rebalance distribution
python noise_injection.py \
  --xes-input ./intermediate/log_with_tbr_fitness.xes \
  --pnml-model ./models/split_miner_model.pnml \
  --output-dir ./intermediate/noise_injection \
  --target-bin1 0.70 \
  --target-bin2 0.20 \
  --target-bin3 0.10

# Step 4: Verify new fitness distribution
python fitness_stats.py \
  --xes-input ./intermediate/noise_injection/balanced_noise_injected.xes \
  --csv-output ./stats/balanced_fitness_distribution.csv

# Step 5: Sample to create balanced dataset
python sample_dataset_balanced.py \
  --xes-input ./intermediate/noise_injection/balanced_noise_injected.xes \
  --output-dir ./processed_data/balanced \
  --bin1-count 300 \
  --bin2-count 100 \
  --bin3-count 100

# Step 6: Split into train/val/test
python split_dataset.py \
  --xes-input ./processed_data/balanced/final_balanced_dataset.xes \
  --output-dir ./processed_data/splits \
  --train-ratio 0.70 \
  --val-ratio 0.15 \
  --test-ratio 0.15

# Step 7: Visualize the model (optional)
python viz_petri_net.py \
  --pnml-input ./models/split_miner_model.pnml \
  --png-output ./visualizations/model.png
```

---

## Getting Help

Every script has built-in help available:

```bash
python <script_name>.py --help
```

Example:
```bash
python noise_injection.py --help
```

This displays all available arguments and their descriptions.

---
