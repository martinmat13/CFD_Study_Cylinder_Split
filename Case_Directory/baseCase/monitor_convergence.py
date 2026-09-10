#!/usr/bin/env python3
"""
============================================================================
OpenFOAM Convergence Monitor  –  v2.0
============================================================================
Real-time monitoring script for cylinder CFD case convergence.

Usage:
    python3 monitor_convergence.py                  # run all static checks
    python3 monitor_convergence.py --live           # live residual window
    python3 monitor_convergence.py --live --interval 1.5
    python3 monitor_convergence.py --residuals      # static residual PNG only
    python3 monitor_convergence.py --forces         # static force PNG only
    python3 monitor_convergence.py --mass           # mass-balance check only

Handles the new mixed-type solverInfo.dat format:
    # Solver information
    # Time   U_solver   Ux_initial   Ux_final   Ux_iters   ...
    0.0001   smoothSolver   1.00e+00   3.18e-02   1   ...
============================================================================o           
"""

import os
import argparse
from datetime import datetime

import pandas as pd
import matplotlib
import matplotlib.pyplot as plt
import matplotlib.animation as animation

# ── Paths ─────────────────────────────────────────────────────────────────────
CASE_DIR = os.path.dirname(os.path.abspath(__file__))
POST_DIR  = os.path.join(CASE_DIR, "postProcessing")

# ── Visual constants ──────────────────────────────────────────────────────────
CONVERGENCE_THRESHOLD = 1e-4

# Ordered so legend reads: velocity → pressure → turbulence
RESIDUAL_STYLES = {
    "Ux_final":    dict(color="#E74C3C", ls="-",  lw=1.6, label="Ux"),
    "Uy_final":    dict(color="#FF7F50", ls="--", lw=1.4, label="Uy"),
    "p_final":     dict(color="#2ECC71", ls="-",  lw=1.6, label="p"),
    "k_final":     dict(color="#3498DB", ls="-",  lw=1.6, label="k"),
    "omega_final": dict(color="#A78BFA", ls="-",  lw=1.6, label="ω"),
    "epsilon_final": dict(color="#F59E0B", ls=":", lw=1.4, label="ε"),
}

DARK_BG   = "#16213E"
DARK_AX   = "#1A1A2E"
DARK_GRID = "#2A2A4E"
DARK_TEXT = "#D0D0E8"
DARK_EDGE = "#444466"


# ═══════════════════════════════════════════════════════════════════════════════
#  FILE PARSER
# ═══════════════════════════════════════════════════════════════════════════════

def parse_solver_dat(filepath: str) -> pd.DataFrame | None:
    """
    Parse solverInfo.dat files that contain mixed string/numeric columns.

    Format example
    --------------
    # Solver information
    # Time   U_solver   Ux_initial   Ux_final   Ux_iters   U_converged   ...
    0.0001   smoothSolver   1.00e+00   3.18e-02   1   false   ...

    Handles:
      - Solver name tokens (smoothSolver, GAMG, …)
      - Boolean tokens  (true / false)
      - Scientific-notation floats
      - Partially-written last lines (simulation still running)
    """
    if not os.path.exists(filepath):
        return None

    with open(filepath, "r") as fh:
        lines = fh.readlines()

    if len(lines) < 3:
        return None

    # ── Find the column-header line (starts with '#' and contains 'Time') ───
    header_idx = None
    for i, line in enumerate(lines):
        if line.startswith("#") and "Time" in line:
            header_idx = i
            break

    if header_idx is None:
        return None

    columns    = lines[header_idx].lstrip("#").split()
    n_cols     = len(columns)
    data_start = header_idx + 1

    # ── Parse data rows ──────────────────────────────────────────────────────
    rows = []
    for line in lines[data_start:]:
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        parts = s.split()
        if not parts:
            continue
        # Tolerate short lines (last line still being written)
        if len(parts) < n_cols:
            parts += [None] * (n_cols - len(parts))
        rows.append(parts[:n_cols])

    if not rows:
        return None

    df = pd.DataFrame(rows, columns=columns)

    # ── Type conversions ─────────────────────────────────────────────────────
    # Numeric: Time, *_initial, *_final, *_iters
    numeric_tags = ("Time", "initial", "final", "iters")
    for col in df.columns:
        if any(t in col for t in numeric_tags):
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # Boolean: *_converged
    for col in df.columns:
        if "converged" in col.lower():
            df[col] = df[col].map({"true": True, "false": False})

    return df


