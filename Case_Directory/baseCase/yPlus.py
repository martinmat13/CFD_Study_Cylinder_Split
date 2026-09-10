#!/usr/bin/env python3
"""
============================================================================
OpenFOAM Cylinder y+ Live Convergence Monitor
============================================================================
Scans postProcessing outputs, filters for the cylinder patch, and plots 
either a static summary or a real-time updating live monitoring window.

Usage:
    python3 monitor_yplus.py                    # Static analysis & plot
    python3 monitor_yplus.py --live             # Live live-updating convergence loop
    python3 monitor_yplus.py --live --interval 2.0  # Refresh every 2 seconds
============================================================================
"""

import os
import sys
import glob
import time
import argparse
import pandas as pd
import matplotlib.pyplot as plt

# Styling configuration
plt.style.use('seaborn-v0_8-whitegrid' if 'seaborn-v0_8-whitegrid' in plt.style.available else 'default')

def find_yplus_files(case_dir):
    """Recursively search for yPlus data files in standard OpenFOAM structures."""
    search_pattern = os.path.join(case_dir, "postProcessing", "**", "yPlus.dat")
    files = glob.glob(search_pattern, recursive=True)
    if not files:
        search_pattern = os.path.join(case_dir, "postProcessing", "**", "*yPlus*", "*.dat")
        files = glob.glob(search_pattern, recursive=True)
    return files

def parse_cylinder_yplus_file(filepath):
    """Parses OpenFOAM yPlus dat file, filtering exclusively for the 'cylinder' patch."""
    data_rows = []
    if not os.path.exists(filepath):
        return pd.DataFrame(data_rows)
        
    with open(filepath, 'r') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            
            parts = line.split()
            if len(parts) >= 5:
                patch_name = parts[1]
                if patch_name.lower() == 'cylinder':
                    try:
                        data_rows.append({
                            'Time': float(parts[0]),
                            'Min': float(parts[2]),
                            'Max': float(parts[3]),
                            'Avg': float(parts[4])
                        })
                    except ValueError:
                        continue
    return pd.DataFrame(data_rows)

def load_all_cylinder_data(case_dir):
    files = find_yplus_files(case_dir)
    if not files:
        return pd.DataFrame(), None
    
    # Pick the most recently updated yPlus.dat file if multiple exist
    target_file = max(files, key=os.path.getmtime)
    df = parse_cylinder_yplus_file(target_file)
    return df.sort_values(by='Time').drop_duplicates(subset=['Time']), target_file

def run_live_monitor(case_dir, interval):
    """Continuously polls the yPlus log stream and refreshes the live plot."""
    print(f"\n🚀 Launching Live Cylinder y+ Monitor (Refresh interval: {interval}s)")
    print("   Press Ctrl+C in your terminal to exit live tracking.\n")
    
    plt.ion() # Turn on interactive matplotlib mode
    fig, ax = plt.subplots(figsize=(10, 5))
    
    try:
        while True:
            df, target_file = load_all_cylinder_data(case_dir)
            
            ax.clear()
            if not df.empty:
                color = '#1f77b4'
                ax.plot(df['Time'], df['Max'], label='Max $y^+$ (Peaks)', color=color, linestyle='--', alpha=0.8)
                ax.plot(df['Time'], df['Avg'], label='Average $y^+$', color=color, linewidth=2.5)
                ax.plot(df['Time'], df['Min'], label='Min $y^+$', color=color, linestyle=':', alpha=0.8)
                
                ax.axhspan(30, 100, color='green', alpha=0.08, label='Target Wall-Function Range [30 - 100]')
                ax.axhspan(0.1, 1.5, color='orange', alpha=0.08, label='Target Sublayer Zone [$y^+ \\approx 1$]')
                
                current_time = df['Time'].iloc[-1]
                current_avg = df['Avg'].iloc[-1]
                current_max = df['Max'].iloc[-1]
                ax.set_title(f'Live OpenFOAM Cylinder y+ Tracker | Latest Time: {current_time:.4f}s (Avg: {current_avg:.2f}, Max: {current_max:.2f})', fontsize=11, fontweight='bold')
                ax.legend(loc='upper right', frameon=True, fontsize=8)
            else:
                ax.set_title('Live OpenFOAM Cylinder y+ Tracker | Waiting for solver output data...', fontsize=11)
                
            ax.set_xlabel('Simulation Time [s]', fontsize=10, fontweight='bold')
            ax.set_ylabel('Cylinder Surface $y^+$', fontsize=10, fontweight='bold')
            ax.grid(True, linestyle='--', alpha=0.6)
            
            plt.draw()
            plt.pause(interval)
            
    except KeyboardInterrupt:
        print("\n\n✅ Live monitoring session terminated by user.")
        plt.ioff()

def main():
    parser = argparse.ArgumentParser(description="Monitor and analyze OpenFOAM cylinder wall y+ metrics.")
    parser.add_argument('--dir', type=str, default=os.getcwd(), help='Target OpenFOAM case directory')
    parser.add_argument('--live', action='store_true', help='Enable live-updating graphical tracking mode')
    parser.add_argument('--interval', type=float, default=1.5, help='Refresh interval in seconds for live mode')
    args = parser.parse_args()

    case_dir = os.path.abspath(args.dir)

    if args.live:
        run_live_monitor(case_dir, args.interval)
    else:
        files = find_yplus_files(case_dir)
        if not files:
            print(f"❌ ERROR: No yPlus data files found inside {case_dir}/postProcessing/")
            sys.exit(1)
            
        df, _ = load_all_cylinder_data(case_dir)
        if df.empty:
            print("❌ ERROR: Parsed cylinder data dataframe is empty.")
            sys.exit(1)
            
        print(f"\n📊 CYLINDER WALL Y+ SUMMARY REPORT")
        print(f"  • Final Time Step Monitored : {df['Time'].iloc[-1]:.5f} s")
        print(f"  • Final Average y+          : {df['Avg'].iloc[-1]:.4f}")
        print(f"  • Final Max y+              : {df['Max'].iloc[-1]:.4f}")
        
        # Static render plot
        fig, ax = plt.subplots(figsize=(9, 5))
        ax.plot(df['Time'], df['Max'], label='Max $y^+$', color='#1f77b4', linestyle='--', alpha=0.8)
        ax.plot(df['Time'], df['Avg'], label='Average $y^+$', color='#1f77b4', linewidth=2.5)
        ax.plot(df['Time'], df['Min'], label='Min $y^+$', color='#1f77b4', linestyle=':', alpha=0.8)
        ax.axhspan(30, 100, color='green', alpha=0.08, label='Target Wall-Function Range')
        ax.set_title('OpenFOAM Cylinder Wall $y^+$ Convergence Tracker', fontsize=12, fontweight='bold')
        ax.set_xlabel('Simulation Time [s]', fontweight='bold')
        ax.set_ylabel('Cylinder Surface $y^+$', fontweight='bold')
        ax.legend(loc='upper right', frameon=True, fontsize=9)
        ax.grid(True, linestyle='--', alpha=0.6)
        plt.tight_layout()
        plt.show()

if __name__ == "__main__":
    main()
