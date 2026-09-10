#!/usr/bin/env python3
"""
=============================================================
Advanced OpenFOAM PostProcessing Analysis Script
=============================================================

Features
--------
✔ Automatic case discovery
✔ Reads OpenFOAM postProcessing data
✔ Force coefficient analysis
✔ Strouhal number estimation
✔ y+ analysis
✔ Mass conservation analysis
✔ Solver residual plots
✔ Multi-case comparison
✔ Automatic report generation

Author: ChatGPT
=============================================================
"""

from pathlib import Path
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use('Agg')

import matplotlib.pyplot as plt
from scipy.fft import fft, fftfreq
import warnings
import re

warnings.filterwarnings("ignore")

# ============================================================
# CONFIGURATION
# ============================================================

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT_DIR = SCRIPT_DIR.parent
CASES_DIR = ROOT_DIR / "cases"

GLOBAL_ANALYSIS_DIR = ROOT_DIR / "global_analysis"
GLOBAL_ANALYSIS_DIR.mkdir(exist_ok=True)

SUMMARY_FILE = GLOBAL_ANALYSIS_DIR / "global_case_summary.csv"

D = 0.1
NU = 1.5e-5

FIGSIZE = (10, 6)
DPI = 300

# ============================================================
# HELPER FUNCTIONS
# ============================================================

def ensure_dir(path):
    path.mkdir(parents=True, exist_ok=True)


def read_openfoam_table(filepath):

    if not filepath.exists():
        return None

    try:
        data = pd.read_csv(
            filepath,
            delim_whitespace=True,
            comment='#',
            header=None
        )

        return data

    except Exception as e:
        print(f"Failed reading {filepath}: {e}")
        return None


def extract_re(case_name):

    match = re.search(r'Re(\d+)', case_name)

    if match:
        return float(match.group(1))

    return None


def compute_fft(time, signal):

    time = np.array(time)
    signal = np.array(signal)

    dt = np.mean(np.diff(time))

    signal = signal - np.mean(signal)

    n = len(signal)

    yf = fft(signal)
    xf = fftfreq(n, dt)

    positive = xf > 0

    xf = xf[positive]
    amp = 2.0 / n * np.abs(yf[positive])

    return xf, amp


def estimate_strouhal(time, cl, U, D):

    xf, amp = compute_fft(time, cl)

    if len(amp) < 5:
        return np.nan, np.nan, xf, amp

    peak_idx = np.argmax(amp)

    shedding_freq = xf[peak_idx]

    St = shedding_freq * D / U

    return St, shedding_freq, xf, amp


def save_plot(fig, path):

    fig.tight_layout()
    fig.savefig(path, dpi=DPI)
    plt.close(fig)


# ============================================================
# MAIN ANALYSIS
# ============================================================

all_results = []

case_dirs = sorted([d for d in CASES_DIR.iterdir() if d.is_dir()])

print("=" * 70)
print("ADVANCED OPENFOAM CFD ANALYSIS")
print("=" * 70)
print(f"Found {len(case_dirs)} cases")
print()

# ============================================================
# LOOP OVER CASES
# ============================================================