# ═══════════════════════════════════════════════════════════════════════════════
#  DRAWING HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

def _draw_residuals(ax: plt.Axes, df: pd.DataFrame, time_col: str,
                    dark: bool = False) -> bool:
    """
    Clear *ax* and redraw all residual curves found in *df*.

    Returns True if at least one curve was drawn.
    """
    ax.cla()

    time    = pd.to_numeric(df[time_col], errors="coerce")
    plotted = False

    for col, sty in RESIDUAL_STYLES.items():
        if col not in df.columns:
            continue
        series = pd.to_numeric(df[col], errors="coerce")
        mask   = series.notna() & (series > 0)
        if not mask.any():
            continue
        ax.semilogy(
            time[mask], series[mask],
            color=sty["color"], ls=sty["ls"], lw=sty["lw"],
            label=sty["label"], alpha=0.92,
        )
        plotted = True

    if not plotted:
        colour = DARK_TEXT if dark else "#666666"
        ax.text(0.5, 0.5, "Waiting for residual data…",
                ha="center", va="center", transform=ax.transAxes,
                fontsize=12, color=colour)
        return False

    # ── Convergence-threshold reference line ─────────────────────────────────
    ax.axhline(
        CONVERGENCE_THRESHOLD,
        color="#AAAAAA", ls=":", lw=1.1, alpha=0.75,
        label=f"Threshold ({CONVERGENCE_THRESHOLD:.0e})",
    )

    # ── Axes decoration ───────────────────────────────────────────────────────
    ax.set_xlabel("Simulation Time (s)", fontsize=11)
    ax.set_ylabel("Residual", fontsize=11)
    ax.set_ylim(bottom=1e-10, top=10.0)
    ax.grid(True, which="both", ls="--", alpha=0.20)
    ax.grid(True, which="major", ls="--", alpha=0.38)

    legend = ax.legend(loc="upper right", fontsize=9, framealpha=0.88,
                        ncol=1, handlelength=2.2)

    # ── Title with simulation time & wall-clock ───────────────────────────────
    t_last = time.dropna().iloc[-1] if time.notna().any() else None
    ts     = datetime.now().strftime("%H:%M:%S")
    n_pts  = int(mask.sum()) if plotted else 0
    if t_last is not None:
        title = (f"Solver Residuals  ·  sim t = {t_last:.5g} s  "
                 f"·  {len(df)} steps  ·  [{ts}]")
    else:
        title = "Solver Residuals"
    ax.set_title(title, fontsize=11, fontweight="bold", pad=10)

    # ── Dark-mode palette ─────────────────────────────────────────────────────
    if dark:
        _apply_dark(ax)

    return True


def _apply_dark(ax: plt.Axes) -> None:
    """Apply dark-theme colours to *ax* and its legend."""
    ax.set_facecolor(DARK_AX)
    for spine in ax.spines.values():
        spine.set_color(DARK_EDGE)
    ax.tick_params(colors=DARK_TEXT, which="both")
    ax.xaxis.label.set_color(DARK_TEXT)
    ax.yaxis.label.set_color(DARK_TEXT)
    ax.title.set_color("#EEEEFF")
    ax.yaxis.grid(True, which="both", color=DARK_GRID, ls="--", alpha=0.5)
    ax.xaxis.grid(True, which="major", color=DARK_GRID, ls="--", alpha=0.3)
    legend = ax.get_legend()
    if legend:
        legend.get_frame().set_facecolor("#252540")
        legend.get_frame().set_edgecolor(DARK_EDGE)
        for text in legend.get_texts():
            text.set_color(DARK_TEXT)


# ═══════════════════════════════════════════════════════════════════════════════
#  STATIC RESIDUAL PLOT
# ═══════════════════════════════════════════════════════════════════════════════

