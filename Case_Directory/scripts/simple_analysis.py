#!/usr/bin/env python3
"""
Enhanced CFD Analysis Script - Case Comparison with Grid & Time Convergence
Extracts force data, cell counts, timing info, and generates organized plots
with separate grid convergence and time step convergence analyses.

Plots organized by category:
  - Individual Cases: Cd/Cl time series per case
  - Collective: All cases comparison
  - Grid Convergence: Mesh refinement effects (varying Nx/Ny with constant dt)
  - Time Convergence: Time step effects (varying dt with constant mesh)
  - Performance: CPU timing and scalability
  - Validation: Phase space and statistical distributions
"""

import os
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from pathlib import Path
import subprocess
from datetime import datetime

# ========================================================================
# CONFIGURATION & SETUP
# ========================================================================
PROJECT_ROOT = Path("/home/martin8991/OpenFOAM_cases/Cylinder_CFD_Project/3D_Cases/02_HighRe_Turb_kOmegaSST_3D_D0.1m_prismLayers")
CASES_DIR = PROJECT_ROOT / "cases"
RESULTS_DIR = PROJECT_ROOT / "results"
PLOTS_DIR = RESULTS_DIR / "plots"
LOGS_DIR = PROJECT_ROOT / "logs"

PLOTS_DIR.mkdir(parents=True, exist_ok=True)

# Plot style configuration
plt.rcParams.update({
    'figure.dpi': 150,
    'font.size': 10,
    'axes.labelsize': 11,
    'axes.titlesize': 12,
    'legend.fontsize': 9,
    'xtick.labelsize': 10,
    'ytick.labelsize': 10,
    'grid.alpha': 0.3,
    'grid.linestyle': '--',
    'lines.linewidth': 2,
    'lines.markersize': 7,
})

# Read case CSV
cases_df = pd.read_csv(PROJECT_ROOT / "cases.csv")

