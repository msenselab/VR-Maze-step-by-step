"""
Ursina-based 3D maze renderer.

Loads a MazeData object (from maz_parser) and renders it as a walkable
first-person 3D environment.

Template: D:/vr-tutorial/maze_explorer/maze_explorer.py
  - cube walls with WALL_THICK, texture_scale for correct tiling
  - DirectionalLight + AmbientLight (no unlit=True)
  - camera_pivot.y=0.2, player at y=0 (walls span y=-1..+1)
  - Sky(texture=...) for custom skybox
"""

from ursina import (
    Entity, Vec3 as UVec3, Mesh, color, camera, application, load_model, load_texture,
    held_keys, Text, invoke, destroy, mouse, AmbientLight, DirectionalLight,
)
from ursina.prefabs.first_person_controller import FirstPersonController
from ursina.prefabs.sky import Sky
import math
import sys
import os
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from pywalker.maz_parser import parse_maz, resolve_assets, MazeData

# Wall solid thickness (like maze_explorer WALL_THICK)
WALL_THICK = 0.3

# Track all scene entities for cleanup between trials
_scene_entities = []


def _track(entity):
    """Register an entity for later cleanup."""
    _scene_entities.append(entity)
    return entity


def clear_maze_scene():
    """Destroy all maze entities (walls, floor, lights, skybox, player). Call between trials."""
    for e in _scene_entities:
        try:
            destroy(e)
        except Exception:
            pass
    _scene_entities.clear()


def _load_tex(path: Path) -> object:
    """Load a texture from an absolute path via asset_folder swap."""
    old = application.asset_folder
    application.asset_folder = path.parent
    tex = load_texture(path.name)
    application.asset_folder = old
    return tex


def load_textures(maze_data: MazeData) -> dict:
    """Load all image assets; return {image_id: texture}."""
    textures = {}
    for img_id, path in maze_data.image_paths.items():
        if not path.exists():
            print(f"  [skip] Missing file: {path}")
            continue
        tex = _load_tex(path)
        if tex:
            textures[img_id] = tex
            print(f"  [ok] Loaded texture: {path.name}")
        else:
            print(f"  [warn] load_texture returned None: {path.name}")
    return textures


def _fix_mtl_tabs(obj_path: Path):
    """Replace tab-separated values in MTL files (Ursina parser workaround)."""
    with open(obj_path) as f:
        for line in f:
            if line.strip().startswith('mtllib'):
                mtl_name = line.strip().split(None, 1)[1]
                mtl_path = obj_path.parent / mtl_name
                if mtl_path.exists():
                    text = mtl_path.read_text()
                    if '\t' in text:
                        mtl_path.write_text(text.replace('\t', ' '))
                break


def _obj_bounds(obj_path: Path) -> tuple:
    """Return (max_extent, min_y) from OBJ vertex data."""
    xs, ys, zs = [], [], []
    with open(obj_path) as f:
        for line in f:
            if line.startswith('v '):
                parts = line.split()
                xs.append(float(parts[1]))
                ys.append(float(parts[2]))
                zs.append(float(parts[3]))
    if not xs:
        return 1.0, 0.0
    extent = max(max(xs) - min(xs), max(ys) - min(ys), max(zs) - min(zs))
    return extent, min(ys)


def load_obj_model(model_path: Path):
    """Load OBJ; return (mesh, normalize_factor, min_y) or (None, 1.0, 0.0)."""
    try:
        _fix_mtl_tabs(model_path)
        old = application.asset_folder
        application.asset_folder = model_path.parent
        mdl = load_model(model_path.stem)
        application.asset_folder = old
        if mdl:
            extent, min_y = _obj_bounds(model_path)
            norm = 1.0 / extent if extent > 0 else 1.0
            print(f"  [ok] Loaded model: {model_path.name} (norm={norm:.4f})")
            return mdl, norm, min_y
        print(f"  [warn] load_model returned None: {model_path.name}")
        return None, 1.0, 0.0
    except Exception as e:
        print(f"  [warn] Failed to load model {model_path.name}: {e}")
        return None, 1.0, 0.0


