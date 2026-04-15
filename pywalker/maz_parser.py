"""
Parser for MazeSuite .maz XML files.

Extracts walls, floors, start positions, end regions, active regions,
dynamic objects, lights, and global settings from MazeSuite XML maze files.
"""

import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Vec3:
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0


@dataclass
class Color:
    r: float = 1.0
    g: float = 1.0
    b: float = 1.0


@dataclass
class Wall:
    id: int = 0
    label: str = ""
    vertices: list = field(default_factory=list)  # list of 4 Vec3 (flat walls)
    texture_id: int = 0
    color: Color = field(default_factory=Color)
    visible: bool = True


@dataclass
class CurvedWall:
    id: int = 0
    label: str = ""
    geometry_verts: list = field(default_factory=list)  # list of Vec3 (all vertices)
    geometry_uvs: list = field(default_factory=list)    # list of (u, v) per vertex
    indices: list = field(default_factory=list)          # triangle indices
    texture_id: int = 0
    color: Color = field(default_factory=Color)
    visible: bool = True


@dataclass
class Floor:
    id: int = 0
    vertices: list = field(default_factory=list)  # list of 4 Vec3
    texture_id: int = 0
    color: Color = field(default_factory=Color)
    has_ceiling: bool = False
    ceiling_height: float = 2.0
    visible: bool = True


@dataclass
class StartPosition:
    id: int = 0
    position: Vec3 = field(default_factory=Vec3)
    angle: float = 0.0
    vert_angle: float = 0.0


@dataclass
class EndRegion:
    id: int = 0
    label: str = ""
    xmin: float = 0.0
    xmax: float = 0.0
    zmin: float = 0.0
    zmax: float = 0.0
    height: float = 2.0


@dataclass
class StaticModel:
    id: int = 0
    label: str = ""
    position: Vec3 = field(default_factory=Vec3)
    model_id: int = 0
    scale: float = 1.0
    rotation: Vec3 = field(default_factory=Vec3)


@dataclass
class DynamicObject:
    id: int = 0
    label: str = ""
    position: Vec3 = field(default_factory=Vec3)
    model_id: int = 0
    scale: float = 1.0
    rotation: Vec3 = field(default_factory=Vec3)
    trigger_action: str = ""
    trigger_radius: float = 2.0
    points_granted: int = 0


@dataclass
class Light:
    id: int = 0
    position: Vec3 = field(default_factory=Vec3)
    color: Color = field(default_factory=Color)
    intensity: float = 1.0
    attenuation: float = 0.08
    light_type: str = "Ambulatory"


@dataclass
class GlobalSettings:
    move_speed: float = 3.0
    turn_speed: float = 45.0
    ambient_color: Color = field(default_factory=Color)
    ambient_intensity: float = 0.6
    start_message: str = ""
    camera_mode: str = "First-Person"
    field_of_view: float = 45.0
    avatar_height: float = 0.0
    default_start_id: int = 1
    skybox_id: int = 0
    exit_threshold: int = 0
    exit_threshold_op: str = "GreaterThanEqual"


@dataclass
class MazeData:
    settings: GlobalSettings = field(default_factory=GlobalSettings)
    walls: list = field(default_factory=list)
    curved_walls: list = field(default_factory=list)
    floors: list = field(default_factory=list)
    start_positions: list = field(default_factory=list)
    end_regions: list = field(default_factory=list)
    static_models: list = field(default_factory=list)
    dynamic_objects: list = field(default_factory=list)
    lights: list = field(default_factory=list)
    images: dict = field(default_factory=dict)   # id -> filename
    models: dict = field(default_factory=dict)    # id -> filename
    sounds: dict = field(default_factory=dict)    # id -> filename
    # Resolved absolute paths (populated by resolve_assets)
    image_paths: dict = field(default_factory=dict)  # id -> Path
    model_paths: dict = field(default_factory=dict)  # id -> Path
    sound_paths: dict = field(default_factory=dict)  # id -> Path