print("\n" + "="*80)
print("█ ENHANCED CFD ANALYSIS - GRID & TIME CONVERGENCE STUDIES".ljust(80))
print("="*80)
print(f"  Total Cases: {len(cases_df)}")
print(f"  Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print("="*80)

# ========================================================================
# 1. EXTRACT MESH INFORMATION & IDENTIFY CONVERGENCE TYPES
# ========================================================================
print("\n[STEP 1/7] 📊 Extracting mesh information & case classification...")

mesh_data = []
grid_convergence_cases = {}  # Cases grouped by mesh refinement (same dt)
time_convergence_cases = {}  # Cases grouped by time step (same mesh)

cases_df = cases_df.dropna(subset=['label'])
cases_df['label'] = cases_df['label'].astype(str)

for _, row in cases_df.iterrows():
    case_label = row['label']

    if pd.isna(case_label):
        continue

    case_dir = CASES_DIR / str(case_label)
    
    try:
        result = subprocess.run(
            ['checkMesh', '-time', '0'],
            cwd=str(case_dir),
            capture_output=True,
            text=True,
            timeout=30
        )
        
        output = result.stdout + result.stderr
        cells = None
        
        for line in output.split('\n'):
            if 'cells' in line.lower():
                try:
                    parts = line.split()
                    for i, part in enumerate(parts):
                        if 'cells' in part.lower():
                            cells = int(parts[i-1])
                            break
                except:
                    pass
        
        if cells is None:
            cells = row['Nx'] * row['Ny']
        
    except Exception as e:
        cells = row['Nx'] * row['Ny']
    
    mesh_data.append({
        'label': case_label,
        'Nx': row['Nx'],
        'Ny': row['Ny'],
        'dt': row.get('dt', None),
        'Cells': cells
    })
    
    # Classify for convergence studies
    dt_key = row.get('dt', 'unknown')
    mesh_key = (row['Nx'], row['Ny'])
    
    if dt_key not in grid_convergence_cases:
        grid_convergence_cases[dt_key] = []
    grid_convergence_cases[dt_key].append((case_label, mesh_key, cells))
    
    if mesh_key not in time_convergence_cases:
        time_convergence_cases[mesh_key] = []
    time_convergence_cases[mesh_key].append((case_label, dt_key, cells))
    
    print(
    f"  ✓ {str(case_label)}: "
    f"{int(cells):>6d} cells | "
    f"Nx={int(row['Nx']):>3d} "
    f"Ny={int(row['Ny']):>3d} | "
    f"dt={dt_key}"
    )
mesh_df = pd.DataFrame(mesh_data)
print(f"\n  Grid Convergence groups (by dt): {len(grid_convergence_cases)} groups")
print(f"  Time Convergence groups (by mesh): {len(time_convergence_cases)} groups")

# ========================================================================
# 2. EXTRACT TIMING & PERFORMANCE INFORMATION
# ========================================================================
print("\n[STEP 2/7] ⏱️  Extracting timing information...")

timing_data = []

for _, row in cases_df.iterrows():
    case_label = row['label']
    log_file = LOGS_DIR / f"{case_label}.log"
    
    clock_time = None
    exec_time = None
    
    if log_file.exists():
        with open(log_file, 'r') as f:
            log_content = f.read()
        
        for line in log_content.split('\n'):
            if 'ExecutionTime' in line and 'ClockTime' in line:
                try:
                    parts = line.split('=')
                    if len(parts) >= 2:
                        exec_str = parts[1].split('s')[0].strip()
                        exec_time = float(exec_str)
                    if len(parts) >= 3:
                        clock_str = parts[2].split('s')[0].strip()
                        clock_time = float(clock_str)
                except:
                    pass
    
    # Count timesteps from force file
    force_file = CASES_DIR / case_label / "postProcessing" / "forceCoeffs" / "0" / "coefficient.dat"
    timesteps = 0
    if force_file.exists():
        with open(force_file, 'r') as f:
            for line in f:
                if not line.startswith('#'):
                    timesteps += 1
    
    time_per_step = None
    if exec_time and timesteps:
        time_per_step = (exec_time / timesteps) * 1000
    
    status = "✓" if exec_time else "⚠"
    print(f"  {status} {case_label}: ExecTime={exec_time:.1f}s | ClockTime={clock_time:.1f}s | Steps={timesteps}")
    
    timing_data.append({
        'label': case_label,
        'Clock_Time_s': clock_time,
        'Exec_Time_s': exec_time,
        'Timesteps': timesteps,
        'Time_Per_Step_ms': time_per_step
    })

timing_df = pd.DataFrame(timing_data)

# ========================================================================
# 3. EXTRACT FORCE COEFFICIENTS
# ========================================================================
print("\n[STEP 3/7] 📉 Extracting force coefficients...")

force_data = {}

for _, row in cases_df.iterrows():
    case_label = row['label']
    coeff_file = CASES_DIR / case_label / "postProcessing" / "forceCoeffs" / "0" / "coefficient.dat"
    
    if not coeff_file.exists():
        print(f"  ⚠ {case_label}: coefficient.dat not found")
        continue
    
    df = pd.read_csv(coeff_file, sep=r'\s+', comment='#', header=None)
    
    cols = ['Time', 'Cd', 'Cd_f', 'Cd_r', 'Cl', 'Cl_f', 'Cl_r',
            'CmPitch', 'CmRoll', 'CmYaw', 'Cs', 'Cs_f', 'Cs_r']
    df.columns = cols[:len(df.columns)]
    
    force_data[case_label] = df
    print(f"  ✓ {case_label}: {len(df):>4d} timesteps")

# ========================================================================
# 4. COMPUTE STATISTICS & CONVERGENCE METRICS
# ========================================================================
print("\n[STEP 4/7] 📈 Computing statistics...")

stats_data = []

for case_label, df in force_data.items():
    skip = int(len(df) * 0.4)
    steady = df.iloc[skip:]
    
    stats_data.append({
        'label': case_label,
        'Cd_mean': steady['Cd'].mean(),
        'Cd_std': steady['Cd'].std(),
        'Cl_rms': np.sqrt(np.mean(steady['Cl']**2)),
        'Cl_mean': steady['Cl'].mean(),
        'Cs_mean': steady['Cs'].mean()
    })

stats_df = pd.DataFrame(stats_data)

# Merge all data - start with cases_df to preserve all columns including dt
merged_df = cases_df[['label', 'dt']].copy() if 'dt' in cases_df.columns else cases_df[['label']].copy()
merged_df = merged_df.merge(mesh_df, left_on='label', right_on='label', how='left')
merged_df = merged_df.merge(timing_df, left_on='label', right_on='label', how='left')
merged_df = merged_df.merge(stats_df, left_on='label', right_on='label', how='left')

print("  Data merged successfully")
print(f"  Total records: {len(merged_df)}")

# ========================================================================
# 5. SAVE SUMMARY CSV
# ========================================================================
print("\n[STEP 5/7] 💾 Saving summary data...")

summary_csv = RESULTS_DIR / "summary_comparison.csv"
merged_df.to_csv(summary_csv, index=False)
print(f"  ✓ Saved: {summary_csv}")

# Display summary with safe column selection
display_cols = ['label', 'Cells', 'Exec_Time_s', 'Cd_mean', 'Cl_rms']
if 'dt' in merged_df.columns:
    display_cols.insert(2, 'dt')

print("\n" + merged_df[display_cols].to_string(index=False))

# ========================================================================
# 6. GENERATE ORGANIZED PLOTS
# ========================================================================
print("\n[STEP 6/7] 📊 Generating plots...")
print("  ┌─ Individual Case Plots")
print("  ├─ Collective Comparison Plots")
print("  ├─ Grid Convergence Analysis")
print("  ├─ Time Convergence Analysis")
print("  ├─ Performance & Scalability")
print("  └─ Statistical Validation")

# --------  A. INDIVIDUAL CASE TIME SERIES --------
print("\n  [A] Individual Case Time Series...")

for case_label, df in force_data.items():
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8))
    
    ax1.plot(df['Time'], df['Cd'], linewidth=2, color='#1f77b4', label='Cd')
    ax1.fill_between(df['Time'], df['Cd'].min(), df['Cd'].max(), alpha=0.1, color='#1f77b4')
    ax1.set_ylabel('Drag Coefficient ($C_d$)', fontsize=11, fontweight='bold')
    ax1.set_title(f'Drag Coefficient Time Series — {case_label}', fontsize=12, fontweight='bold')
    ax1.grid(True, alpha=0.3)
    ax1.legend(loc='upper right')
    
    ax2.plot(df['Time'], df['Cl'], linewidth=2, color='#ff7f0e', label='Cl')
    ax2.fill_between(df['Time'], df['Cl'].min(), df['Cl'].max(), alpha=0.1, color='#ff7f0e')
    ax2.set_xlabel('Time (s)', fontsize=11, fontweight='bold')
    ax2.set_ylabel('Lift Coefficient ($C_l$)', fontsize=11, fontweight='bold')
    ax2.set_title(f'Lift Coefficient Time Series — {case_label}', fontsize=12, fontweight='bold')
    ax2.grid(True, alpha=0.3)
    ax2.legend(loc='upper right')
    
    fig.tight_layout()
    fig_name = PLOTS_DIR / f"01_TimeSeries_{case_label}.png"
    fig.savefig(fig_name, dpi=150, bbox_inches='tight')
    plt.close(fig)

