"""
Visualize maze walking trajectories from experiment CSV data.

Usage:
  python pywalker/plot_trajectory.py data/20260321_170419_trajectory.csv
  python pywalker/plot_trajectory.py data/20260321_170419_trajectory.csv --trials 1
  python pywalker/plot_trajectory.py data/20260321_170419_trajectory.csv --trials 1 2
"""

import argparse
import sys
from pathlib import Path

import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.cm as cm
import numpy as np


def plot_trajectories(traj_path: str, trial_nums: list[int] = None, save: bool = False):
    """Plot 2D bird's-eye trajectories (x, z) with collection events marked."""
    df = pd.read_csv(traj_path)

    # Filter trials
    available = sorted(df['trial'].unique())
    if trial_nums:
        df = df[df['trial'].isin(trial_nums)]
        if df.empty:
            print(f"No data for trials {trial_nums}. Available: {available}")
            return
    trials = sorted(df['trial'].unique())
    n_trials = len(trials)

    # Color palette
    colors = cm.Set2(np.linspace(0, 1, max(n_trials, 3)))

    # --- Figure 1: Trajectories ---
    fig, axes = plt.subplots(1, n_trials, figsize=(5 * n_trials, 5), squeeze=False)
    fig.suptitle('Walking Trajectories (bird\'s-eye view)', fontsize=14, y=1.02)

    for i, trial in enumerate(trials):
        ax = axes[0, i]
        td = df[df['trial'] == trial]
        maze_name = td['maze'].iloc[0]

        # Path
        ax.plot(td['x'], td['z'], color=colors[i], linewidth=0.8, alpha=0.7)

        # Start point
        ax.plot(td['x'].iloc[0], td['z'].iloc[0], 'o',
                color='green', markersize=10, zorder=5, label='Start')

        # End point
        ax.plot(td['x'].iloc[-1], td['z'].iloc[-1], 's',
                color='red', markersize=10, zorder=5, label='End')

        # Collection events
        events = td[td['event'].notna() & (td['event'] != '')]
        for _, ev in events.iterrows():
            ax.plot(ev['x'], ev['z'], '*',
                    color='gold', markersize=15, markeredgecolor='black',
                    markeredgewidth=0.5, zorder=6)
            ax.annotate(ev['event'], (ev['x'], ev['z']),
                       textcoords='offset points', xytext=(8, 8),
                       fontsize=8, color='darkgoldenrod')

        ax.set_title(f'Trial {trial}: {maze_name}', fontsize=11)
        ax.set_xlabel('x')
        ax.set_ylabel('z')
        ax.set_aspect('equal')
        ax.legend(fontsize=8, loc='upper right')
        ax.grid(True, alpha=0.3)

    plt.tight_layout()

    # --- Figure 2: Overlaid trajectories ---
    if n_trials > 1:
        fig2, ax2 = plt.subplots(figsize=(6, 6))
        for i, trial in enumerate(trials):
            td = df[df['trial'] == trial]
            maze_name = td['maze'].iloc[0]
            ax2.plot(td['x'], td['z'], color=colors[i], linewidth=0.8,
                     alpha=0.7, label=f'Trial {trial} ({maze_name})')
            ax2.plot(td['x'].iloc[0], td['z'].iloc[0], 'o',
                     color=colors[i], markersize=8)

        ax2.set_title('All Trajectories Overlaid')
        ax2.set_xlabel('x')
        ax2.set_ylabel('z')
        ax2.set_aspect('equal')
        ax2.legend(fontsize=9)
        ax2.grid(True, alpha=0.3)
        plt.tight_layout()

    # --- Figure 3: Speed and angle over time ---
    fig3, axes3 = plt.subplots(2, 1, figsize=(10, 5), sharex=True)
    for i, trial in enumerate(trials):
        td = df[df['trial'] == trial].copy()
        maze_name = td['maze'].iloc[0]
        t = td['time_s'].values
        x = td['x'].values
        z = td['z'].values

        # Speed: distance per time step
        dx = np.diff(x)
        dz = np.diff(z)
        dt = np.diff(t)
        dt[dt == 0] = 1e-6  # avoid division by zero
        speed = np.sqrt(dx**2 + dz**2) / dt
        t_mid = (t[:-1] + t[1:]) / 2

        axes3[0].plot(t_mid, speed, color=colors[i], linewidth=0.5,
                      alpha=0.6, label=f'Trial {trial}')

        # Head angle
        axes3[1].plot(t, td['angle'].values, color=colors[i], linewidth=0.5,
                      alpha=0.6, label=f'Trial {trial}')

        # Mark collections
        events = td[td['event'].notna() & (td['event'] != '')]
        for _, ev in events.iterrows():
            axes3[0].axvline(ev['time_s'], color=colors[i], alpha=0.3, linestyle='--')
            axes3[1].axvline(ev['time_s'], color=colors[i], alpha=0.3, linestyle='--')

    axes3[0].set_ylabel('Speed (units/s)')
    axes3[0].legend(fontsize=8)
    axes3[0].set_ylim(0, None)
    axes3[0].grid(True, alpha=0.3)
    axes3[1].set_ylabel('Head angle (°)')
    axes3[1].set_xlabel('Time (s)')
    axes3[1].legend(fontsize=8)
    axes3[1].grid(True, alpha=0.3)
    fig3.suptitle('Speed and Head Direction Over Time', fontsize=13)
    plt.tight_layout()

    if save:
        out_dir = Path(traj_path).parent
        stem = Path(traj_path).stem
        fig.savefig(out_dir / f'{stem}_paths.png', dpi=150, bbox_inches='tight')
        if n_trials > 1:
            fig2.savefig(out_dir / f'{stem}_overlay.png', dpi=150, bbox_inches='tight')
        fig3.savefig(out_dir / f'{stem}_speed.png', dpi=150, bbox_inches='tight')
        print(f"Saved figures to {out_dir}/")

    plt.show()


def main():
    parser = argparse.ArgumentParser(description='Visualize maze trajectory data')
    parser.add_argument('csv', help='Path to trajectory CSV file')
    parser.add_argument('--trials', nargs='+', type=int, default=None,
                        help='Trial numbers to plot (default: all)')
    parser.add_argument('--save', action='store_true',
                        help='Save figures as PNG files')
    args = parser.parse_args()

    plot_trajectories(args.csv, trial_nums=args.trials, save=args.save)


if __name__ == '__main__':
    main()
