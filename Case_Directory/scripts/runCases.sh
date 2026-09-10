#!/bin/bash
#==============================================================
# runCases.sh
# Reads cases.csv, copies baseCase for each entry, updates the
# case parameters (physics + mesh), and runs the solver.
#==============================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"
BASEDIR="$ROOT_DIR/baseCase"
CASESFILE="$ROOT_DIR/cases.csv"
CASESDIR="$ROOT_DIR/cases"
LOGDIR="$ROOT_DIR/logs"

PARALLEL_JOBS=8
FILTER_LABEL=""

usage() {
    cat <<EOF
Usage: bash runCases.sh [options]

Options:
  --parallel N      Number of cores for decomposition/solver (default: 8)
  --label FILTER    Only run rows whose label contains FILTER
  -h, --help        Show this help message
EOF
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --parallel)
            PARALLEL_JOBS="$2"
            shift 2
            ;;
        --label)
            FILTER_LABEL="$2"
            shift 2
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            usage
            exit 1
            ;;
    esac
done

mkdir -p "$CASESDIR" "$LOGDIR"

if [ -z "${WM_PROJECT_DIR:-}" ]; then
    source /opt/openfoam10/etc/bashrc 2>/dev/null || true
fi

if [ ! -f "$CASESFILE" ]; then
    echo "ERROR: cases.csv not found at $CASESFILE"
    exit 1
fi

COMPLETED_CASES=()
FAILED_CASES=()

echo "Running CFD campaign..."
echo "----------------------------------"

mapfile -t CSV_LINES < <(tail -n +2 "$CASESFILE")
echo "Total cases to process: ${#CSV_LINES[@]}"