print("    ✓ Individual time series saved")

# --------  B. COLLECTIVE COMPARISON --------
print("\n  [B] Collective Comparison Plots...")

# Combined Cd plot
fig, ax = plt.subplots(figsize=(13, 6))
colors = plt.cm.tab20(np.linspace(0, 1, len(force_data)))
for (case_label, df), color in zip(force_data.items(), colors):
    ax.plot(df['Time'], df['Cd'], linewidth=1.8, label=case_label, color=color, alpha=0.85)
ax.set_xlabel('Time (s)', fontsize=11, fontweight='bold')
ax.set_ylabel('Drag Coefficient ($C_d$)', fontsize=11, fontweight='bold')
ax.set_title('Drag Coefficient Comparison — All Cases', fontsize=12, fontweight='bold')
ax.legend(fontsize=8, loc='best', ncol=2)
ax.grid(True, alpha=0.3)
fig.tight_layout()
fig.savefig(PLOTS_DIR / "02_Cd_AllCases_Comparison.png", dpi=150, bbox_inches='tight')
plt.close(fig)

# Combined Cl plot
fig, ax = plt.subplots(figsize=(13, 6))
for (case_label, df), color in zip(force_data.items(), colors):
    ax.plot(df['Time'], df['Cl'], linewidth=1.8, label=case_label, color=color, alpha=0.85)
ax.set_xlabel('Time (s)', fontsize=11, fontweight='bold')
ax.set_ylabel('Lift Coefficient ($C_l$)', fontsize=11, fontweight='bold')
ax.set_title('Lift Coefficient Comparison — All Cases', fontsize=12, fontweight='bold')
ax.legend(fontsize=8, loc='best', ncol=2)
ax.grid(True, alpha=0.3)
fig.tight_layout()
fig.savefig(PLOTS_DIR / "03_Cl_AllCases_Comparison.png", dpi=150, bbox_inches='tight')
plt.close(fig)

print("    ✓ Collective comparison plots saved")

# --------  C. GRID CONVERGENCE ANALYSIS --------
print("\n  [C] Grid Convergence Analysis (varying mesh with constant dt)...")

for dt_key, cases_in_group in grid_convergence_cases.items():
    if len(cases_in_group) < 2:
        continue
    
    # Extract cases and sort by cell count
    grid_cases = sorted(cases_in_group, key=lambda x: x[2])
    labels = [x[0] for x in grid_cases]
    cells_list = [x[2] for x in grid_cases]
    
    # Get metrics for each case
    cd_means = []
    cd_stds = []
    cl_rms_list = []
    for label in labels:
        row = merged_df[merged_df['label'] == label].iloc[0] if label in merged_df['label'].values else None
        if row is not None:
            cd_means.append(row['Cd_mean'])
            cd_stds.append(row['Cd_std'])
            cl_rms_list.append(row['Cl_rms'])
        else:
            cd_means.append(np.nan)
            cd_stds.append(np.nan)
            cl_rms_list.append(np.nan)
    
    # Plot: Cd vs Mesh Size
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(15, 6))
    
    # Subplot 1: Cd convergence
    ax1.errorbar(cells_list, cd_means, yerr=cd_stds, fmt='o-', linewidth=2.5, 
                 markersize=10, capsize=5, capthick=2, color='#1f77b4', label='$C_d$ ± std')
    ax1.set_xlabel('Number of Cells', fontsize=11, fontweight='bold')
    ax1.set_ylabel('Mean Drag Coefficient ($C_d$)', fontsize=11, fontweight='bold')
    ax1.set_title(f'Grid Convergence Study (dt={dt_key}): Drag Coefficient', fontsize=12, fontweight='bold')
    ax1.set_xscale('log')
    ax1.grid(True, alpha=0.3, which='both')
    ax1.legend(fontsize=10)
    
    # Use table legend instead of overlapping annotations
    table_text = "\n".join([f"{i+1}. {label}" for i, label in enumerate(labels)])
    ax1.text(0.98, 0.97, table_text, transform=ax1.transAxes, fontsize=7,
            verticalalignment='top', horizontalalignment='right',
            bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.7))
    
    # Add numbered markers on plot
    for i, (cells, cd_mean) in enumerate(zip(cells_list, cd_means)):
        ax1.plot(cells, cd_mean, 'o', markersize=14, color='white', zorder=5)
        ax1.text(cells, cd_mean, str(i+1), ha='center', va='center', fontsize=9, fontweight='bold', zorder=6)
    
    # Subplot 2: Cl_rms convergence
    ax2.plot(cells_list, cl_rms_list, 'o-', linewidth=2.5, markersize=10, color='#ff7f0e', label='$C_l$ RMS')
    ax2.set_xlabel('Number of Cells', fontsize=11, fontweight='bold')
    ax2.set_ylabel('Lift RMS ($C_{l,rms}$)', fontsize=11, fontweight='bold')
    ax2.set_title(f'Grid Convergence Study (dt={dt_key}): Lift Oscillation', fontsize=12, fontweight='bold')
    ax2.set_xscale('log')
    ax2.grid(True, alpha=0.3, which='both')
    ax2.legend(fontsize=10)
    
    # Use same legend table approach
    ax2.text(0.98, 0.97, table_text, transform=ax2.transAxes, fontsize=7,
            verticalalignment='top', horizontalalignment='right',
            bbox=dict(boxstyle='round', facecolor='lightblue', alpha=0.7))
    
    # Add numbered markers on plot
    for i, (cells, cl_rms) in enumerate(zip(cells_list, cl_rms_list)):
        ax2.plot(cells, cl_rms, 'o', markersize=14, color='white', zorder=5)
        ax2.text(cells, cl_rms, str(i+1), ha='center', va='center', fontsize=9, fontweight='bold', zorder=6)
    
    fig.tight_layout()
    dt_str = str(dt_key).replace('.', 'p')
    fig.savefig(PLOTS_DIR / f"04_GridConvergence_dt{dt_str}.png", dpi=150, bbox_inches='tight')
    plt.close(fig)


