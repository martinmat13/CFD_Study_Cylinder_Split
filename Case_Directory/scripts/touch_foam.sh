#!/bin/bash
# ============================================================
# create_foam_files.sh
# Navigate to each case folder and create <folder_name>.foam
# ============================================================

# Path to the parent cases folder
CASES_DIR="../cases"

# Loop over all Re* case directories
for d in "$CASES_DIR"/Re*; do
    # Make sure it's a directory
    if [ -d "$d" ]; then
        # Get the folder name only (for .foam file)
        CASE_NAME=$(basename "$d")

        # Navigate to the folder
        cd "$d" || { echo "Failed to enter $d"; continue; }

        # Create the .foam file
        touch "${CASE_NAME}.foam"
        echo "Created ${CASE_NAME}.foam in $d"

        # Go back to scripts folder
        cd - > /dev/null
    fi
done

echo "All .foam files created for all cases!"