def parse_maz(filepath: str) -> MazeData:
    """Parse a .maz XML file and return structured MazeData."""
    tree = ET.parse(filepath)
    root = tree.getroot()
    maze = MazeData()

    # --- Global settings ---
    g = root.find("Global")
    if g is not None:
        speed = g.find("Speed")
        if speed is not None:
            maze.settings.move_speed = float(speed.get("moveSpeed", 3))
            maze.settings.turn_speed = float(speed.get("turnSpeed", 45))

        amb = g.find("AmbientLight")
        if amb is not None:
            maze.settings.ambient_color = Color(
                float(amb.get("r", 1)), float(amb.get("g", 1)), float(amb.get("b", 1))
            )
            maze.settings.ambient_intensity = float(amb.get("intensity", 0.6))

        msg = g.find("StartMessage")
        if msg is not None and msg.get("enabled") == "True":
            maze.settings.start_message = msg.get("message", "")

        dsp = g.find("DefaultStartPosition")
        if dsp is not None:
            maze.settings.default_start_id = int(dsp.get("id", 1))

        sky = g.find("Skybox")
        if sky is not None:
            maze.settings.skybox_id = int(sky.get("id", 0))

        ps = g.find("PerspectiveSettings")
        if ps is not None:
            maze.settings.camera_mode = ps.get("cameraMode", "First-Person")
            maze.settings.field_of_view = float(ps.get("fieldOfView", 45))
            maze.settings.avatar_height = float(ps.get("avatarHeight", 0))

        po = g.find("PointOptions")
        if po is not None:
            maze.settings.exit_threshold = int(po.get("exitThreshold", 0))
            maze.settings.exit_threshold_op = po.get("exitThresholdOperator", "GreaterThanEqual")

    # --- Image library ---
    ilib = root.find("ImageLibrary")
    if ilib is not None:
        for img in ilib.findall("Image"):
            maze.images[int(img.get("id"))] = img.get("file", "")

    # --- Model library ---
    mlib = root.find("ModelLibrary")
    if mlib is not None:
        for mdl in mlib.findall("Model"):
            maze.models[int(mdl.get("id"))] = mdl.get("file", "")

    # --- Audio library ---
    alib = root.find("AudioLibrary")
    if alib is not None:
        for snd in alib.findall("Sound"):
            maze.sounds[int(snd.get("id"))] = snd.get("file", "")

    # --- Maze items ---
    items = root.find("MazeItems")
    if items is None:
        return maze

    # Walls
    walls_el = items.find("Walls")
    if walls_el is not None:
        for w in walls_el.findall("Wall"):
            wall = Wall(
                id=int(w.get("id", 0)),
                label=w.get("label", ""),
            )
            for pt_name in ["MzPoint1", "MzPoint2", "MzPoint3", "MzPoint4"]:
                pt = w.find(pt_name)
                if pt is not None:
                    wall.vertices.append(Vec3(
                        float(pt.get("x", 0)), float(pt.get("y", 0)), float(pt.get("z", 0))
                    ))
            tex = w.find("Texture")
            if tex is not None:
                wall.texture_id = int(tex.get("id", 0))
            col = w.find("Color")
            if col is not None:
                wall.color = Color(float(col.get("r", 1)), float(col.get("g", 1)), float(col.get("b", 1)))
            app = w.find("Appearance")
            if app is not None:
                wall.visible = app.get("visible", "True") == "True"
            maze.walls.append(wall)

    # Curved walls (arc/boundary walls)
    # Also inside <Walls> element, as <CurvedWall>
    if walls_el is not None:
        for cw in walls_el.findall("CurvedWall"):
            curved = CurvedWall(
                id=int(cw.get("id", 0)),
                label=cw.get("label", ""),
            )
            # Geometry: flat CSV of (x, y, z, texX, texY, ...) repeated per vertex
            geom_el = cw.find("Geometry")
            if geom_el is not None and geom_el.text:
                vals = [float(v) for v in geom_el.text.strip().rstrip(',').split(',')]
                # Each vertex is 5 values: x, y, z, texX, texY
                # But examining data: pairs of (top, bottom) vertices
                # Format: x,y,z,texX,texY repeated
                for i in range(0, len(vals), 5):
                    if i + 4 < len(vals):
                        curved.geometry_verts.append(Vec3(vals[i], vals[i+1], vals[i+2]))
                        curved.geometry_uvs.append((vals[i+3], vals[i+4]))

            # Indices: triangle vertex indices
            idx_el = cw.find("Indicies")  # note: typo in XML ("Indicies")
            if idx_el is not None and idx_el.text:
                curved.indices = [int(x) for x in idx_el.text.strip().split(',')]

            tex = cw.find("Texture")
            if tex is not None:
                curved.texture_id = int(tex.get("id", 0))
            col = cw.find("Color")
            if col is not None:
                curved.color = Color(float(col.get("r", 1)), float(col.get("g", 1)), float(col.get("b", 1)))
            app = cw.find("Appearance")
            if app is not None:
                curved.visible = app.get("visible", "True") == "True"
            maze.curved_walls.append(curved)

    # Floors
    floors_el = items.find("Floors")
    if floors_el is not None:
        for f in floors_el.findall("Floor"):
            floor = Floor(id=int(f.get("id", 0)))
            for pt_name in ["MzPoint1", "MzPoint2", "MzPoint3", "MzPoint4"]:
                pt = f.find(pt_name)
                if pt is not None:
                    floor.vertices.append(Vec3(
                        float(pt.get("x", 0)), float(pt.get("y", 0)), float(pt.get("z", 0))
                    ))
            ftex = f.find("FloorTexture")
            if ftex is not None:
                floor.texture_id = int(ftex.get("id", 0))
            fcol = f.find("FloorColor")
            if fcol is not None:
                floor.color = Color(float(fcol.get("r", 1)), float(fcol.get("g", 1)), float(fcol.get("b", 1)))
            app = f.find("Appearance")
            if app is not None:
                floor.has_ceiling = app.get("hasCeiling", "False") == "True"
                floor.ceiling_height = float(app.get("ceilingHeight", 2))
                floor.visible = app.get("visible", "True") == "True"
            maze.floors.append(floor)

    # Static models
    sm_el = items.find("StaticModels")
    if sm_el is not None:
        for sm in sm_el.findall("StaticModel"):
            pt = sm.find("MzPoint")
            pos = Vec3(float(pt.get("x", 0)), float(pt.get("y", 0)), float(pt.get("z", 0))) if pt is not None else Vec3()
            mdl = sm.find("Model")
            model_id = int(mdl.get("id", 0)) if mdl is not None else 0
            scale = float(mdl.get("scale", 1)) if mdl is not None else 1.0
            rot = Vec3(
                float(mdl.get("rotX", 0)), float(mdl.get("rotY", 0)), float(mdl.get("rotZ", 0))
            ) if mdl is not None else Vec3()
            maze.static_models.append(StaticModel(
                id=int(sm.get("id", 0)), label=sm.get("label", ""),
                position=pos, model_id=model_id, scale=scale, rotation=rot,
            ))

    # Start positions
    spos_el = items.find("StartPositions")
    if spos_el is not None:
        for sp in spos_el.findall("StartPosition"):
            pt = sp.find("MzPoint")
            pos = Vec3(float(pt.get("x", 0)), float(pt.get("y", 0)), float(pt.get("z", 0))) if pt is not None else Vec3()
            va = sp.find("ViewAngle")
            angle = float(va.get("angle", 0)) if va is not None else 0
            vert_angle = float(va.get("vertAngle", 0)) if va is not None else 0
            maze.start_positions.append(StartPosition(
                id=int(sp.get("id", 0)), position=pos, angle=angle, vert_angle=vert_angle
            ))

    # End regions
    er_el = items.find("EndRegions")
    if er_el is not None:
        for er in er_el.findall("EndRegion"):
            maze.end_regions.append(EndRegion(
                id=int(er.get("id", 0)),
                label=er.get("label", ""),
                xmin=float(er.get("xmin", 0)),
                xmax=float(er.get("xmax", 0)),
                zmin=float(er.get("zmin", 0)),
                zmax=float(er.get("zmax", 0)),
            ))

    # Dynamic objects
    dyn_el = items.find("DynamicObjects")
    if dyn_el is not None:
        for do in dyn_el.findall("DynamicObject"):
            pt = do.find("MzPoint")
            pos = Vec3(float(pt.get("x", 0)), float(pt.get("y", 0)), float(pt.get("z", 0))) if pt is not None else Vec3()
            mdl = do.find("Model")
            model_id = int(mdl.get("id", 0)) if mdl is not None else 0
            scale = float(mdl.get("scale", 1)) if mdl is not None else 1.0
            rot = Vec3(
                float(mdl.get("rotX", 0)), float(mdl.get("rotY", 0)), float(mdl.get("rotZ", 0))
            ) if mdl is not None else Vec3()

            trigger_action = ""
            trigger_radius = 2.0
            points_granted = 0
            p2 = do.find("Phase2Event")
            if p2 is not None:
                trigger_action = p2.get("triggerAction", "")
                trigger_radius = float(p2.get("radius", 2))
                points_granted = int(p2.get("pointsGranted", 0))

            maze.dynamic_objects.append(DynamicObject(
                id=int(do.get("id", 0)),
                label=do.get("label", ""),
                position=pos, model_id=model_id, scale=scale, rotation=rot,
                trigger_action=trigger_action, trigger_radius=trigger_radius,
                points_granted=points_granted,
            ))

    # Lights
    lights_el = items.find("Lights")
    if lights_el is not None:
        for lt in lights_el.findall("Light"):
            pt = lt.find("MzPoint")
            pos = Vec3(float(pt.get("x", 0)), float(pt.get("y", 0)), float(pt.get("z", 0))) if pt is not None else Vec3()
            col_el = lt.find("Color")
            col = Color(float(col_el.get("r", 1)), float(col_el.get("g", 1)), float(col_el.get("b", 1))) if col_el is not None else Color()
            app = lt.find("Appearance")
            intensity = float(app.get("intensity", 1)) if app is not None else 1.0
            attenuation = float(app.get("attenuation", 0.08)) if app is not None else 0.08
            light_type = app.get("type", "Ambulatory") if app is not None else "Ambulatory"
            maze.lights.append(Light(
                id=int(lt.get("id", 0)),
                position=pos, color=col,
                intensity=intensity, attenuation=attenuation, light_type=light_type,
            ))

    return maze