# --------- IMPROVED GRID CONVERGENCE PLOT (ANNOTATE CELL COUNT, MOVE LEGEND) ---------
for dt_key, cases_in_group in grid_convergence_cases.items():
    if len(cases_in_group) < 2:
        continue
    grid_cases = sorted(cases_in_group, key=lambda x: x[2])
    labels = [x[0] for x in grid_cases]
    cells_list = [x[2] for x in grid_cases]
    cd_means = []
    cd_stds = []
    cl_rms_list = []
    for label in labels:
        row = merged_df[merged_df['label'] == label].iloc[0] if label in merged_df['label'].values else None
        if row is not None:
            cd_means.append(row['Cd_mean'])
            cd_stds.append(row['Cd_std'])
            cl_rms_list.append(row['Cl_rms'])
        else:
            cd_means.append(np.nan)
            cd_stds.append(np.nan)
            cl_rms_list.append(np.nan)
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(15, 6))
    # Subplot 1: Cd convergence (linear x scale, annotate cell count)
    ax1.errorbar(cells_list, cd_means, yerr=cd_stds, fmt='o-', linewidth=2.5, 
                 markersize=10, capsize=5, capthick=2, color='#1f77b4', label='$C_d$ ± std')
    ax1.set_xlabel('Number of Cells', fontsize=11, fontweight='bold')
    ax1.set_ylabel('Mean Drag Coefficient ($C_d$)', fontsize=11, fontweight='bold')
    ax1.set_title(f'Grid Convergence (dt={dt_key}): Drag Coefficient', fontsize=12, fontweight='bold')
    ax1.grid(True, alpha=0.3, which='both')
    # Annotate cell count
    for i, (cells, cd_mean) in enumerate(zip(cells_list, cd_means)):
        ax1.annotate(f'{cells}', (cells, cd_mean), textcoords="offset points", xytext=(0,10), ha='center', fontsize=9, color='black', fontweight='bold')
    ax1.legend(fontsize=10, loc='lower right')
    # Subplot 2: Cl_rms convergence (linear x scale, annotate cell count)
    ax2.plot(cells_list, cl_rms_list, 'o-', linewidth=2.5, markersize=10, color='#ff7f0e', label='$C_l$ RMS')
    ax2.set_xlabel('Number of Cells', fontsize=11, fontweight='bold')
    ax2.set_ylabel('Lift RMS ($C_{l,rms}$)', fontsize=11, fontweight='bold')
    ax2.set_title(f'Grid Convergence (dt={dt_key}): Lift Oscillation', fontsize=12, fontweight='bold')
    ax2.grid(True, alpha=0.3, which='both')
    for i, (cells, cl_rms) in enumerate(zip(cells_list, cl_rms_list)):
        ax2.annotate(f'{cells}', (cells, cl_rms), textcoords="offset points", xytext=(0,10), ha='center', fontsize=9, color='black', fontweight='bold')
    ax2.legend(fontsize=10, loc='lower right')
    fig.tight_layout()
    dt_str = str(dt_key).replace('.', 'p')
    fig.savefig(PLOTS_DIR / f"04_GridConvergence_LINEAR_dt{dt_str}.png", dpi=150, bbox_inches='tight')
    plt.close(fig)
print("    ✓ Grid convergence plots saved (linear scale, annotated)")

# --------  D. TIME CONVERGENCE ANALYSIS --------
print("\n  [D] Time Convergence Analysis (varying dt with constant mesh)...")