def check_residuals() -> bool:
    """Parse solverInfo.dat, draw residuals to PNG, print statistics."""
    residual_file = os.path.join(POST_DIR, "solverInfo", "0", "solverInfo.dat")

    if not os.path.exists(residual_file):
        print("❌ Residuals file not found:", residual_file)
        return False

    print("📊 Reading residuals from:", residual_file)
    df = parse_solver_dat(residual_file)

    if df is None or len(df) == 0:
        print("⚠️  Could not parse residuals file or no data found")
        return False

    time_col = df.columns[0]  # 'Time'
    df[time_col] = pd.to_numeric(df[time_col], errors="coerce")
    df = df.dropna(subset=[time_col])
    print(f"   ✓ Loaded {len(df)} timesteps  "
          f"(t = {df[time_col].min():.4g} … {df[time_col].max():.4g} s)")

    # ── Plot ──────────────────────────────────────────────────────────────────
    fig, ax = plt.subplots(figsize=(13, 6))
    fig.subplots_adjust(left=0.08, right=0.97, top=0.92, bottom=0.11)
    ok = _draw_residuals(ax, df, time_col, dark=False)

    plot_file = os.path.join(CASE_DIR, "convergence_residuals.png")
    plt.savefig(plot_file, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"   ✓ Plot saved: {plot_file}")

    if not ok:
        return False

    # ── Statistics ────────────────────────────────────────────────────────────
    print("\n📈 Residual Statistics (latest timestep):")
    any_found = False
    for col, sty in RESIDUAL_STYLES.items():
        if col not in df.columns:
            continue
        s = pd.to_numeric(df[col], errors="coerce").dropna()
        s_pos = s[s > 0]
        if len(s) == 0:
            continue
        last = s.iloc[-1]
        minv = s_pos.min() if len(s_pos) else float("nan")
        conv = "✅" if last <= CONVERGENCE_THRESHOLD else "⏳"
        print(f"   {conv} {sty['label']:6s} ({col:20s})  "
              f"latest: {last:.3e}   min: {minv:.3e}")
        any_found = True

    if not any_found:
        print("   ℹ️  No matching residual columns. Available:", list(df.columns[:8]))

    return True


# ═══════════════════════════════════════════════════════════════════════════════
#  LIVE RESIDUAL PLOT
# ═══════════════════════════════════════════════════════════════════════════════

def live_plot_residuals(interval_s: float = 2.0) -> animation.FuncAnimation:
    """
    Open an interactive matplotlib window that refreshes every *interval_s*
    seconds by re-reading solverInfo.dat from disk.

    Close the window or press Ctrl+C to stop.
    """
    residual_file = os.path.join(POST_DIR, "solverInfo", "0", "solverInfo.dat")

    print(f"🔴 LIVE MODE  –  {residual_file}")
    print(f"   Refresh: {interval_s} s  |  close window or Ctrl+C to stop\n")

    # ── Figure setup ──────────────────────────────────────────────────────────
    fig, ax = plt.subplots(figsize=(14, 6.5))
    fig.patch.set_facecolor(DARK_BG)
    ax.set_facecolor(DARK_AX)
    fig.subplots_adjust(left=0.08, right=0.97, top=0.91, bottom=0.11)

    # Persistent footer text (file path + last update)
    footer = fig.text(
        0.01, 0.005,
        f"  {residual_file}",
        fontsize=7, color="#4A4A6A", ha="left", va="bottom",
    )
    # "LIVE" badge
    fig.text(
        0.99, 0.005,
        "● LIVE",
        fontsize=8, color="#E74C3C", ha="right", va="bottom",
        fontweight="bold",
    )

    # ── Animation callback ────────────────────────────────────────────────────
    def update(_frame: int) -> None:
        df = parse_solver_dat(residual_file)
        if df is None or len(df) == 0:
            ax.cla()
            ax.set_facecolor(DARK_AX)
            ax.text(0.5, 0.5, "Waiting for data…",
                    ha="center", va="center", transform=ax.transAxes,
                    fontsize=13, color=DARK_TEXT)
            ax.set_title("Solver Residuals", color="#EEEEFF",
                         fontsize=12, fontweight="bold")
        else:
            time_col = df.columns[0]
            df[time_col] = pd.to_numeric(df[time_col], errors="coerce")
            df.dropna(subset=[time_col], inplace=True)
            _draw_residuals(ax, df, time_col, dark=True)

        # Restore figure-level dark background (ax.cla() can reset it)
        fig.patch.set_facecolor(DARK_BG)
        footer.set_text(
            f"  {residual_file}   ·   last read: "
            f"{datetime.now().strftime('%H:%M:%S')}"
        )
        fig.canvas.draw_idle()

    ani = animation.FuncAnimation(
        fig, update,
        interval=int(interval_s * 1000),
        cache_frame_data=False,
    )

    try:
        plt.show()
    except KeyboardInterrupt:
        print("\n⏹  Live monitoring stopped.")

    return ani  # keep reference so garbage-collector leaves it alive


