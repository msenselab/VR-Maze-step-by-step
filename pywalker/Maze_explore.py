"""Maze Explorer

Procedurally generated maze experiment with trajectory logging:
  - Random maze via recursive backtracking (easy: 5x5, hard: 9x9)
  - State machine: INSTRUCTION -> FIXATION -> TASK -> FEEDBACK -> DONE
  - Player position logged every 0.1 s to trajectory.csv
  - Maze wall geometry saved to maze_walls.csv
  - Open visualize.ipynb after the experiment to plot trajectories

Controls during task:
  WASD        move
  Mouse       look around
  ESC         skip current trial
  Shift+Q     quit
"""

import atexit
import csv
import time as pytime
import random
from ursina import *
from ursina.prefabs.first_person_controller import FirstPersonController

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
CELL         = 5      # world-space units per maze cell (wider corridors)
WALL_HEIGHT  = 5
WALL_THICK   = 0.32
COLLECT_DIST = 2

TRIG_FIXATION         = 1
TRIG_MAZE_START_EASY  = 2
TRIG_MAZE_START_HARD  = 3
TRIG_EASY_STAR_1      = 4
TRIG_HARD_STAR_1      = 5
TRIG_HARD_STAR_2      = 6
TRIG_HARD_STAR_3      = 7
TRIG_TRIAL_COMPLETE   = 8
TRIG_TRIAL_ESCAPE     = 9
TRIG_BLOCK_REST_START = 10
TRIG_BLOCK_REST_END   = 11

N_BLOCKS         = 3
EASY_PER_BLOCK   = 3
HARD_PER_BLOCK   = 3
EASY_ROWS, EASY_COLS = 6, 6
HARD_ROWS, HARD_COLS = 6, 6
HARD_MIN_STAR_CELL_DIST = 3.0


def send_trigger(code: int) -> None:
    """Mock EEG trigger — replace with serial/LabJack for real experiments."""
    print(f'  [TRIGGER] code={code}  t={pytime.time():.3f}')


def star_trigger(condition: str, star_index: int) -> int:
    """Return the condition-specific trigger code for a collected star."""
    if condition == 'easy':
        return TRIG_EASY_STAR_1
    hard_codes = [TRIG_HARD_STAR_1, TRIG_HARD_STAR_2, TRIG_HARD_STAR_3]
    return hard_codes[min(max(star_index, 0), len(hard_codes) - 1)]


def make_star(x: float, z: float) -> Entity:
    """Create a simple 3D-ish star marker from crossed billboard quads."""
    root = Entity(position=(x, 1.1, z))
    Entity(
        parent=root,
        model='quad',
        texture='white_cube',
        color=color.gold,
        scale=0.9,
        billboard=True,
        double_sided=True,
    )
    Entity(
        parent=root,
        model='quad',
        texture='white_cube',
        color=color.yellow,
        scale=0.55,
        rotation_z=45,
        billboard=True,
        double_sided=True,
    )
    return root


# ---------------------------------------------------------------------------
# Maze generation — recursive backtracking (DFS)
# ---------------------------------------------------------------------------

def generate_maze(rows: int, cols: int):
    """Return interior-wall boolean grids for a randomly carved maze.

    h_walls[r][c]  True => wall between row r and row r+1 at column c.
    v_walls[r][c]  True => wall between col c and col c+1 at row r.
    """
    h_walls = [[True] * cols       for _ in range(rows - 1)]
    v_walls = [[True] * (cols - 1) for _ in range(rows)]
    visited = [[False] * cols      for _ in range(rows)]

    def dfs(r, c):
        visited[r][c] = True
        dirs = [(1, 0, 'S'), (-1, 0, 'N'), (0, 1, 'E'), (0, -1, 'W')]
        random.shuffle(dirs)
        for dr, dc, d in dirs:
            nr, nc = r + dr, c + dc
            if 0 <= nr < rows and 0 <= nc < cols and not visited[nr][nc]:
                if   d == 'S': h_walls[r][c]     = False
                elif d == 'N': h_walls[r - 1][c] = False
                elif d == 'E': v_walls[r][c]     = False
                elif d == 'W': v_walls[r][c - 1] = False
                dfs(nr, nc)

    dfs(0, 0)
    return h_walls, v_walls


def cell_center(r, c, rows, cols):
    """World-space (x, z) of cell (r, c) centre."""
    return (
        (c - (cols - 1) / 2.0) * CELL,
        (r - (rows - 1) / 2.0) * CELL,
    )