def resolve_assets(maze: MazeData, maz_filepath: str, library_dir: str = None):
    """
    Resolve asset filenames to absolute paths.

    Search order for each filename:
      1. Same directory as the .maz file
      2. library_dir (auto-detected as ../Library relative to .maz if not given)
      3. library_dir/Objs  (for models)
      4. library_dir/Audio (for sounds)
    """
    maz_path = Path(maz_filepath).resolve()
    maz_dir = maz_path.parent

    if library_dir is None:
        library_dir = maz_dir.parent / "Library"
    else:
        library_dir = Path(library_dir).resolve()

    def find_file(filename: str, subdirs: list[str] = None) -> Path | None:
        """Search for a file in standard locations."""
        name = Path(filename).name  # strip any directory prefix
        candidates = [
            maz_dir / name,
            library_dir / name,
        ]
        if subdirs:
            for sd in subdirs:
                candidates.append(library_dir / sd / name)
        for c in candidates:
            if c.exists():
                return c
        return None

    for img_id, filename in maze.images.items():
        path = find_file(filename)
        if path:
            maze.image_paths[img_id] = path

    for mdl_id, filename in maze.models.items():
        path = find_file(filename, subdirs=["Objs"])
        if path:
            maze.model_paths[mdl_id] = path

    for snd_id, filename in maze.sounds.items():
        path = find_file(filename, subdirs=["Audio"])
        if path:
            maze.sound_paths[snd_id] = path

    # Report missing assets
    for img_id, filename in maze.images.items():
        if img_id not in maze.image_paths:
            print(f"  [warn] Image not found: {filename} (id={img_id})")
    for mdl_id, filename in maze.models.items():
        if mdl_id not in maze.model_paths:
            print(f"  [warn] Model not found: {filename} (id={mdl_id})")
    for snd_id, filename in maze.sounds.items():
        if snd_id not in maze.sound_paths:
            print(f"  [warn] Sound not found: {filename} (id={snd_id})")


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python maz_parser.py <file.maz>")
        sys.exit(1)
    data = parse_maz(sys.argv[1])
    resolve_assets(data, sys.argv[1])
    print(f"Walls: {len(data.walls)}")
    print(f"Floors: {len(data.floors)}")
    print(f"Start positions: {len(data.start_positions)}")
    print(f"Dynamic objects: {len(data.dynamic_objects)}")
    print(f"Lights: {len(data.lights)}")
    print(f"Images: {data.images}")
    print(f"Models: {data.models}")
    print(f"Sounds: {data.sounds}")
    print(f"Resolved images: {data.image_paths}")
    print(f"Resolved models: {data.model_paths}")
    print(f"Resolved sounds: {data.sound_paths}")
    if data.start_positions:
        sp = data.start_positions[0]
        print(f"Start: ({sp.position.x:.1f}, {sp.position.y:.1f}, {sp.position.z:.1f}) angle={sp.angle}")
    print(f"Settings: speed={data.settings.move_speed}, fov={data.settings.field_of_view}")
    print(f"Start message: {data.settings.start_message}")