def build_curved_wall(cw, texture, wall_color):
    """Create an Entity for a CurvedWall using its geometry vertices and triangle indices."""
    if not cw.geometry_verts or not cw.indices:
        return

    verts = [UVec3(v.x, v.y, v.z) for v in cw.geometry_verts]
    uvs = cw.geometry_uvs if cw.geometry_uvs else None

    if texture is not None:
        col = color.white
    else:
        col = color.rgb(
            int(wall_color.r * 180),
            int(wall_color.g * 200),
            int(wall_color.b * 160),
        )

    # Front face
    mesh = Mesh(vertices=verts, uvs=uvs, triangles=cw.indices, mode='triangle')
    e = _track(Entity(model=mesh, texture=texture, color=col, collider='mesh'))
    e.collider = 'mesh'

    # Back face (reverse winding for double-sided rendering)
    back_tris = []
    for i in range(0, len(cw.indices), 3):
        if i + 2 < len(cw.indices):
            back_tris.extend([cw.indices[i], cw.indices[i+2], cw.indices[i+1]])
    mesh_back = Mesh(vertices=verts, uvs=uvs, triangles=back_tris, mode='triangle')
    _track(Entity(model=mesh_back, texture=texture, color=col))


def build_maze_scene(maze_data: MazeData):
    """Build all Ursina entities from parsed maze data. Returns (player, collectibles)."""

    # ------------------------------------------------------------------
    # Textures
    # ------------------------------------------------------------------
    textures = load_textures(maze_data)
    print(f"Loaded {len(textures)}/{len(maze_data.image_paths)} textures")

    # Defaults: fall back to Ursina built-ins
    _wall_tex  = textures.get(102) or 'brick'   # wall_hedge.jpg
    _floor_tex = textures.get(101) or 'grass'   # ground_grass.jpg
    _sky_tex   = textures.get(maze_data.settings.skybox_id)  # skybox2.jpg

    # ------------------------------------------------------------------
    # Lighting (maze_explorer pattern: DirectionalLight + AmbientLight)
    # ------------------------------------------------------------------
    sun = _track(DirectionalLight(shadows=False))
    sun.look_at(UVec3(1, -1, -1))
    _track(AmbientLight(color=color.rgba(0.5, 0.5, 0.5, 1)))

    # ------------------------------------------------------------------
    # Walls — solid cubes (maze_explorer style), one entity per wall
    # texture_scale=(width, height) tiles texture every 1 world unit
    # ------------------------------------------------------------------
    wall_count = 0
    for wall in maze_data.walls:
        if not wall.visible or len(wall.vertices) < 4:
            continue

        v = wall.vertices
        cx = sum(p.x for p in v) / 4
        cy = sum(p.y for p in v) / 4
        cz = sum(p.z for p in v) / 4

        # Horizontal extent (bottom edge)
        dx = v[1].x - v[2].x
        dz = v[1].z - v[2].z
        width = math.sqrt(dx * dx + dz * dz)

        # Vertical extent
        height = abs(v[0].y - v[1].y)
        if height < 0.01:
            height = 2.0

        # Y-axis rotation
        angle_y = -math.degrees(math.atan2(dx, dz))

        tex = textures.get(wall.texture_id) or _wall_tex

        _track(Entity(
            model='cube',
            position=(cx, cy, cz),
            scale=(width, height, WALL_THICK),
            rotation_y=angle_y,
            texture=tex,
            texture_scale=(width, height),
            collider='box',
        ))
        wall_count += 1

    # --- Curved walls (boundary arcs) ---
    curved_count = 0
    for cw in maze_data.curved_walls:
        if cw.visible:
            tex = textures.get(cw.texture_id) or _wall_tex
            build_curved_wall(cw, tex, cw.color)
            curved_count += 1

    print(f"Built {wall_count} walls + {curved_count} curved walls")

    # ------------------------------------------------------------------
    # Floor — quad with texture_scale for correct tiling
    # ------------------------------------------------------------------
    for floor in maze_data.floors:
        if not floor.visible or len(floor.vertices) < 4:
            continue
        v = floor.vertices
        xs = [p.x for p in v]
        zs = [p.z for p in v]
        cx = (min(xs) + max(xs)) / 2
        cz = (min(zs) + max(zs)) / 2
        sx = max(xs) - min(xs)
        sz = max(zs) - min(zs)
        floor_tex = textures.get(floor.texture_id) or _floor_tex
        _track(Entity(
            model='quad',
            position=(cx, v[0].y, cz),
            scale=(sx, sz),
            rotation_x=90,
            texture=floor_tex,
            texture_scale=(sx, sz),
            collider='box',
        ))

    # ------------------------------------------------------------------
    # Collectibles (dynamic objects) — star.obj or gold sphere fallback
    # ------------------------------------------------------------------
    # Pre-load unique models
    loaded_models = {}
    for dobj in maze_data.dynamic_objects:
        mid = dobj.model_id
        if mid not in loaded_models:
            model_path = maze_data.model_paths.get(mid)
            if model_path:
                loaded_models[mid] = load_obj_model(model_path)
            else:
                loaded_models[mid] = (None, 1.0, 0.0)

    collectibles = []
    for dobj in maze_data.dynamic_objects:
        if dobj.points_granted <= 0:
            continue

        # Reload model per instance so individual destroy() works
        mid = dobj.model_id
        model_path = maze_data.model_paths.get(mid)
        mdl = None
        if model_path:
            old = application.asset_folder
            application.asset_folder = model_path.parent
            mdl = load_model(model_path.stem)
            application.asset_folder = old

        _, norm, min_y = loaded_models.get(mid, (None, 1.0, 0.0))

        if mdl is not None:
            s = dobj.scale * norm
            y_off = -min_y * s
            e = _track(Entity(
                model=mdl,
                color=color.gold,
                scale=s,
                position=(dobj.position.x, dobj.position.y + y_off, dobj.position.z),
                rotation=(dobj.rotation.x, dobj.rotation.y, dobj.rotation.z),
            ))
        else:
            e = _track(Entity(
                model='sphere',
                color=color.gold,
                scale=0.7,
                position=(dobj.position.x, dobj.position.y + 0.3, dobj.position.z),
            ))
        collectibles.append((e, dobj))

    # ------------------------------------------------------------------
    # Skybox — Sky() with custom texture if available
    # ------------------------------------------------------------------
    if _sky_tex:
        _track(Sky(texture=_sky_tex))
        print("  Skybox: skybox2.jpg")
    else:
        _track(Sky())
        print("  Skybox: built-in")

    # ------------------------------------------------------------------
    # Player — maze_explorer pattern
    #   Walls span y=-1..+1; player at y=0; camera_pivot.y=0.2
    #   → camera at y=0.2 (slightly above wall mid-point)
    # ------------------------------------------------------------------
    start_x, start_z = 12.0, 12.0
    start_angle = 0.0
    if maze_data.start_positions:
        sp = maze_data.start_positions[0]
        start_x, start_z = sp.position.x, sp.position.z
        start_angle = sp.angle

    # Auto-face toward maze center when angle=0
    if start_angle == 0 and maze_data.floors:
        fv = maze_data.floors[0].vertices
        fcx = sum(p.x for p in fv) / len(fv)
        fcz = sum(p.z for p in fv) / len(fv)
        start_angle = math.degrees(math.atan2(fcx - start_x, fcz - start_z))

    player = FirstPersonController()
    player.gravity = 0
    player.cursor.visible = False
    player.camera_pivot.y = 0.2   # slightly above y=0 mid-wall
    player.speed = maze_data.settings.move_speed
    player.position = UVec3(start_x, 0, start_z)
    player.rotation_y = start_angle
    mouse.locked = True

    # Use maze file FOV (45°)
    camera.fov = maze_data.settings.field_of_view

    # Track player last so cursor is still alive when player.on_disable runs
    _track(player)
    _track(player.cursor)

    # ------------------------------------------------------------------
    # Gamepad support via pygame
    # ------------------------------------------------------------------
    import pygame
    pygame.init()
    pygame.joystick.init()
    _joystick = None
    if pygame.joystick.get_count() > 0:
        _joystick = pygame.joystick.Joystick(0)
        _joystick.init()
        print(f"  Gamepad: {_joystick.get_name()} ({_joystick.get_numaxes()} axes)")
    else:
        print("  No gamepad detected")

    from ursina import time as ursina_time
    STICK_DEADZONE = 0.2
    LOOK_SPEED = 3.0
    _original_update = player.update

    def _gamepad_update():
        _original_update()
        if _joystick is None:
            return
        pygame.event.pump()

        lx = _joystick.get_axis(0)
        ly = _joystick.get_axis(1)
        if abs(lx) > STICK_DEADZONE or abs(ly) > STICK_DEADZONE:
            from ursina import raycast, Vec3
            move_dir = (
                player.forward * (-ly) + player.right * lx
            ).normalized()
            pos = player.position + Vec3(0, 1, 0)
            if not raycast(pos, move_dir, distance=0.5,
                           traverse_target=player.traverse_target,
                           ignore=player.ignore_list).hit:
                player.position += move_dir * ursina_time.dt * player.speed

        rx = _joystick.get_axis(2) if _joystick.get_numaxes() > 2 else 0
        ry = _joystick.get_axis(3) if _joystick.get_numaxes() > 3 else 0
        if abs(rx) > STICK_DEADZONE:
            player.rotation_y += rx * LOOK_SPEED
        if abs(ry) > STICK_DEADZONE:
            from ursina import clamp
            player.camera_pivot.rotation_x += ry * LOOK_SPEED
            player.camera_pivot.rotation_x = clamp(player.camera_pivot.rotation_x, -90, 90)

    player.update = _gamepad_update

    return player, collectibles