for case_dir in case_dirs:

    print("-" * 70)
    print(f"Processing case: {case_dir.name}")

    post_dir = case_dir / "postProcessing"

    if not post_dir.exists():
        print("  No postProcessing directory.")
        continue

    analysis_dir = post_dir / "analysis"
    figures_dir = analysis_dir / "figures"
    data_dir = analysis_dir / "data"

    ensure_dir(analysis_dir)
    ensure_dir(figures_dir)
    ensure_dir(data_dir)

    result = {
        "Case": case_dir.name,
        "Re": np.nan,
        "U": np.nan,
        "Cd_mean": np.nan,
        "Cd_std": np.nan,
        "Cl_mean": np.nan,
        "Cl_rms": np.nan,
        "St": np.nan,
        "Freq": np.nan,
        "Max_yPlus": np.nan,
        "Mean_yPlus": np.nan,
        "Mass_Imbalance": np.nan
    }

    # ========================================================
    # Extract Reynolds number
    # ========================================================

    Re = extract_re(case_dir.name)

    if Re is not None:
        U = Re * NU / D
    else:
        U = 1.0

    result["Re"] = Re
    result["U"] = U

    # ========================================================
    # FORCE COEFFICIENTS
    # ========================================================

    coeff_file = (
        post_dir /
        "forceCoeffs" /
        "0" /
        "coefficient.dat"
    )

    coeff_data = read_openfoam_table(coeff_file)

    if coeff_data is not None:

        ncols = coeff_data.shape[1]

        if ncols >= 5:
            # OpenFOAM forceCoeffs output format:
            # Col 0: Time
            # Col 1: Cd (total drag)
            # Col 2: Cd(f) (pressure drag)
            # Col 3: Cd(r) (viscous drag)
            # Col 4: Cl (lift)
            # Cols 5+: Other components
            
            coeff_data = coeff_data.iloc[:, [0, 1, 4]]

            coeff_data.columns = [
                "time",
                "Cd",
                "Cl"
            ]

            coeff_data.to_csv(
                data_dir / "force_coefficients.csv",
                index=False
            )

            time = coeff_data["time"]
            Cd = coeff_data["Cd"]
            Cl = coeff_data["Cl"]

            # discard startup transient
            start_idx = int(0.4 * len(time))

            time_ss = time.iloc[start_idx:]
            Cd_ss = Cd.iloc[start_idx:]
            Cl_ss = Cl.iloc[start_idx:]

            Cd_mean = Cd_ss.mean()
            Cd_std = Cd_ss.std()

            Cl_mean = Cl_ss.mean()
            Cl_rms = np.sqrt(np.mean(Cl_ss**2))

            result["Cd_mean"] = Cd_mean
            result["Cd_std"] = Cd_std
            result["Cl_mean"] = Cl_mean
            result["Cl_rms"] = Cl_rms

            # ====================================================
            # Strouhal analysis
            # ====================================================

            try:

                St, freq, xf, amp = estimate_strouhal(
                    time_ss,
                    Cl_ss,
                    U,
                    D
                )

                result["St"] = St
                result["Freq"] = freq

                fig = plt.figure(figsize=FIGSIZE)

                plt.plot(xf, amp)

                plt.xlabel("Frequency [Hz]")
                plt.ylabel("Amplitude")
                plt.title(
                    f"Lift FFT - {case_dir.name}"
                )

                plt.grid(True)

                save_plot(
                    fig,
                    figures_dir / "cl_fft.png"
                )

            except Exception as e:
                print(f"  FFT failed: {e}")

            # ====================================================
            # Force coefficient plots
            # ====================================================

            fig = plt.figure(figsize=FIGSIZE)

            plt.plot(time, Cd, label="Cd")
            plt.plot(time, Cl, label="Cl")

            plt.xlabel("Time [s]")
            plt.ylabel("Coefficient")

            plt.title(
                f"Force Coefficients - {case_dir.name}"
            )

            plt.legend()
            plt.grid(True)

            save_plot(
                fig,
                figures_dir / "force_coefficients.png"
            )

            # Cd history
            fig = plt.figure(figsize=FIGSIZE)

            plt.plot(time, Cd)

            plt.xlabel("Time [s]")
            plt.ylabel("Cd")

            plt.title(
                f"Drag Coefficient - {case_dir.name}"
            )

            plt.grid(True)

            save_plot(
                fig,
                figures_dir / "Cd_history.png"
            )

            # Cl history
            fig = plt.figure(figsize=FIGSIZE)

            plt.plot(time, Cl)

            plt.xlabel("Time [s]")
            plt.ylabel("Cl")

            plt.title(
                f"Lift Coefficient - {case_dir.name}"
            )

            plt.grid(True)

            save_plot(
                fig,
                figures_dir / "Cl_history.png"
            )

            print(f"  Re       = {Re}")
            print(f"  U        = {U:.5f}")
            print(f"  Cd_mean  = {Cd_mean:.5f}")
            print(f"  Cl_rms   = {Cl_rms:.5f}")
            print(f"  St       = {St:.5f}")

    # ========================================================
    # yPlus ANALYSIS
    # ========================================================

    yplus_file = (
        post_dir /
        "yPlus" /
        "0" /
        "yPlus.dat"
    )

    yplus_data = read_openfoam_table(yplus_file)

    if yplus_data is not None:

        try:

            if yplus_data.shape[1] == 4:

                yplus_data.columns = [
                    "time",
                    "min",
                    "max",
                    "average"
                ]

            elif yplus_data.shape[1] == 5:

                yplus_data.columns = [
                    "time",
                    "patch",
                    "min",
                    "max",
                    "average"
                ]

            else:
                raise ValueError(
                    f"Unexpected yPlus format: "
                    f"{yplus_data.shape[1]} columns"
                )

            max_yplus = yplus_data["max"].max()
            mean_yplus = yplus_data["average"].mean()

            result["Max_yPlus"] = max_yplus
            result["Mean_yPlus"] = mean_yplus

            fig = plt.figure(figsize=FIGSIZE)

            plt.plot(
                yplus_data["time"],
                yplus_data["max"],
                label="Max y+"
            )

            plt.plot(
                yplus_data["time"],
                yplus_data["average"],
                label="Mean y+"
            )

            plt.xlabel("Time [s]")
            plt.ylabel("y+")

            plt.title(
                f"yPlus Evolution - {case_dir.name}"
            )

            plt.legend()
            plt.grid(True)

            save_plot(
                fig,
                figures_dir / "yplus.png"
            )

        except Exception as e:
            print(f"  yPlus analysis failed: {e}")

    # ========================================================
    # MASS FLOW ANALYSIS
    # ========================================================

    in_file = (
        post_dir /
        "inMassFlow" /
        "0" /
        "surfaceFieldValue.dat"
    )

    out_file = (
        post_dir /
        "outMassFlow" /
        "0" /
        "surfaceFieldValue.dat"
    )

    in_data = read_openfoam_table(in_file)
    out_data = read_openfoam_table(out_file)

    if in_data is not None and out_data is not None:

        try:

            in_data.columns = ["time", "massIn"]
            out_data.columns = ["time", "massOut"]

            merged = pd.merge(
                in_data,
                out_data,
                on="time"
            )

            imbalance = np.abs(
                merged["massIn"] + merged["massOut"]
            )

            result["Mass_Imbalance"] = imbalance.mean()

            fig = plt.figure(figsize=FIGSIZE)

            plt.plot(
                merged["time"],
                merged["massIn"],
                label="Inlet"
            )

            plt.plot(
                merged["time"],
                merged["massOut"],
                label="Outlet"
            )

            plt.xlabel("Time [s]")
            plt.ylabel("Mass Flow")

            plt.title(
                f"Mass Flow Balance - {case_dir.name}"
            )

            plt.legend()
            plt.grid(True)

            save_plot(
                fig,
                figures_dir / "mass_balance.png"
            )

        except Exception as e:
            print(f"  Mass flow analysis failed: {e}")

    # ========================================================
    # SOLVER RESIDUALS
    # ========================================================

    solver_file = (
        post_dir /
        "solverInfo" /
        "0" /
        "solverInfo.dat"
    )

    solver_data = read_openfoam_table(solver_file)

    if solver_data is not None:

        try:

            fig = plt.figure(figsize=FIGSIZE)

            for col in range(
                1,
                min(6, solver_data.shape[1])
            ):

                plt.semilogy(
                    solver_data.iloc[:, 0],
                    solver_data.iloc[:, col]
                )

            plt.xlabel("Time [s]")
            plt.ylabel("Residual")

            plt.title(
                f"Solver Residuals - {case_dir.name}"
            )

            plt.grid(True)

            save_plot(
                fig,
                figures_dir / "solver_residuals.png"
            )

        except Exception as e:
            print(f"  Residual plotting failed: {e}")

    # ========================================================
    # SAVE REPORT
    # ========================================================

    report_file = analysis_dir / "summary_report.txt"

    with open(report_file, "w") as f:

        f.write("=" * 60 + "\n")
        f.write(f"CASE REPORT: {case_dir.name}\n")
        f.write("=" * 60 + "\n\n")

        for key, value in result.items():
            f.write(f"{key:20s}: {value}\n")

    all_results.append(result)

    print("  Analysis completed")
    print()