for mesh_key, cases_in_group in time_convergence_cases.items():
    # --- Only use cases with label containing 'T' followed by a digit (T1, T2, ...)
    import re
    mesh_nx, mesh_ny = mesh_key
    mesh_cases = merged_df[(merged_df['Nx'] == mesh_nx) & (merged_df['Ny'] == mesh_ny)]
    # Filter for T1, T2, ...
    mesh_cases = mesh_cases[mesh_cases['label'].str.contains(r'T\d+', regex=True)]
    # Use dt_x if present, else dt, else dt_y
    if 'dt_x' in mesh_cases.columns:
        dt_col = 'dt_x'
    elif 'dt' in mesh_cases.columns:
        dt_col = 'dt'
    elif 'dt_y' in mesh_cases.columns:
        dt_col = 'dt_y'
    else:
        dt_col = None
    if dt_col is None:
        continue
    mesh_cases = mesh_cases[mesh_cases[dt_col].notnull()]
    mesh_cases = mesh_cases.copy()
    mesh_cases[dt_col] = mesh_cases[dt_col].astype(float)
    mesh_cases = mesh_cases.sort_values(dt_col)
    if len(mesh_cases) < 2:
        continue
    dt_list = mesh_cases[dt_col].values
    cd_means = mesh_cases['Cd_mean'].values
    cd_stds = mesh_cases['Cd_std'].values
    cl_rms_list = mesh_cases['Cl_rms'].values
    labels = mesh_cases['label'].values
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 7))
    ax1.errorbar(dt_list, cd_means, yerr=cd_stds, fmt='s-', linewidth=2.5, 
                 markersize=10, capsize=5, capthick=2, color='#2ca02c', label='$C_d$ ± std')
    ax1.set_xlabel('Time Step (dt)', fontsize=12, fontweight='bold')
    ax1.set_ylabel('Mean Drag Coefficient ($C_d$)', fontsize=12, fontweight='bold')
    ax1.set_title(f'Time Convergence Study (mesh {mesh_nx}×{mesh_ny}): Drag Coefficient', fontsize=13, fontweight='bold')
    # ax1.set_xscale('log')
    ax1.grid(True, alpha=0.3, which='both')
    legend_labels = [f"dt={dt:.2e} ({label})" for dt, label in zip(dt_list, labels)]
    for i, (dt, cd_mean) in enumerate(zip(dt_list, cd_means)):
        ax1.annotate(f'{dt:.2e}', (dt, cd_mean), textcoords="offset points", xytext=(0,10), ha='center', fontsize=9, color='black', fontweight='bold')
    # fig.legend(legend_labels, fontsize=10, loc='upper right')
    ax2.plot(dt_list, cl_rms_list, 's-', linewidth=2.5, markersize=10, color='#d62728', label='$C_l$ RMS')
    ax2.set_xlabel('Time Step (dt)', fontsize=12, fontweight='bold')
    ax2.set_ylabel('Lift RMS ($C_{l,rms}$)', fontsize=12, fontweight='bold')
    ax2.set_title(f'Time Convergence Study (mesh {mesh_nx}×{mesh_ny}): Lift Oscillation', fontsize=13, fontweight='bold')
    # ax2.set_xscale('log')
    ax2.grid(True, alpha=0.3, which='both')
    for i, (dt, cl_rms) in enumerate(zip(dt_list, cl_rms_list)):
        ax2.annotate(f'{dt:.2e}', (dt, cl_rms), textcoords="offset points", xytext=(0,10), ha='center', fontsize=9, color='black', fontweight='bold')
    fig.tight_layout(pad=2.0)
    mesh_str = f"{mesh_nx}x{mesh_ny}"
    plot_file = PLOTS_DIR / f"05_TimeConvergence_mesh{mesh_str}.png"
    fig.savefig(plot_file, dpi=150, bbox_inches='tight')
    plt.close(fig)
    print(f"    ✓ {plot_file.name} — {len(dt_list)} time steps with dt range {dt_list[0]:.2e}-{dt_list[-1]:.2e}")


# --------- TIME CONVERGENCE: PLOT Cd/Cl vs dt (ANNOTATED) ---------
print("\n  [D2] Time Convergence: Cd/Cl vs Timestep (annotated)...")
for mesh_key, cases_in_group in time_convergence_cases.items():
    if len(cases_in_group) < 2:
        continue
    # Extract and sort by dt
    time_cases = sorted(cases_in_group, key=lambda x: (x[1], x[0]), reverse=True)
    labels = [x[0] for x in time_cases]
    dt_list = []
    cd_means = []
    cd_stds = []
    cl_means = []
    cl_rms_list = []
    for label in labels:
        if label in merged_df['label'].values:
            row = merged_df[merged_df['label'] == label].iloc[0]
            dt_val = row.get('dt', np.nan)
            try:
                if isinstance(dt_val, str):
                    dt_val = float(dt_val)
            except (ValueError, TypeError):
                dt_val = np.nan
            if not np.isnan(dt_val):
                dt_list.append(dt_val)
                cd_means.append(row['Cd_mean'])
                cd_stds.append(row['Cd_std'])
                cl_means.append(row['Cl_mean'])
                cl_rms_list.append(row['Cl_rms'])
    if len(dt_list) < 2:
        continue
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 7))
    # Cd vs dt
    ax1.errorbar(dt_list, cd_means, yerr=cd_stds, fmt='s-', linewidth=2.5, 
                 markersize=10, capsize=5, capthick=2, color='#2ca02c', label='$C_d$ ± std')
    ax1.set_xlabel('Time Step (dt)', fontsize=12, fontweight='bold')
    ax1.set_ylabel('Mean Drag Coefficient ($C_d$)', fontsize=12, fontweight='bold')
    ax1.set_title(f'Time Convergence: $C_d$ vs dt (mesh {mesh_key[0]}×{mesh_key[1]})', fontsize=13, fontweight='bold')
    ax1.set_xscale('log')
    ax1.grid(True, alpha=0.3, which='both')
    for i, (dt, cd_mean) in enumerate(zip(dt_list, cd_means)):
        ax1.annotate(f'dt={dt:.2e}', (dt, cd_mean), textcoords="offset points", xytext=(0,10), ha='center', fontsize=9, color='black', fontweight='bold')
    ax1.legend(fontsize=10, loc='lower right')
    # Cl vs dt
    ax2.plot(dt_list, cl_means, 's-', linewidth=2.5, markersize=10, color='#d62728', label='$C_l$ mean')
    ax2.set_xlabel('Time Step (dt)', fontsize=12, fontweight='bold')
    ax2.set_ylabel('Mean Lift Coefficient ($C_l$)', fontsize=12, fontweight='bold')
    ax2.set_title(f'Time Convergence: $C_l$ vs dt (mesh {mesh_key[0]}×{mesh_key[1]})', fontsize=13, fontweight='bold')
    ax2.set_xscale('log')
    ax2.grid(True, alpha=0.3, which='both')
    for i, (dt, cl_mean) in enumerate(zip(dt_list, cl_means)):
        ax2.annotate(f'dt={dt:.2e}', (dt, cl_mean), textcoords="offset points", xytext=(0,10), ha='center', fontsize=9, color='black', fontweight='bold')
    ax2.legend(fontsize=10, loc='lower right')
    fig.tight_layout(pad=2.0)
    mesh_str = f"{mesh_key[0]}x{mesh_key[1]}"
    plot_file = PLOTS_DIR / f"05b_TimeConvergence_CdCl_mesh{mesh_str}.png"
    fig.savefig(plot_file, dpi=150, bbox_inches='tight')
    plt.close(fig)
    print(f"    ✓ {plot_file.name} — {len(dt_list)} time steps annotated")
