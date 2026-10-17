# OpenFOAM Automated Cylinder Flow Framework

This repository contains a fully automated, parameterized framework for simulating incompressible flow past a circular cylinder using OpenFOAM. It features a bespoke block-structured meshing topology (double O-grid) and a set of shell/Python scripts to handle large parametric sweeps, automated execution, and post-processing without manual case intervention.

This work was developed as part of a research internship at the University of Split, Faculty of Maritime Studies.

## Features

* **Fully Parameterized Meshing:** The entire domain is built analytically in `blockMesh`. Geometric and grading quantities are derived from a small set of control parameters (e.g., diameter, expansion ratios, cell counts).

* **Double O-Grid Topology:** Ensures high-quality orthogonal cells near the viscous sublayer, transitioning smoothly into a far-field H-grid.

* **Automated Campaign Execution:** Drive hundreds of simulations from a single `cases.csv` file using template-copy instantiation.

* **Fault-Tolerant Pipeline:** Each case runs independently with detailed logging, allowing you to resume interrupted campaigns easily.

* **Automated Post-Processing:** Python scripts automatically extract drag/lift coefficients, Strouhal numbers, $y^+$ values, and generate comparative plots.

## Repository Structure

```
.
├── baseCase/                  # Template OpenFOAM case (never modified in place)
│   ├── 0/                     # Initial conditions (U, p, k, epsilon, omega, etc.)
│   ├── constant/              # transportProperties, turbulenceProperties
│   └── system/                # blockMeshDict, controlDict, fvSchemes, fvSolution
├── cases.csv                  # Tabular configuration for the simulation campaign
├── cases/                     # Directory where generated cases are instantiated
├── logs/                      # Execution logs for each case
├── scripts/                   # Utility scripts (runCases.sh, cleanCases.sh, etc.)
├── global_analysis/           # Output directory for aggregated plots and CSV summaries
└── README.md

```

## Prerequisites

* **OpenFOAM:** (Developed/tested on OpenFOAM v10 / v2312)
* **Python 3:** Required for post-processing (`pandas`, `numpy`, `scipy`, `matplotlib`)

## Usage

### 1. Configure the Campaign

Define your parametric sweep in `cases.csv`. The script reads the following columns to inject parameters directly into the OpenFOAM dictionaries:

| Re | state | solver | ddT | U | endTime | dt | maxCo | D | N_bl | E | R_prism_mult | E_far | N_c | N_z | label |

### 2. Run the Simulations

Use the `runCases.sh` script to parse the CSV, generate the meshes, and execute the solvers.

```bash
# Run all cases in cases.csv with default 8 cores
./runCases.sh

# Run with a specific number of cores
./runCases.sh --parallel 4

# Run only a specific case by matching a label
./runCases.sh --label case_Re500000
```

*Note: The script automatically skips cases that have already been generated.*

### 3. Post-Processing

Extract force coefficients, Strouhal numbers, and generate plots using the Python script.

```bash
python3 postProcess.py
```

*Outputs will be saved in individual `postProcessing/analysis/` folders within each case, and aggregated results will be placed in `global_analysis/`.*

### 4. Visualization

To quickly view the results in ParaView, generate the `.foam` marker files:

```bash
./touch_foam.sh
```

### 5. Cleanup

To remove generated cases, logs, or results, use `cleanCases.sh`.

```bash
# Remove a specific case
./cleanCases.sh --label case_Re100000

# Remove ALL generated cases and logs
./cleanCases.sh --all

# Remove results data as well
./cleanCases.sh --all --results
```

## Modeling Regimes Supported

* **Laminar Flow:** Validated at low Reynolds numbers (e.g., $Re=100$, $Re=200$).
* **Turbulent RANS:** Includes configurations for standard $k-\epsilon$ and $k-\omega$ SST models. (Note: standard 2D assumptions may over-predict coherence at high Re).