# ============================================================
# GLOBAL COMPARISON
# ============================================================

if len(all_results) > 0:

    summary_df = pd.DataFrame(all_results)

    summary_df.to_csv(
        SUMMARY_FILE,
        index=False
    )

    # ========================================================
    # Cd comparison
    # ========================================================

    fig = plt.figure(figsize=(12, 6))

    plt.bar(
        summary_df["Case"],
        summary_df["Cd_mean"]
    )

    plt.ylabel("Mean Cd")

    plt.title(
        "Mean Drag Coefficient Comparison"
    )

    plt.xticks(rotation=45)

    plt.grid(True)

    save_plot(
        fig,
        GLOBAL_ANALYSIS_DIR / "Cd_comparison.png"
    )

    # ========================================================
    # Strouhal comparison
    # ========================================================

    fig = plt.figure(figsize=(12, 6))

    plt.bar(
        summary_df["Case"],
        summary_df["St"]
    )

    plt.ylabel("Strouhal Number")

    plt.title(
        "Strouhal Number Comparison"
    )

    plt.xticks(rotation=45)

    plt.grid(True)

    save_plot(
        fig,
        GLOBAL_ANALYSIS_DIR / "St_comparison.png"
    )

    # ========================================================
    # yPlus comparison
    # ========================================================

    fig = plt.figure(figsize=(12, 6))

    plt.bar(
        summary_df["Case"],
        summary_df["Max_yPlus"]
    )

    plt.ylabel("Maximum y+")

    plt.title(
        "Maximum y+ Comparison"
    )

    plt.xticks(rotation=45)

    plt.grid(True)

    save_plot(
        fig,
        GLOBAL_ANALYSIS_DIR / "yplus_comparison.png"
    )

    # ========================================================
    # Cd vs Re (Reynolds dependency)
    # ========================================================

    valid_re = summary_df[summary_df["Re"].notna()]

    if len(valid_re) > 1:

        valid_re = valid_re.sort_values("Re")

        fig = plt.figure(figsize=(12, 6))

        plt.scatter(
            valid_re["Re"],
            valid_re["Cd_mean"],
            s=100,
            alpha=0.7,
            color='blue'
        )

        plt.plot(
        valid_re["Re"],
        valid_re["Cd_mean"],
        linestyle='-',
        linewidth=1.5,
        color='blue',
        alpha=0.8
        )

        plt.xscale('log')   # Logarithmic Reynolds number axis
        plt.xlabel("Reynolds Number (Re)", fontsize=12)
        plt.ylabel("Mean Drag Coefficient (Cd)", fontsize=12)
        plt.title("Drag Coefficient vs Reynolds Number", fontsize=14)
        plt.grid(True, alpha=0.3)

        save_plot(
            fig,
            GLOBAL_ANALYSIS_DIR / "Cd_vs_Re.png"
        )

        print("✓ Generated: Cd vs Re plot")

    # ========================================================
    # Cl (rms) vs Re (Reynolds dependency)
    # ========================================================

    if len(valid_re) > 1:

        fig = plt.figure(figsize=(12, 6))

        plt.scatter(
            valid_re["Re"],
            valid_re["Cl_rms"],
            s=100,
            alpha=0.7,
            color='green'
        )

        plt.plot(
        valid_re["Re"],
        valid_re["Cl_rms"],
        linestyle='-',
        linewidth=1.5,
        color='blue',
        alpha=0.8
        )

        plt.xscale('log')   # Logarithmic Reynolds number axis
        plt.xlabel("Reynolds Number (Re)", fontsize=12)
        plt.ylabel("RMS Lift Coefficient (Cl_rms)", fontsize=12)
        plt.title("Lift Coefficient (RMS) vs Reynolds Number", fontsize=14)
        plt.grid(True, alpha=0.3)

        save_plot(
            fig,
            GLOBAL_ANALYSIS_DIR / "Cl_rms_vs_Re.png"
        )

        print("✓ Generated: Cl (rms) vs Re plot")

    # ========================================================
    # Strouhal Number vs Re (Vortex shedding frequency)
    # ========================================================

    valid_st = summary_df[
        (summary_df["Re"].notna()) &
        (summary_df["St"].notna()) &
        (summary_df["St"] > 0)
    ]

    if len(valid_st) > 1:

        valid_st = valid_st.sort_values("Re")

        fig = plt.figure(figsize=(12, 6))

        plt.scatter(
            valid_st["Re"],
            valid_st["St"],
            s=100,
            alpha=0.7,
            color='red'
        )

        plt.plot(
        valid_st["Re"],
        valid_st["St"],
        linestyle='-',
        linewidth=1.5,
        color='blue',
        alpha=0.8
        )

        plt.xscale('log')   # Logarithmic Reynolds number axis
        plt.xlabel("Reynolds Number (Re)", fontsize=12)
        plt.ylabel("Strouhal Number (St)", fontsize=12)
        plt.title("Strouhal Number vs Reynolds Number", fontsize=14)
        plt.grid(True, alpha=0.3)

        save_plot(
            fig,
            GLOBAL_ANALYSIS_DIR / "St_vs_Re.png"
        )

        print("✓ Generated: St vs Re plot")

    print("=" * 70)
    print("GLOBAL ANALYSIS COMPLETED")
    print("=" * 70)

    print(f"Summary CSV:")
    print(f"  {SUMMARY_FILE}")

    print()

else:
    print("No valid cases processed.")