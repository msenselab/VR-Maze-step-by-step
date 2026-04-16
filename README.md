# VR-Maze-step-by-step

A minimal, self-contained maze-walking experiment built with
[Ursina Engine](https://www.ursinaengine.org/).
Participants navigate procedurally generated mazes in first-person view,
collect stars, and have their trajectory logged for later analysis.
The code is designed as a step-by-step teaching example for students who
want to build their own VR/3D behavioural experiments in Python.

---

## Quick start

```bash
# 1. Clone the repository
git clone https://github.com/<your-org>/VR-Maze-step-by-step.git
cd VR-Maze-step-by-step

# 2. Create a virtual environment and install dependencies
#    macOS / Linux
./setup_env.sh
source .venv/bin/activate

#    Windows
setup_env.bat
.venv\Scripts\activate

# 3. Run the experiment
python pywalker/Maze_explore.py
```

The setup scripts use [uv](https://github.com/astral-sh/uv) (installed
automatically if missing) and create a `.venv` with `ursina`, `pyserial`,
`pillow`, `pygame`, and `LabJackPython`.

---

## How the experiment works

### State machine

`Maze_explore.py` runs a simple **state machine** that drives every trial
through five phases:

```
INSTRUCTION ─► FIXATION (1 s) ─► TASK ─► FEEDBACK ─► next trial …
                                                        │
                                                   (between blocks)
                                                        ▼
                                                   BLOCK_REST
```

1. **INSTRUCTION** — on-screen text tells the participant which trial and
   condition is coming. Press **Space** to continue.
2. **FIXATION** — a centred "+" cross for 1 second (a trigger is sent
   here for EEG synchronisation).
3. **TASK** — the maze appears. The player moves with **WASD** and looks
   around with the mouse. Gold stars are scattered in the maze; walk close
   to one to collect it. When all stars are collected the trial ends
   automatically. Press **Esc** to skip a trial.
4. **FEEDBACK** — summary screen showing condition, stars collected, and
   time. Press **Space** to advance.
5. **BLOCK_REST** — appears between blocks so the participant can take a
   break.

After all trials the experiment writes a summary and reminds the user
where the data files are saved.

### Trial structure

The experiment runs **3 blocks × 6 trials** (18 trials total).
Each block contains:

| Condition | Maze size | Stars to collect |
|-----------|-----------|-----------------|
| easy      | 6 × 6     | 1               |
| hard      | 6 × 6     | 3               |

Within each block the 3 easy and 3 hard trials are presented in random
order.

### Maze generation

Mazes are generated on the fly using **recursive-backtracking (DFS)**.
Starting from cell (0, 0) the algorithm carves a random spanning tree,
guaranteeing that every cell is reachable through exactly one path.
Interior walls are stored as two boolean grids (`h_walls` for horizontal
segments between rows, `v_walls` for vertical segments between columns).
The `build_maze()` function then converts these grids into 3D box
entities with collision.

### EEG trigger codes

Each experimental event sends a numeric trigger code.
In the teaching version `send_trigger()` simply prints to the console;
for real experiments, replace it with the `EEGTrigger` class in
`trigger.py`, which drives a LabJack U3 via its FIO pins.

| Code | Event                    |
|------|--------------------------|
| 1    | Fixation onset           |
| 2    | Maze start — easy        |
| 3    | Maze start — hard        |
| 4    | Easy: star collected     |
| 5    | Hard: star 1 collected   |
| 6    | Hard: star 2 collected   |
| 7    | Hard: star 3 collected   |
| 8    | Trial complete           |
| 9    | Trial skipped (Esc)      |
| 10   | Block rest start         |
| 11   | Block rest end           |

---

## Output files

Every run produces three CSV files in the working directory:

| File                  | Contents |
|-----------------------|----------|
| `maze_experiment.csv` | One row per trial: block, condition, maze size, stars collected, duration, completion flag |
| `trajectory.csv`      | Player position (x, z) sampled every 0.1 s, plus `collect_*` events when a star is picked up |
| `maze_walls.csv`      | Wall geometry (centre x, z and extents sx, sz) for each trial — used by the trajectory plotter |

---

## Visualising the walking trajectory

After the experiment, use `plot_trajectory.py` to draw bird's-eye
trajectory maps from the logged CSV data:

```bash
# Plot all trials
python pywalker/plot_trajectory.py trajectory.csv

# Plot specific trials
python pywalker/plot_trajectory.py trajectory.csv --trials 1 2

# Save figures as PNG
python pywalker/plot_trajectory.py trajectory.csv --save
```

The script produces three figures:

1. **Per-trial trajectory** — one subplot per trial showing the walking
   path (coloured line), start position (green dot), end position (red
   square), and star-collection events (gold stars with labels).
2. **Overlay plot** — all selected trials superimposed on a single axis
   for direct comparison.
3. **Speed and head-angle time series** — instantaneous speed and
   heading direction over time, with vertical dashed lines marking
   collection events.

---

## Project structure

```
VR-Maze-step-by-step/
├── pywalker/
│   ├── Maze_explore.py      # Main experiment script (run this)
│   ├── maz_parser.py        # Parser for MazeSuite .maz XML files
│   ├── maze_renderer.py     # Ursina renderer for pre-made .maz mazes
│   ├── plot_trajectory.py   # Post-hoc trajectory visualisation
│   ├── trigger.py           # LabJack U3 EEG trigger driver
│   ├── trigger_debug.py     # Debug version (FIO1 LED always on)
│   └── models_compressed/
│       └── star.bam         # 3D star model (Panda3D binary)
├── setup_env.sh             # Environment setup (macOS/Linux)
├── setup_env.bat            # Environment setup (Windows)
├── requirements.txt         # Python dependencies
└── README.md
```

### Module overview

- **`Maze_explore.py`** — the self-contained experiment. Generates a
  random maze, spawns stars, runs the state machine, logs data, and
  cleans up. This is the file to read and modify.
- **`maz_parser.py`** — reads `.maz` XML files exported from
  [MazeSuite](http://www.mazesuite.com/), returning structured
  dataclasses (walls, floors, start positions, dynamic objects, lights).
  Useful when you want to load a hand-designed maze instead of generating
  one procedurally.
- **`maze_renderer.py`** — takes a parsed `MazeData` object and builds
  the full 3D scene in Ursina (walls, floor, skybox, lighting,
  collectibles, gamepad support). Run it standalone with
  `python pywalker/maze_renderer.py some_maze.maz`.
- **`trigger.py`** — production EEG trigger class (`EEGTrigger`) that
  writes N-bit codes to LabJack U3 FIO pins with a configurable pulse
  width. Falls back gracefully to console printing when no hardware is
  attached.
- **`trigger_debug.py`** — variant that forces the FIO1 LED on with
  every pulse so you can visually confirm triggers during hardware
  setup.
- **`plot_trajectory.py`** — reads `trajectory.csv` (and optionally
  `maze_walls.csv`) and produces matplotlib figures of the walking
  paths, speed profiles, and head-direction time series.

---

## Controls

| Key          | Action                    |
|--------------|---------------------------|
| W A S D      | Move forward/left/back/right |
| Mouse        | Look around               |
| Space        | Advance through screens   |
| Esc          | Skip the current trial    |
| Shift + Q    | Quit the application      |

Gamepad input (left stick = move, right stick = look) is supported when
a controller is connected.

---

## License

MIT