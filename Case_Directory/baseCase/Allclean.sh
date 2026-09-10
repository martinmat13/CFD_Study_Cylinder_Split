#!/bin/bash

#==============================================================================
# Cylinder CFD Case Clean Script
# Removes simulation artifacts, temporary files, and old results
# Usage: ./Allclean.sh [OPTIONS]
# Options:
#   --full        Clean everything including postProcessing
#   --mesh        Only remove mesh (polyMesh, processor*, etc)
#   --results     Only remove time directories and postProcessing
#   --logs        Only remove log files
#   --backup      Backup postProcessing before deletion
#   --dry-run     Preview what would be deleted without removing
#   --help        Show this help message
#==============================================================================

# Color codes for terminal output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Default options
CLEAN_FULL=true
CLEAN_MESH=true
CLEAN_RESULTS=true
CLEAN_LOGS=true
DRY_RUN=false
BACKUP=false

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --full)
            CLEAN_FULL=true
            CLEAN_MESH=true
            CLEAN_RESULTS=true
            CLEAN_LOGS=true
            shift
            ;;
        --mesh)
            CLEAN_FULL=false
            CLEAN_MESH=true
            CLEAN_RESULTS=false
            CLEAN_LOGS=false
            shift
            ;;
        --results)
            CLEAN_FULL=false
            CLEAN_MESH=false
            CLEAN_RESULTS=true
            CLEAN_LOGS=false
            shift
            ;;
        --logs)
            CLEAN_FULL=false
            CLEAN_MESH=false
            CLEAN_RESULTS=false
            CLEAN_LOGS=true
            shift
            ;;
        --backup)
            BACKUP=true
            shift
            ;;
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        --help)
            grep "^#" "$0" | grep -E "^# |^#$" | sed 's/^# //'
            exit 0
            ;;
        *)
            echo -e "${RED}Unknown option: $1${NC}"
            echo "Use --help for usage information"
            exit 1
            ;;
    esac
done

# Display mode
MODE="FULL CLEAN"
if [ "$CLEAN_MESH" = true ] && [ "$CLEAN_RESULTS" = false ]; then
    MODE="MESH ONLY"
elif [ "$CLEAN_MESH" = false ] && [ "$CLEAN_RESULTS" = true ]; then
    MODE="RESULTS ONLY"
elif [ "$CLEAN_LOGS" = true ] && [ "$CLEAN_MESH" = false ] && [ "$CLEAN_RESULTS" = false ]; then
    MODE="LOGS ONLY"
fi

if [ "$DRY_RUN" = true ]; then
    MODE="DRY-RUN: $MODE"
fi

echo -e "${BLUE}=====================================${NC}"
echo -e "${BLUE}OpenFOAM Case Cleaner${NC}"
echo -e "${BLUE}=====================================${NC}"
echo -e "Mode:     ${YELLOW}$MODE${NC}"
echo -e "Location: ${YELLOW}$(pwd)${NC}"
echo -e "${BLUE}=====================================${NC}"

# Track deleted sizes
DELETED_SIZE=0

# Helper function to get file size
get_size() {
    if [ -d "$1" ]; then
        du -sh "$1" 2>/dev/null | cut -f1
    elif [ -f "$1" ]; then
        ls -lh "$1" | awk '{print $5}'
    fi
}

# Helper function to report deletion
report_delete() {
    local target=$1
    local desc=$2
    if [ "$DRY_RUN" = false ]; then
        SIZE=$(get_size "$target")
        echo -e "  ${GREEN}✓${NC} $desc ${YELLOW}($SIZE)${NC}"
    else
        echo -e "  ${YELLOW}※${NC} $desc (would be deleted)"
    fi
}

# ============================================================================
# 1️⃣ BACKUP postProcessing if requested
# ============================================================================
if [ "$BACKUP" = true ] && [ -d "postProcessing" ]; then
    echo -e "\n${BLUE}[1/5]${NC} Backing up postProcessing..."
    BACKUP_DIR="postProcessing_backup_$(date +%Y%m%d_%H%M%S)"
    if [ "$DRY_RUN" = false ]; then
        cp -r postProcessing "$BACKUP_DIR"
        echo -e "  ${GREEN}✓${NC} Backed up to: ${YELLOW}$BACKUP_DIR${NC}"
    else
        echo -e "  ${YELLOW}※${NC} Would backup to: $BACKUP_DIR"
    fi
fi

# ============================================================================
# 2️⃣ Remove Windows Zone.Identifier files
# ============================================================================
ZONE_FILES=$(find . -name "*Zone.Identifier*" -type f 2>/dev/null | wc -l)
if [ $ZONE_FILES -gt 0 ]; then
    echo -e "\n${BLUE}[2/5]${NC} Removing Zone.Identifier files..."
    if [ "$DRY_RUN" = false ]; then
        find . -name "*Zone.Identifier*" -type f -delete
        echo -e "  ${GREEN}✓${NC} Removed $ZONE_FILES Zone.Identifier files"
    else
        echo -e "  ${YELLOW}※${NC} Would remove $ZONE_FILES Zone.Identifier files"
    fi