# ═══════════════════════════════════════════════════════════════════════════════
#  FORCE COEFFICIENTS
# ═══════════════════════════════════════════════════════════════════════════════

def check_forces() -> bool:
    """Plot drag and lift coefficients from postProcessing/forceCoeffs."""
    force_file = os.path.join(POST_DIR, "forceCoeffs", "0", "coefficient.dat")

    if not os.path.exists(force_file):
        print("❌ Force coefficients file not found:", force_file)
        return False

    print("📊 Reading forces from:", force_file)
    try:
        df = pd.read_csv(
            force_file, sep=r"\s+", skiprows=12,
            comment="#", skip_blank_lines=True, engine="python",
        )
        if len(df) == 0:
            print("⚠️  Force file is empty")
            return False

        for col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        df = df.dropna(axis=1, how="all").dropna(axis=0, how="all")

        if len(df) == 0 or len(df.columns) < 2:
            print("⚠️  No valid numeric data in force file")
            return False

        print(f"   ✓ Loaded {len(df)} timesteps")

        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8), sharex=True)
        fig.subplots_adjust(hspace=0.08)

        time = df.iloc[:, 0]
        cd   = df.iloc[:, 1] if len(df.columns) > 1 else None
        cl   = df.iloc[:, 4] if len(df.columns) > 4 else None

        if cd is not None:
            m = cd.notna()
            ax1.plot(time[m], cd[m], color="#3498DB", lw=1.6, label="Cd")
            ax1.set_ylabel("Drag Coefficient  Cd", fontsize=11)
            ax1.set_title("Force Coefficients vs Time", fontsize=12,
                           fontweight="bold")
            ax1.grid(True, ls="--", alpha=0.3)
            ax1.legend(fontsize=9)

        if cl is not None:
            m = cl.notna()
            ax2.plot(time[m], cl[m], color="#E74C3C", lw=1.6, label="Cl")
            ax2.axhline(0, color="#AAAAAA", ls=":", lw=1.0, alpha=0.6)
            ax2.set_xlabel("Time (s)", fontsize=11)
            ax2.set_ylabel("Lift Coefficient  Cl", fontsize=11)
            ax2.grid(True, ls="--", alpha=0.3)
            ax2.legend(fontsize=9)

        plot_file = os.path.join(CASE_DIR, "convergence_forces.png")
        plt.savefig(plot_file, dpi=150, bbox_inches="tight")
        plt.close()
        print(f"   ✓ Force plot saved: {plot_file}")

        print("\n📈 Force Coefficient Statistics:")
        if cd is not None:
            v = cd.dropna()
            if len(v):
                print(f"   Cd mean:  {v.mean():.4f} ± {v.std():.4f}")
                print(f"   Cd range: {v.min():.4f} … {v.max():.4f}")
        if cl is not None:
            v = cl.dropna()
            if len(v):
                print(f"   Cl mean:  {v.mean():.6f}  (should be ~0)")
                print(f"   Cl RMS:   {(v ** 2).mean() ** 0.5:.4f}")
                print(f"   Cl range: {v.min():.4f} … {v.max():.4f}")

        return True

    except Exception as exc:
        print(f"❌ Error reading forces: {exc}")
        return False


# ═══════════════════════════════════════════════════════════════════════════════
#  MASS BALANCE
# ═══════════════════════════════════════════════════════════════════════════════