print("    ✓ Time convergence plots saved (Cd/Cl vs dt annotated)")
    
# --------- TIMESTEP SENSITIVITY: Cd/Cl vs timestep (for all cases with same mesh) ---------
print("\n  [D3] Timestep Sensitivity: Cd/Cl vs Timestep Index (all dt for mesh {mesh_key[0]}x{mesh_key[1]})...")
for mesh_key, cases_in_group in time_convergence_cases.items():
    if len(cases_in_group) < 2:
        continue
    # Only consider cases with the same mesh (e.g., 80x80)
    labels = [x[0] for x in cases_in_group]
    # Sort by dt (smallest to largest)
    dt_label_pairs = []
    for label in labels:
        if label in merged_df['label'].values:
            row = merged_df[merged_df['label'] == label].iloc[0]
            dt_val = row.get('dt', np.nan)
            try:
                if isinstance(dt_val, str):
                    dt_val = float(dt_val)
            except (ValueError, TypeError):
                dt_val = np.nan
            if not np.isnan(dt_val):
                dt_label_pairs.append((dt_val, label))
    dt_label_pairs.sort()
    # Plot Cd and Cl time series for each case (different dt)
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 10), sharex=True)
    for i, (dt, label) in enumerate(dt_label_pairs):
        if label in force_data:
            df = force_data[label]
            ax1.plot(df['Time'], df['Cd'], label=f"dt={dt:.2e} ({label})")
            ax2.plot(df['Time'], df['Cl'], label=f"dt={dt:.2e} ({label})")
    ax1.set_ylabel('Drag Coefficient ($C_d$)', fontsize=12, fontweight='bold')
    ax1.set_title(f'Timestep Sensitivity: $C_d$ vs Time (mesh {mesh_key[0]}×{mesh_key[1]})', fontsize=13, fontweight='bold')
    ax1.grid(True, alpha=0.3)
    ax1.legend(fontsize=10, loc='upper right', ncol=2)
    ax2.set_xlabel('Time (s)', fontsize=12, fontweight='bold')
    ax2.set_ylabel('Lift Coefficient ($C_l$)', fontsize=12, fontweight='bold')
    ax2.set_title(f'Timestep Sensitivity: $C_l$ vs Time (mesh {mesh_key[0]}×{mesh_key[1]})', fontsize=13, fontweight='bold')
    ax2.grid(True, alpha=0.3)
    ax2.legend(fontsize=10, loc='upper right', ncol=2)
    fig.tight_layout()
    mesh_str = f"{mesh_key[0]}x{mesh_key[1]}"
    plot_file = PLOTS_DIR / f"05c_TimestepSensitivity_mesh{mesh_str}.png"
    fig.savefig(plot_file, dpi=150, bbox_inches='tight')
    plt.close(fig)
    print(f"    ✓ {plot_file.name} — {len(dt_label_pairs)} timesteps compared")

# --------  E. PERFORMANCE & SCALABILITY ANALYSIS --------
print("\n  [E] Performance & Scalability Analysis...")

# Execution time vs mesh size
valid_timing = merged_df.dropna(subset=['Exec_Time_s'])
sorted_timing = valid_timing.sort_values('Cells')

fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5))

# Subplot 1: Exec Time bar chart with labels
bars = ax1.bar(range(len(sorted_timing)), sorted_timing['Exec_Time_s'], 
               color=plt.cm.RdYlGn_r(np.linspace(0.2, 0.8, len(sorted_timing))), alpha=0.8, edgecolor='black', linewidth=1.2)