def cell_distance(a, b):
    """Euclidean distance between two cells in grid coordinates."""
    dr = a[0] - b[0]
    dc = a[1] - b[1]
    return (dr * dr + dc * dc) ** 0.5


def sample_star_cells(all_cells, n_stars, condition):
    """Sample star cells; enforce a wider spread for hard condition."""
    if condition != 'hard' or n_stars <= 1:
        return random.sample(all_cells, n_stars)

    # Retry randomized sampling first.
    for _ in range(200):
        picks = random.sample(all_cells, n_stars)
        ok = True
        for i in range(len(picks)):
            for j in range(i + 1, len(picks)):
                if cell_distance(picks[i], picks[j]) < HARD_MIN_STAR_CELL_DIST:
                    ok = False
                    break
            if not ok:
                break
        if ok:
            return picks

    # Fallback: greedily maximize spacing if random retries fail.
    picks = [random.choice(all_cells)]
    while len(picks) < n_stars:
        best_cell = None
        best_score = -1.0
        for cand in all_cells:
            if cand in picks:
                continue
            score = min(cell_distance(cand, p) for p in picks)
            if score > best_score:
                best_score = score
                best_cell = cand
        if best_cell is None:
            break
        picks.append(best_cell)
    return picks


# ---------------------------------------------------------------------------
# Maze scene builder
# ---------------------------------------------------------------------------

def build_maze(rows: int, cols: int, h_walls, v_walls):
    """Instantiate Ursina wall entities.

    Returns:
        entities   -- list of Entity objects (pass to destroy() on teardown)
        wall_recs  -- list of (x, z, sx, sz) for the visualiser CSV
    """
    entities  = []
    wall_recs = []
    hw = cols * CELL / 2.0
    hh = rows * CELL / 2.0

    def make_wall(x, z, sx, sz):
        e = Entity(
            model='cube',
            position=(x, WALL_HEIGHT / 2, z),
            scale=(sx, WALL_HEIGHT, sz),
            color=color.light_gray,
            texture='grass',
            collider='box',
        )
        entities.append(e)
        wall_recs.append((x, z, sx, sz))

    # Outer boundary
    span_x = cols * CELL + WALL_THICK
    span_z = rows * CELL + WALL_THICK
    make_wall( 0,  -hh,  span_x, WALL_THICK)  # north
    make_wall( 0,   hh,  span_x, WALL_THICK)  # south
    make_wall(-hw,   0, WALL_THICK,  span_z)  # west
    make_wall( hw,   0, WALL_THICK,  span_z)  # east

    # Interior horizontal walls (east-west segments, between rows)
    for r in range(rows - 1):
        wz = (r - (rows - 1) / 2.0 + 0.5) * CELL
        for c in range(cols):
            if h_walls[r][c]:
                wx, _ = cell_center(r, c, rows, cols)
                make_wall(wx, wz, CELL + WALL_THICK, WALL_THICK)

    # Interior vertical walls (north-south segments, between columns)
    for r in range(rows):
        _, wz = cell_center(r, 0, rows, cols)
        for c in range(cols - 1):
            if v_walls[r][c]:
                wx = (c - (cols - 1) / 2.0 + 0.5) * CELL
                make_wall(wx, wz, WALL_THICK, CELL + WALL_THICK)

    # Floor
    floor = Entity(
        model='quad',
        scale=(cols * CELL, rows * CELL),
        rotation_x=90,
        color=color.dark_gray,
        texture='grass',
        collider='box',
    )
    entities.append(floor)

    return entities, wall_recs


# ---------------------------------------------------------------------------
# Experiment controller
# ---------------------------------------------------------------------------