def run_maze(maz_filepath: str):
    """Load a .maz file and run the interactive 3D maze (standalone mode)."""
    from ursina import Ursina, window
    maze_data = parse_maz(maz_filepath)
    resolve_assets(maze_data, maz_filepath)

    print(f"Loaded maze: {len(maze_data.walls)} walls, {len(maze_data.floors)} floors")
    if maze_data.start_positions:
        sp = maze_data.start_positions[0]
        print(f"Start: ({sp.position.x:.1f}, {sp.position.z:.1f}) angle={sp.angle}")

    app = Ursina(title='MazeWalker-Py', borderless=False, size=(1024, 768))
    window.fps_counter.enabled = True

    player, collectibles = build_maze_scene(maze_data)

    exit_threshold = maze_data.settings.exit_threshold
    state = {'points': 0, 'completed': False}

    if maze_data.settings.start_message:
        msg = Text(text=maze_data.settings.start_message, origin=(0, 0), scale=1.5, color=color.white)
        invoke(destroy, msg, delay=3)

    score_text = Text(
        text=f'Stars: 0 / {exit_threshold}',
        position=(-0.85, 0.45), scale=1.5, color=color.yellow,
    )

    class GameUpdater(Entity):
        def update(self):
            for item in collectibles[:]:
                entity, dobj = item
                dx = player.x - entity.x
                dz = player.z - entity.z
                if math.sqrt(dx * dx + dz * dz) < dobj.trigger_radius:
                    state['points'] += dobj.points_granted
                    score_text.text = f'Stars: {state["points"]} / {exit_threshold}'
                    destroy(entity)
                    collectibles.remove(item)
                    print(f'  Collected! {state["points"]}/{exit_threshold}')
                    if state['points'] >= exit_threshold and not state['completed']:
                        state['completed'] = True
                        score_text.text = f'COMPLETE! All {exit_threshold} collected!'
                        score_text.color = color.lime
            if held_keys['escape']:
                application.quit()

    GameUpdater()
    app.run()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python maze_renderer.py <file.maz>")
        sys.exit(1)
    run_maze(sys.argv[1])