ax1.set_xticks(range(len(sorted_timing)))
ax1.set_xticklabels(sorted_timing['label'].values, rotation=45, ha='right', fontsize=9)
ax1.set_ylabel('Execution Time (s)', fontsize=11, fontweight='bold')
ax1.set_title('CPU Execution Time by Case', fontsize=12, fontweight='bold')
ax1.grid(True, alpha=0.3, axis='y')

# Add value labels on bars
for i, (bar, val) in enumerate(zip(bars, sorted_timing['Exec_Time_s'].values)):
    ax1.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 50,
            f'{val:.0f}s', ha='center', va='bottom', fontsize=9, fontweight='bold')

# Subplot 2: Parallel efficiency
if 'Clock_Time_s' in valid_timing.columns:
    sorted_timing_full = sorted_timing.dropna(subset=['Clock_Time_s'])
    efficiency = (sorted_timing_full['Exec_Time_s'] / sorted_timing_full['Clock_Time_s']) * 100
    bars2 = ax2.bar(range(len(sorted_timing_full)), efficiency,
                   color=plt.cm.Blues(np.linspace(0.4, 0.9, len(sorted_timing_full))), alpha=0.8, edgecolor='black', linewidth=1.2)
    ax2.set_xticks(range(len(sorted_timing_full)))
    ax2.set_xticklabels(sorted_timing_full['label'].values, rotation=45, ha='right', fontsize=9)
    ax2.set_ylabel('Parallel Efficiency (%)', fontsize=11, fontweight='bold')
    ax2.set_title('Parallel Efficiency (CPU/Wall Time)', fontsize=12, fontweight='bold')
    ax2.axhline(y=100, color='red', linestyle='--', linewidth=1.5, label='100% efficiency')
    ax2.grid(True, alpha=0.3, axis='y')
    ax2.legend()
    
    for i, (bar, val) in enumerate(zip(bars2, efficiency.values)):
        ax2.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 2,
                f'{val:.1f}%', ha='center', va='bottom', fontsize=9, fontweight='bold')

fig.tight_layout()
fig.savefig(PLOTS_DIR / "06_Performance_Analysis.png", dpi=150, bbox_inches='tight')
plt.close(fig)

print("    ✓ Performance analysis plot saved")

# --------  F. STATISTICAL VALIDATION --------
print("\n  [F] Statistical Validation Plots...")

# Drag-Lift Phase Space
fig, ax = plt.subplots(figsize=(10, 8))
colors = plt.cm.tab20(np.linspace(0, 1, len(force_data)))

for (case_label, df), color in zip(force_data.items(), colors):
    skip = int(len(df) * 0.1)
    ax.scatter(df['Cd'].iloc[skip:], df['Cl'].iloc[skip:], 
              alpha=0.4, s=15, label=case_label, color=color)

ax.set_xlabel('Drag Coefficient ($C_d$)', fontsize=11, fontweight='bold')
ax.set_ylabel('Lift Coefficient ($C_l$)', fontsize=11, fontweight='bold')
ax.set_title('Drag-Lift Phase Space — All Cases', fontsize=12, fontweight='bold')
ax.legend(fontsize=8, loc='best', ncol=2)
ax.grid(True, alpha=0.3)
fig.tight_layout()
fig.savefig(PLOTS_DIR / "07_DragLift_PhaseSpace.png", dpi=150, bbox_inches='tight')
plt.close(fig)

# Statistics Bar Chart
fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 6))
sorted_stats = merged_df.sort_values('Cells')

x_pos = np.arange(len(sorted_stats))
width = 0.35

bars1 = ax1.bar(x_pos - width/2, sorted_stats['Cd_mean'], width,
               label='$C_d$ mean', color='#1f77b4', alpha=0.8, edgecolor='black', linewidth=1)
bars1_err = ax1.errorbar(x_pos - width/2, sorted_stats['Cd_mean'], yerr=sorted_stats['Cd_std'],
                        fmt='none', ecolor='black', capsize=3, capthick=1.5, linewidth=1.5)

ax1.set_xticks(x_pos)
ax1.set_xticklabels(sorted_stats['label'].values, rotation=45, ha='right', fontsize=9)
ax1.set_ylabel('Coefficient Value', fontsize=11, fontweight='bold')
ax1.set_title('Mean Drag Coefficient with Std Dev', fontsize=12, fontweight='bold')
ax1.grid(True, alpha=0.3, axis='y')
ax1.legend(fontsize=10)

bars2 = ax2.bar(x_pos, sorted_stats['Cl_rms'], width,
               label='$C_l$ RMS', color='#ff7f0e', alpha=0.8, edgecolor='black', linewidth=1)
ax2.set_xticks(x_pos)
ax2.set_xticklabels(sorted_stats['label'].values, rotation=45, ha='right', fontsize=9)
ax2.set_ylabel('Lift RMS', fontsize=11, fontweight='bold')
ax2.set_title('Lift Oscillation Amplitude', fontsize=12, fontweight='bold')
ax2.grid(True, alpha=0.3, axis='y')
ax2.legend(fontsize=10)

for i, (bar, val) in enumerate(zip(bars1, sorted_stats['Cd_mean'].values)):
    ax1.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.02,
            f'{val:.3f}', ha='center', va='bottom', fontsize=8)

for i, (bar, val) in enumerate(zip(bars2, sorted_stats['Cl_rms'].values)):
    ax2.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.01,
            f'{val:.3f}', ha='center', va='bottom', fontsize=8)