class Experiment(Entity):
    """State machine: INSTRUCTION -> FIXATION -> TASK -> FEEDBACK -> DONE."""

    @staticmethod
    def _build_trials():
        """Build 3 blocks x 6 trials: 3 easy + 3 hard, randomized in each block."""
        trials = []
        for block in range(1, N_BLOCKS + 1):
            block_trials = [
                {
                    'condition': 'easy',
                    'rows': EASY_ROWS,
                    'cols': EASY_COLS,
                    'n_stars': 1,
                    'block': block,
                }
                for _ in range(EASY_PER_BLOCK)
            ]
            block_trials.extend([
                {
                    'condition': 'hard',
                    'rows': HARD_ROWS,
                    'cols': HARD_COLS,
                    'n_stars': 3,
                    'block': block,
                }
                for _ in range(HARD_PER_BLOCK)
            ])
            random.shuffle(block_trials)
            trials.extend(block_trials)
        return trials

    def __init__(self):
        super().__init__()

        self.trials        = self._build_trials()
        self.current_trial = 0
        self.state         = 'INSTRUCTION'
        self.score         = 0
        self.stars         = []
        self.room_ents     = []
        self._recording    = False
        self.trial_t0      = 0.0
        self._rest_next_block = None

        # Open CSV files
        self._exp_file   = open('maze_experiment.csv', 'w', newline='')
        self._traj_file  = open('trajectory.csv',      'w', newline='')
        self._walls_file = open('maze_walls.csv',      'w', newline='')

        self._exp_w   = csv.writer(self._exp_file)
        self._traj_w  = csv.writer(self._traj_file)
        self._walls_w = csv.writer(self._walls_file)

        atexit.register(self._flush_all)

        self._exp_w.writerow([
            'trial', 'block', 'condition', 'rows', 'cols',
            'n_stars', 'collected', 'duration_s', 'completed',
        ])
        self._traj_w.writerow(['trial', 'time_s', 'x', 'z', 'event'])
        self._walls_w.writerow(['trial', 'x', 'z', 'sx', 'sz'])

        # Player (stays disabled until TASK phase)
        self.player = FirstPersonController(enabled=False)
        self.player.gravity = 1
        self.player.cursor.visible = False
        self.player.speed = 6
        self.player.mouse_sensitivity = Vec2(60, 60)
        # Prevent near-plane clipping artifacts when camera gets close to walls.
        camera.clip_plane_near = 0.005

        # Persistent scene elements
        Sky()
        sun = DirectionalLight(shadows=False)
        sun.look_at(Vec3(1, -1, -1))
        AmbientLight(color=color.rgba(0.3, 0.3, 0.3, 1))

        # HUD
        self.msg_text   = Text(text='', origin=(0, 0),          scale=2, parent=camera.ui)
        self.score_text = Text(text='', position=(-0.85, 0.45), scale=2, parent=camera.ui)

        self.show_instruction()

    # ------------------------------------------------------------------
    def show_instruction(self):
        self.state = 'INSTRUCTION'
        t = self.trials[self.current_trial]
        n = t['n_stars']
        self.msg_text.text = (
            f"Trial {self.current_trial + 1} of {len(self.trials)}\n"
            f"Block: {t['block']}/{N_BLOCKS}\n"
            f"Condition: {t['condition']}  "
            f"({n} star{'s' if n > 1 else ''})\n\n"
            f"WASD — move     Mouse — look\n"
            f"ESC — skip trial\n\n"
            f"Press SPACE to start"
        )
        self.player.enabled = False
        mouse.locked = False

    # ------------------------------------------------------------------
    def show_fixation(self):
        self.state = 'FIXATION'
        self.msg_text.text = '+'
        send_trigger(TRIG_FIXATION)
        invoke(self.start_task, delay=1)

    # ------------------------------------------------------------------
    def show_block_rest(self, next_block: int):
        self.state = 'BLOCK_REST'
        self._rest_next_block = next_block
        self.msg_text.text = (
            f"Block {next_block - 1} complete.\n\n"
            f"Take a short rest.\n"
            f"Press SPACE to start Block {next_block}."
        )
        send_trigger(TRIG_BLOCK_REST_START)
        self.player.enabled = False
        mouse.locked = False

    # ------------------------------------------------------------------
    def start_task(self):
        self.state = 'TASK'
        self.msg_text.text = ''

        t = self.trials[self.current_trial]
        rows, cols = t['rows'], t['cols']

        # Generate and build maze
        h_walls, v_walls = generate_maze(rows, cols)
        self.room_ents, wall_recs = build_maze(rows, cols, h_walls, v_walls)

        # Log wall geometry for the visualiser
        for (wx, wz, sx, sz) in wall_recs:
            self._walls_w.writerow([self.current_trial + 1, wx, wz, sx, sz])
        self._walls_file.flush()

        # Spawn stars at random non-start cell centres
        all_cells  = [(r, c) for r in range(rows) for c in range(cols)
                      if (r, c) != (0, 0)]
        star_cells = sample_star_cells(all_cells, t['n_stars'], t['condition'])
        self.stars = []
        for (r, c) in star_cells:
            sx, sz = cell_center(r, c, rows, cols)
            star = make_star(sx, sz)
            self.stars.append(star)

        self.score = 0
        self.score_text.text = f"Stars: 0/{t['n_stars']}"

        # Place player at cell (0, 0)
        px, pz = cell_center(0, 0, rows, cols)
        self.player.position   = Vec3(px, 2.0, pz)
        self.player.rotation_y = 45
        self.player.enabled    = True
        mouse.locked = True

        self.trial_t0   = pytime.time()
        self._recording = True
        invoke(self._record_traj, delay=0.1)
        if t['condition'] == 'easy':
            send_trigger(TRIG_MAZE_START_EASY)
        else:
            send_trigger(TRIG_MAZE_START_HARD)

    # ------------------------------------------------------------------
    def _record_traj(self):
        if not self._recording:
            return
        self._traj_w.writerow([
            self.current_trial + 1,
            round(pytime.time() - self.trial_t0, 2),
            round(self.player.position.x, 2),
            round(self.player.position.z, 2),
            '',
        ])
        invoke(self._record_traj, delay=0.1)

    # ------------------------------------------------------------------
    def end_task(self, completed: bool):
        self._recording = False
        duration = pytime.time() - self.trial_t0
        t = self.trials[self.current_trial]

        self._exp_w.writerow([
            self.current_trial + 1, t['block'], t['condition'],
            t['rows'], t['cols'], t['n_stars'],
            self.score, f'{duration:.3f}', int(completed),
        ])
        self._exp_file.flush()
        self._traj_file.flush()
        if completed:
            send_trigger(TRIG_TRIAL_COMPLETE)
        else:
            send_trigger(TRIG_TRIAL_ESCAPE)

        for e in self.stars + self.room_ents:
            destroy(e)
        self.stars, self.room_ents = [], []

        self.player.enabled  = False
        self.score_text.text = ''
        mouse.locked = False

        self.show_feedback(t, duration, completed)

    # ------------------------------------------------------------------
    def show_feedback(self, trial, duration, completed):
        self.state = 'FEEDBACK'
        status = 'Complete!' if completed else 'Skipped'
        self.msg_text.text = (
            f"{status}\n"
            f"Condition: {trial['condition']}\n"
            f"Stars: {self.score}/{trial['n_stars']}\n"
            f"Time: {duration:.1f} s\n\n"
            f"Press SPACE to continue"
        )

    # ------------------------------------------------------------------
    def next_trial(self):
        self.msg_text.text = ''
        finished_block = self.trials[self.current_trial]['block']
        self.current_trial += 1
        if self.current_trial < len(self.trials):
            next_block = self.trials[self.current_trial]['block']
            if next_block != finished_block:
                self.show_block_rest(next_block)
            else:
                self.show_instruction()
        else:
            self.show_done()

    # ------------------------------------------------------------------
    def _flush_all(self):
        """Flush and close all CSV files — called on exit regardless of state."""
        for f in (self._exp_file, self._traj_file, self._walls_file):
            try:
                f.flush()
                f.close()
            except Exception:
                pass

    def show_done(self):
        self.state = 'DONE'
        self.msg_text.text = (
            "Experiment complete!\n\n"
            "Files saved:\n"
            "  maze_experiment.csv\n"
            "  trajectory.csv\n"
            "  maze_walls.csv\n\n"
            "Open visualize.ipynb to plot trajectories\n"
            "Press Shift+Q to exit"
        )
        for f in (self._exp_file, self._traj_file, self._walls_file):
            f.close()

    # ------------------------------------------------------------------
    def update(self):
        if self.state != 'TASK':
            return
        t = self.trials[self.current_trial]
        for star in self.stars:
            if star.enabled:
                star.rotation_y += 1.2
            if star.enabled and distance(self.player.position, star.position) < COLLECT_DIST:
                star.enabled = False
                self.score  += 1
                t_s = round(pytime.time() - self.trial_t0, 2)
                self._traj_w.writerow([
                    self.current_trial + 1, t_s,
                    round(self.player.position.x, 2),
                    round(self.player.position.z, 2),
                    f"collect_{self.score}",
                ])
                self.score_text.text = f"Stars: {self.score}/{t['n_stars']}"
                send_trigger(star_trigger(t['condition'], self.score - 1))
        if self.score >= t['n_stars']:
            self.end_task(completed=True)

    # ------------------------------------------------------------------
    def input(self, key):
        if key == 'space':
            if self.state == 'INSTRUCTION':
                self.show_fixation()
            elif self.state == 'FEEDBACK':
                self.next_trial()
            elif self.state == 'BLOCK_REST':
                send_trigger(TRIG_BLOCK_REST_END)
                self._rest_next_block = None
                self.show_instruction()
        elif key == 'left mouse down' and self.state == 'TASK':
            mouse.locked = True
        elif key == 'escape' and self.state == 'TASK':
            self.end_task(completed=False)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
app = Ursina()
experiment = Experiment()
app.run()