for csv_line in "${CSV_LINES[@]}"; do
    [[ -z "$csv_line" ]] && continue

    # Parse the independent geometry and physics variables; derived values are computed in geometryProperties
    IFS=',' read -r Re state solver ddT U endTime dt maxCo D N_bl E R_prism_mult E_far N_c N_z label <<< "$csv_line"

    # Strip carriage returns (\r) from all parsed variables safely
    for var in Re state solver ddT U endTime dt maxCo D N_bl E R_prism_mult E_far N_c N_z label; do
        declare "$var=${!var//$'\r'/}"
    done

    if [[ -z "$label" || -z "$solver" ]]; then
        echo "Skipping bad row: $csv_line"
        continue
    fi

    if [[ -n "$FILTER_LABEL" && "$label" != *"$FILTER_LABEL"* ]]; then
        continue
    fi

    CASEDIR="$CASESDIR/$label"
    LOGFILE="$LOGDIR/$label.log"

    if [ -d "$CASEDIR" ]; then
        echo "=========================================="
        echo "Skipping existing case: $label"
        echo "=========================================="
        continue
    fi

    echo "=========================================="
    echo "Case: $label | Re=$Re | D=$D | Mesh: ${N_bl}x${N_c}"
    echo "=========================================="

    cp -r "$BASEDIR" "$CASEDIR" || { echo "ERROR: Failed to copy baseCase"; FAILED_CASES+=("$label (copy)"); continue; }

    echo "START CASE: $label" | tee -a "$LOGFILE"
    echo "Mesh Parameters: D=$D, N_bl=$N_bl, E=$E, R_prism_mult=$R_prism_mult, E_far=$E_far, N_c=$N_c, N_z=$N_z" | tee -a "$LOGFILE"

    # --- 1. Update Velocity Fields ---
    sed -i "s|INLET_U|$U|g" "$CASEDIR/0/U" || { echo "ERROR: Failed to update 0/U"; FAILED_CASES+=("$label (0/U)"); continue; }
    if [ -f "$CASEDIR/0/include/turbulenceInit" ]; then
        sed -i "s|Uinlet.*INLET_U;|Uinlet          $U;|g" "$CASEDIR/0/include/turbulenceInit"
        echo "  ✓ Updated turbulenceInit with Uinlet=$U" | tee -a "$LOGFILE"
    fi

    # --- 2. Update ControlDict ---
    sed -i "s|INLET_U|$U|g" "$CASEDIR/system/controlDict" || { echo "ERROR: Failed to update controlDict"; FAILED_CASES+=("$label (controlDict)"); continue; }
    sed -i "s|^application.*|application     $solver;|" "$CASEDIR/system/controlDict" || true
    sed -i "s|^endTime.*|endTime         $endTime;|" "$CASEDIR/system/controlDict" || true
    sed -i "s|^deltaT.*|deltaT          $dt;|" "$CASEDIR/system/controlDict" || true
    sed -i "s|^maxCo.*|maxCo           $maxCo;|" "$CASEDIR/system/controlDict" || true
    echo "  ✓ Updated controlDict: solver=$solver, endTime=$endTime, deltaT=$dt, maxCo=$maxCo" | tee -a "$LOGFILE"

    # --- 3. Update Geometry Properties (Mesh) ---
    GEOM="$CASEDIR/system/geometryProperties"
    if [ -f "$GEOM" ]; then
        # Smart replacement function: looks for "Parameter <spaces> Value;" and replaces Value
        update_dict() {
            local param=$1
            local val=$2
            local file=$3
            sed -i -E "s/^([[:space:]]*${param}[[:space:]]+)[^;]+;/\1${val};/g" "$file"
        }
        
        update_dict "D" "$D" "$GEOM"
        update_dict "N_bl" "$N_bl" "$GEOM"
        update_dict "E" "$E" "$GEOM"
        update_dict "R_prism_mult" "$R_prism_mult" "$GEOM"
        update_dict "E_far" "$E_far" "$GEOM"
        update_dict "N_c" "$N_c" "$GEOM"
        update_dict "N_z" "$N_z" "$GEOM"
        
        echo "  ✓ Updated geometryProperties" | tee -a "$LOGFILE"
    else
        echo "  ⚠ geometryProperties missing" | tee -a "$LOGFILE"
    fi

    # --- 4. Update Time Schemes ---
    if [ "$state" = "steady" ]; then
        sed -i '/ddtSchemes/,/}/c\
ddtSchemes\n\
{\n\
    default steadyState;\n\
}' "$CASEDIR/system/fvSchemes" || true
    else
        sed -i "/ddtSchemes/,/}/c\
ddtSchemes\n\
{\n\
    default $ddT;\n\
}" "$CASEDIR/system/fvSchemes" || true
    fi

    # --- 5. Meshing & Execution ---
    echo "blockMesh..." | tee -a "$LOGFILE"
    if ! (cd "$CASEDIR" && blockMesh >>"$LOGFILE" 2>&1); then
        echo "  ✗ blockMesh failed" | tee -a "$LOGFILE"
        FAILED_CASES+=("$label (blockMesh)")
        continue
    fi
    echo "  ✓ blockMesh completed" | tee -a "$LOGFILE"

    echo "Decomposing domain for $PARALLEL_JOBS cores..." | tee -a "$LOGFILE"
    if ! (cd "$CASEDIR" && decomposePar -force >>"$LOGFILE" 2>&1); then
        echo "  ✗ Decomposition failed" | tee -a "$LOGFILE"
        FAILED_CASES+=("$label (decomposition)")
        continue
    fi
    echo "  ✓ Decomposition completed" | tee -a "$LOGFILE"

    echo "Running $solver in parallel ($PARALLEL_JOBS cores)..." | tee -a "$LOGFILE"
    SOLVER_EXIT=0
    (cd "$CASEDIR" && mpirun -np "$PARALLEL_JOBS" "$solver" -parallel >>"$LOGFILE" 2>&1) || SOLVER_EXIT=$?

    if [ "$SOLVER_EXIT" -eq 0 ]; then
        echo "  ✓ Solver completed successfully" | tee -a "$LOGFILE"

        echo "Reconstructing results..." | tee -a "$LOGFILE"
        RECON_EXIT=0
        (cd "$CASEDIR" && reconstructPar >>"$LOGFILE" 2>&1) || RECON_EXIT=$?

        if [ "$RECON_EXIT" -eq 0 ]; then
            echo "  ✓ Reconstruction completed" | tee -a "$LOGFILE"
            rm -rf "$CASEDIR"/processor*
            COMPLETED_CASES+=("$label")
        else
            echo "  ⚠ Reconstruction failed (exit code: $RECON_EXIT)" | tee -a "$LOGFILE"
            FAILED_CASES+=("$label (reconstruction)")
        fi
    else
        echo "  ✗ Solver failed (exit code: $SOLVER_EXIT)" | tee -a "$LOGFILE"
        FAILED_CASES+=("$label (solver)")
    fi

    echo "DONE: $label" | tee -a "$LOGFILE"
done

echo ""
echo "=========================================="
echo "CAMPAIGN SUMMARY"
echo "=========================================="

if [ ${#COMPLETED_CASES[@]} -gt 0 ]; then
    echo "✓ COMPLETED (${#COMPLETED_CASES[@]}):"
    for case in "${COMPLETED_CASES[@]}"; do
        echo "  ✓ $case"
    done
fi

if [ ${#FAILED_CASES[@]} -gt 0 ]; then
    echo ""
    echo "✗ FAILED (${#FAILED_CASES[@]}):"
    for case in "${FAILED_CASES[@]}"; do
        echo "  ✗ $case"
    done
fi

echo ""
echo "TOTAL: Completed=${#COMPLETED_CASES[@]}, Failed=${#FAILED_CASES[@]}"
echo "=========================================="