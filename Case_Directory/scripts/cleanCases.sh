#!/bin/bash
#==============================================================
# Simple cleanCases.sh
# - Deletes case folders
# - Optional: delete logs + results
# - Works from anywhere
#==============================================================

set -e

# ---- Resolve paths ------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"

CASESDIR="$ROOT_DIR/cases"
LOGDIR="$ROOT_DIR/logs"
RESULTS="$ROOT_DIR/results"

FILTER_LABEL=""
CLEAN_ALL=false
CLEAN_RESULTS=false

# ---- Parse arguments ----------------------------------------
while [[ $# -gt 0 ]]; do
    case "$1" in
        --all)     CLEAN_ALL=true ;;
        --label)   FILTER_LABEL="$2"; shift ;;
        --results) CLEAN_RESULTS=true ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
    shift
done

# ---- Safety checks ------------------------------------------
[ ! -d "$CASESDIR" ] && { echo "No cases directory found."; exit 1; }

echo "Project root: $ROOT_DIR"
echo "----------------------------------"

# ---- Clean logic --------------------------------------------
if $CLEAN_ALL; then
    echo "Removing ALL cases..."
    rm -rf "$CASESDIR"
    mkdir -p "$CASESDIR"

elif [ -n "$FILTER_LABEL" ]; then
    TARGET="$CASESDIR/$FILTER_LABEL"

    if [ -d "$TARGET" ]; then
        echo "Removing case: $FILTER_LABEL"
        rm -rf "$TARGET"
    else
        echo "Case not found: $FILTER_LABEL"
    fi

else
    echo "Use --all or --label <name>"
    exit 1
fi

echo "Cleaning logs..."
rm -rf "$LOGDIR"
mkdir -p "$LOGDIR"

if $CLEAN_RESULTS; then
    echo "Cleaning results..."
    rm -rf "$RESULTS"
    mkdir -p "$RESULTS"
fi

echo "Done."