def check_mass_balance() -> bool:
    """Compare inlet vs outlet mass flow (OpenFOAM sign convention aware)."""
    inlet_file  = os.path.join(POST_DIR, "inMassFlow",  "0", "surfaceFieldValue.dat")
    outlet_file = os.path.join(POST_DIR, "outMassFlow", "0", "surfaceFieldValue.dat")

    if not os.path.exists(inlet_file):
        print("⚠️  Inlet mass flow file not found:", inlet_file)
        return False
    if not os.path.exists(outlet_file):
        print("⚠️  Outlet mass flow file not found:", outlet_file)
        return False

    print("✅ Checking Mass Conservation:")
    try:
        inlet  = pd.read_csv(inlet_file,  sep=r"\s+", skiprows=0)
        outlet = pd.read_csv(outlet_file, sep=r"\s+", skiprows=0)

        for col in inlet.columns:
            inlet[col] = pd.to_numeric(inlet[col], errors="coerce")
        for col in outlet.columns:
            outlet[col] = pd.to_numeric(outlet[col], errors="coerce")

        iv = inlet.iloc[:,  1].dropna()
        ov = outlet.iloc[:, 1].dropna()

        if not len(iv) or not len(ov):
            print("⚠️  No valid data in mass-flow files")
            return False

        i_last, o_last = iv.iloc[-1], ov.iloc[-1]
        i_mag,  o_mag  = abs(i_last), abs(o_last)
        balance = abs(i_mag - o_mag) / i_mag * 100 if i_mag > 1e-12 else 0.0

        print(f"   Inlet  (raw):  {i_last:+.6e} kg/s  (negative = inflow)")
        print(f"   Outlet (raw):  {o_last:+.6e} kg/s  (positive = outflow)")
        print(f"   |Inlet|:       {i_mag:.6e} kg/s")
        print(f"   |Outlet|:      {o_mag:.6e} kg/s")
        print(f"   Imbalance:     {balance:.3f} %")

        if balance < 0.5:
            print("   ✓ Excellent mass conservation!")
        elif balance < 1.0:
            print("   ✓ Mass balance OK")
        elif balance < 5.0:
            print("   ⚠️  Minor imbalance — check mesh quality")
        else:
            print("   ❌ Significant imbalance — check BCs or mesh")

        return balance < 5.0

    except Exception as exc:
        print(f"❌ Error checking mass balance: {exc}")
        import traceback
        traceback.print_exc()
        return False


# ═══════════════════════════════════════════════════════════════════════════════
#  ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════════

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Monitor OpenFOAM CFD convergence",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--residuals", action="store_true",
                        help="Plot residuals to PNG (static)")
    parser.add_argument("--forces",    action="store_true",
                        help="Plot Cd/Cl to PNG (static)")
    parser.add_argument("--mass",      action="store_true",
                        help="Check inlet/outlet mass balance")
    parser.add_argument("--live",      action="store_true",
                        help="Open interactive live residual window")
    parser.add_argument("--interval",  type=float, default=2.0, metavar="SEC",
                        help="Refresh interval for --live  [default: 2.0 s]")
    parser.add_argument("--all",       action="store_true",
                        help="Run all static checks (default when no flag given)")
    args = parser.parse_args()

    # Default to --all when no flag is provided
    if not any([args.residuals, args.forces, args.mass, args.live]):
        args.all = True

    print("=" * 70)
    print("  OpenFOAM Convergence Monitor  v2.0")
    print(f"  {datetime.now().strftime('%Y-%m-%d  %H:%M:%S')}")
    print("=" * 70)

    # ── Live mode blocks until the window is closed ───────────────────────────
    if args.live:
        live_plot_residuals(interval_s=args.interval)
        return

    # ── Static checks ─────────────────────────────────────────────────────────
    results = []

    if args.residuals or args.all:
        print("\n🔍 Checking Residuals…")
        results.append(("Residuals", check_residuals()))

    if args.forces or args.all:
        print("\n🔍 Checking Force Coefficients…")
        results.append(("Forces", check_forces()))

    if args.mass or args.all:
        print("\n🔍 Checking Mass Balance…")
        results.append(("Mass Balance", check_mass_balance()))

    print("\n" + "=" * 70)
    print("  Summary")
    for name, ok in results:
        icon = "✅ PASS" if ok else "❌ FAIL / INCOMPLETE"
        print(f"    {name:20s}: {icon}")
    print("=" * 70)


if __name__ == "__main__":
    main()