fig.tight_layout()
fig.savefig(PLOTS_DIR / "08_Statistics_Comparison.png", dpi=150, bbox_inches='tight')
plt.close(fig)

print("    ✓ Statistical validation plots saved")

print("\n  All plots generated successfully ✓") 


# ========================================================================
# 7. FINAL SUMMARY TABLE & ANALYSIS
# ========================================================================
print("\n[STEP 7/7] 📋 Generating final summary table...\n")

print("="*120)
print("█ COMPREHENSIVE CASE SUMMARY".ljust(120))
print("="*120)

# Build summary table with safe column selection
summary_cols = ['label', 'Cells']
if 'Nx' in merged_df.columns:
    summary_cols.extend(['Nx', 'Ny'])
if 'dt' in merged_df.columns:
    summary_cols.append('dt')
summary_cols.extend(['Exec_Time_s', 'Clock_Time_s', 'Cd_mean', 'Cd_std', 'Cl_rms'])

# Filter to only existing columns
summary_cols = [col for col in summary_cols if col in merged_df.columns]

summary_table = merged_df[summary_cols].copy()
summary_table = summary_table.sort_values('Cells')

# Format for display
pd.set_option('display.max_columns', None)
pd.set_option('display.width', None)
pd.set_option('display.max_colwidth', None)

print(summary_table.to_string(index=False))

# Efficiency Analysis
print("\n" + "="*120)
print("█ PARALLEL EFFICIENCY ANALYSIS".ljust(120))
print("="*120)
print(f"{'Case Label':<30} {'Cells':<8} {'ExecTime(s)':<15} {'ClockTime(s)':<15} {'Efficiency':<15}")
print("-"*120)

valid = merged_df.dropna(subset=['Exec_Time_s', 'Clock_Time_s']).sort_values('Cells')
for _, row in valid.iterrows():
    efficiency_pct = (row['Exec_Time_s'] / row['Clock_Time_s']) * 100 if row['Clock_Time_s'] else 0
    print(f"{row['label']:<30} {int(row['Cells']):<8} {row['Exec_Time_s']:<15.2f} {row['Clock_Time_s']:<15.2f} {efficiency_pct:<14.1f}%")

# Convergence Summary
print("\n" + "="*120)
print("█ CONVERGENCE STUDY CLASSIFICATION".ljust(120))
print("="*120)

print("\n📊 GRID CONVERGENCE GROUPS (fixed dt, varying mesh):")
print("-"*120)
for dt_key, cases_in_group in grid_convergence_cases.items():
    if len(cases_in_group) >= 2:
        print(f"\n  dt = {dt_key}:")
        for label, mesh_key, cells in sorted(cases_in_group, key=lambda x: x[2]):
            row_data = merged_df[merged_df['label'] == label].iloc[0] if label in merged_df['label'].values else None
            if row_data is not None:
                print(f"    ✓ {label:<35} | Cells={cells:<6d} | Mesh={mesh_key[0]:<3}×{mesh_key[1]:<3} | Cd={row_data['Cd_mean']:>8.5f} | Cl_rms={row_data['Cl_rms']:>8.5f}")

print("\n📊 TIME CONVERGENCE GROUPS (fixed mesh, varying dt):")
print("-"*120)
for mesh_key, cases_in_group in time_convergence_cases.items():
    if len(cases_in_group) >= 2:
        print(f"\n  mesh {mesh_key[0]}×{mesh_key[1]}:")
        for label, dt_val, cells in sorted(cases_in_group, key=lambda x: (x[1], x[0]), reverse=True):
            row_data = merged_df[merged_df['label'] == label].iloc[0] if label in merged_df['label'].values else None
            if row_data is not None:
                print(f"    ✓ {label:<35} | dt={str(dt_val):<8} | Cells={cells:<6d} | Cd={row_data['Cd_mean']:>8.5f} | Cl_rms={row_data['Cl_rms']:>8.5f}")

# Final summary
print("\n" + "="*120)
print("█ ANALYSIS COMPLETE ✓".ljust(120))
print("="*120)
print(f"\n📁 Output Locations:")
print(f"   • Plots Directory: {PLOTS_DIR}/")
print(f"   • Summary CSV: {summary_csv}")
print(f"\n📊 Generated Plots ({len(list(PLOTS_DIR.glob('*.png')))} files):")
for i, plot_file in enumerate(sorted(PLOTS_DIR.glob('*.png')), 1):
    print(f"   {i}. {plot_file.name}")

print(f"\n🎯 Plots Organized by Category:")
print(f"   • 01_TimeSeries_*.png: Individual case Cd/Cl time evolution")
print(f"   • 02-03: Collective Cd/Cl comparison across all cases")
print(f"   • 04_GridConvergence_*.png: Mesh refinement effects (separate for each dt)")
print(f"   • 05_TimeConvergence_*.png: Time step effects (separate for each mesh)")
print(f"   • 05c_TimestepSensitivity_*.png: Cd/Cl vs time for all timesteps (timestep sensitivity)")
print(f"   • 06_Performance_Analysis.png: CPU time and parallel efficiency")
print(f"   • 07_DragLift_PhaseSpace.png: Drag-lift correlation")
print(f"   • 08_Statistics_Comparison.png: Mean/std Cd and Cl_rms")

print("\n" + "="*120 + "\n")