fi

# ============================================================================
# 3️⃣ Remove mesh-related files
# ============================================================================
if [ "$CLEAN_MESH" = true ]; then
    echo -e "\n${BLUE}[3/5]${NC} Cleaning mesh artifacts..."
    
    # polyMesh
    if [ -d "constant/polyMesh" ]; then
        if [ "$DRY_RUN" = false ]; then
            rm -rf constant/polyMesh
            report_delete "constant/polyMesh" "Removed polyMesh"
        else
            SIZE=$(get_size "constant/polyMesh")
            echo -e "  ${YELLOW}※${NC} polyMesh ${YELLOW}($SIZE)${NC}"
        fi
    fi
    
    # dynamicCode
    if [ -d "dynamicCode" ]; then
        if [ "$DRY_RUN" = false ]; then
            rm -rf dynamicCode
            report_delete "dynamicCode" "Removed dynamicCode"
        else
            SIZE=$(get_size "dynamicCode")
            echo -e "  ${YELLOW}※${NC} dynamicCode ${YELLOW}($SIZE)${NC}"
        fi
    fi
    
    # Processor folders (parallel runs)
    PROC_COUNT=$(ls -d processor* 2>/dev/null | wc -l)
    if [ $PROC_COUNT -gt 0 ]; then
        if [ "$DRY_RUN" = false ]; then
            rm -rf processor*
            echo -e "  ${GREEN}✓${NC} Removed $PROC_COUNT processor directories"
        else
            echo -e "  ${YELLOW}※${NC} Would remove $PROC_COUNT processor directories"
        fi
    fi
fi

# ============================================================================
# 4️⃣ Remove time directories and results
# ============================================================================
if [ "$CLEAN_RESULTS" = true ]; then
    echo -e "\n${BLUE}[4/5]${NC} Cleaning simulation results..."
    
    # Time directories (except 0/)
    TIME_DIRS=$(find . -maxdepth 1 -type d -regex './[0-9.]+$' ! -name "0" 2>/dev/null | wc -l)
    if [ $TIME_DIRS -gt 0 ]; then
        if [ "$DRY_RUN" = false ]; then
            find . -maxdepth 1 -type d -regex './[0-9.]+$' ! -name "0" -exec rm -rf {} + 2>/dev/null
            echo -e "  ${GREEN}✓${NC} Removed $TIME_DIRS time directories"
        else
            echo -e "  ${YELLOW}※${NC} Would remove $TIME_DIRS time directories"
        fi
    fi
    
    # postProcessing
    if [ -d "postProcessing" ]; then
        if [ "$DRY_RUN" = false ]; then
            rm -rf postProcessing
            report_delete "postProcessing" "Removed postProcessing"
        else
            SIZE=$(get_size "postProcessing")
            echo -e "  ${YELLOW}※${NC} postProcessing ${YELLOW}($SIZE)${NC}"
        fi
    fi
fi

# ============================================================================
# 5️⃣ Remove log files
# ============================================================================
if [ "$CLEAN_LOGS" = true ]; then
    echo -e "\n${BLUE}[5/5]${NC} Cleaning log files..."
    
    LOG_FILES=$(find . -maxdepth 1 -name "log.*" -type f 2>/dev/null | wc -l)
    if [ $LOG_FILES -gt 0 ]; then
        if [ "$DRY_RUN" = false ]; then
            find . -maxdepth 1 -name "log.*" -type f -delete
            echo -e "  ${GREEN}✓${NC} Removed $LOG_FILES log files"
        else
            echo -e "  ${YELLOW}※${NC} Would remove $LOG_FILES log files"
        fi
    fi
    
    # Convergence plot files
    PLOT_FILES=0
    for plotfile in convergence_*.png result*.foam mesh*.foam; do
        if [ -f "$plotfile" ]; then
            PLOT_FILES=$((PLOT_FILES + 1))
            if [ "$DRY_RUN" = false ]; then
                rm -f "$plotfile"
            fi
        fi
    done
    if [ $PLOT_FILES -gt 0 ]; then
        if [ "$DRY_RUN" = false ]; then
            echo -e "  ${GREEN}✓${NC} Removed $PLOT_FILES convergence/result files"
        else
            echo -e "  ${YELLOW}※${NC} Would remove $PLOT_FILES convergence/result files"
        fi
    fi
fi

# ============================================================================
# Summary
# ============================================================================
echo -e "\n${BLUE}=====================================${NC}"
if [ "$DRY_RUN" = true ]; then
    echo -e "${YELLOW}DRY-RUN COMPLETE${NC}"
    echo "No files were actually deleted."
    echo "Re-run without --dry-run to apply changes."
else
    echo -e "${GREEN}Case Cleaned Successfully! ✅${NC}"
fi
echo -e "${BLUE}=====================================${NC}\n"

exit 0